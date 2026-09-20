#!/usr/bin/env python3
import csv
import glob
import hashlib
import io
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR", os.path.join(HOME, ".claude"))
CODEX_DIR = os.environ.get("CODEX_HOME", os.path.join(HOME, ".codex"))
PORT = int(os.environ.get("TOKENMETER_PORT", "7788"))
TEXT_CAP = 600

with open(os.path.join(HERE, "pricing.json")) as f:
    _pricing_file = json.load(f)
PRICING = {k: v for k, v in _pricing_file.items() if not k.startswith("_")}
PLANS = {k: v for k, v in _pricing_file.get("_plans", {}).items() if not k.startswith("_")}


def price_for(model):
    best = None
    for prefix in PRICING:
        if model.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return PRICING.get(best)


def cost_of(rec):
    p = price_for(rec["model"])
    if not p:
        return None
    usd = rec["in"] * p["input"] + rec["cr"] * p["cache_read"] + rec["out"] * p["output"]
    usd += rec["cw5"] * p["cache_write_5m"] + rec["cw1h"] * p["cache_write_1h"]
    return round(usd / 1e6, 6)


def prompt_text(content):
    if isinstance(content, str):
        return content[:TEXT_CAP]
    if isinstance(content, list) and not any(b.get("type") == "tool_result" for b in content if isinstance(b, dict)):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")[:TEXT_CAP]
    return None


def parse_claude(path):
    project = os.path.basename(os.path.dirname(path))
    by_msg = {}
    prompts = {}
    with open(path, "rb") as f:
        for raw in f:
            if b'"usage"' not in raw and b'"promptId"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            msg = d.get("message") or {}
            if d.get("type") == "user" and d.get("promptId") and d["promptId"] not in prompts:
                text = prompt_text(msg.get("content"))
                if text is not None:
                    prompts[d["promptId"]] = {"ts": d.get("timestamp"), "tool": "claude", "session": d.get("sessionId"), "project": d.get("cwd") or project, "id": d["promptId"], "text": text}
                continue
            u = msg.get("usage")
            if d.get("type") != "assistant" or not u or msg.get("model", "").startswith("<"):
                continue
            cw = u.get("cache_creation") or {}
            cw5 = cw.get("ephemeral_5m_input_tokens")
            cw1h = cw.get("ephemeral_1h_input_tokens", 0)
            if cw5 is None:
                cw5 = u.get("cache_creation_input_tokens", 0)
            by_msg[msg.get("id") or d.get("uuid")] = {
                "ts": d.get("timestamp"),
                "tool": "claude",
                "model": msg.get("model", "unknown"),
                "project": d.get("cwd") or project,
                "session": d.get("sessionId"),
                "in": u.get("input_tokens", 0),
                "cr": u.get("cache_read_input_tokens", 0),
                "cw5": cw5,
                "cw1h": cw1h,
                "out": u.get("output_tokens", 0),
                "reason": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
                "sub": bool(d.get("isSidechain")),
            }
    return list(by_msg.values()), list(prompts.values())


def parse_codex(path):
    new, old, prompts = [], [], []
    model, cwd, session = "unknown", None, None
    with open(path, "rb") as f:
        for raw in f:
            if b"token_usage_record" not in raw and b"token_count" not in raw and b"turn_context" not in raw and b"session_meta" not in raw and b"input_text" not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            p = d.get("payload") or {}
            t = d.get("type")
            if t == "session_meta":
                cwd, session = p.get("cwd"), p.get("id") or p.get("session_id")
                model = p.get("model") or model
            elif t == "turn_context":
                model = p.get("model") or model
                prompts.append({"ts": d.get("timestamp"), "tool": "codex", "session": session, "project": cwd, "id": p.get("turn_id"), "text": ""})
            elif t == "response_item" and p.get("role") == "user" and prompts and not prompts[-1]["text"]:
                texts = [b.get("text", "") for b in p.get("content", []) if isinstance(b, dict) and b.get("type") == "input_text"]
                texts = [x.strip() for x in texts if x.strip() and not x.lstrip().startswith("<")]
                if texts:
                    prompts[-1]["text"] = texts[0][:TEXT_CAP]
            elif t == "token_usage_record" and p.get("usage"):
                new.append(codex_rec(d, p["usage"], model, cwd, session))
            elif t == "event_msg" and p.get("type") == "token_count" and (p.get("info") or {}).get("last_token_usage"):
                old.append(codex_rec(d, p["info"]["last_token_usage"], model, cwd, session))
    return new or old, prompts


def codex_rec(d, u, model, cwd, session):
    cached = u.get("cached_input_tokens", 0)
    return {
        "ts": d.get("timestamp"),
        "tool": "codex",
        "model": model,
        "project": cwd or "unknown",
        "session": session,
        "in": max(u.get("input_tokens", 0) - cached, 0),
        "cr": cached,
        "cw5": u.get("cache_write_input_tokens", 0),
        "cw1h": 0,
        "out": u.get("output_tokens", 0),
        "reason": u.get("reasoning_output_tokens", 0),
        "sub": False,
    }


class Store:
    def __init__(self):
        self.files = {}
        self.lock = threading.Lock()
        self.version = ""
        self.scanned_at = 0

    def sources(self):
        for path in glob.glob(os.path.join(CLAUDE_DIR, "projects", "**", "*.jsonl"), recursive=True):
            yield path, parse_claude
        for path in glob.glob(os.path.join(CODEX_DIR, "sessions", "**", "*.jsonl"), recursive=True):
            yield path, parse_codex

    def scan(self):
        with self.lock:
            seen = set()
            h = hashlib.md5()
            for path, parser in self.sources():
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                seen.add(path)
                key = (st.st_mtime, st.st_size)
                h.update(f"{path}{key}".encode())
                if self.files.get(path, (None,))[0] != key:
                    try:
                        recs, prompts = parser(path)
                    except OSError:
                        continue
                    for r in recs:
                        r["cost"] = cost_of(r)
                    self.files[path] = (key, recs, prompts)
            for gone in set(self.files) - seen:
                del self.files[gone]
            self.version = h.hexdigest()[:12]
            self.scanned_at = time.time()

    def snapshot(self):
        self.scan()
        with self.lock:
            recs = list({(r["ts"], r["session"], r["out"], r["cr"]): r for _, rs, _ in self.files.values() for r in rs}.values())
            prompts = list({p["id"]: p for _, _, ps in self.files.values() for p in ps}.values())
        recs.sort(key=lambda r: r["ts"] or "")
        prompts.sort(key=lambda p: p["ts"] or "")
        return {
            "version": self.version,
            "generated": self.scanned_at,
            "records": recs,
            "prompts": prompts,
            "priced_models": sorted(PRICING),
            "plans": PLANS,
            "sources": {"claude": CLAUDE_DIR, "codex": CODEX_DIR},
        }


STORE = Store()
FIELDS = ["ts", "tool", "model", "project", "session", "in", "cr", "cw5", "cw1h", "out", "reason", "sub", "cost"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype="application/json", status=200, extra=None):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send(f.read(), "text/html; charset=utf-8")
        if url.path == "/api/health":
            return self.send(json.dumps({"ok": True, "app": "tokenmeter"}))
        if url.path == "/api/version":
            STORE.scan()
            return self.send(json.dumps({"version": STORE.version}))
        if url.path == "/api/usage":
            return self.send(json.dumps(STORE.snapshot(), separators=(",", ":")))
        if url.path == "/api/export.csv":
            since = parse_qs(url.query).get("since", [""])[0]
            out = io.StringIO()
            w = csv.DictWriter(out, FIELDS)
            w.writeheader()
            for r in STORE.snapshot()["records"]:
                if (r["ts"] or "") >= since:
                    w.writerow(r)
            return self.send(out.getvalue(), "text/csv", extra={"Content-Disposition": "attachment; filename=tokenmeter.csv"})
        self.send("not found", "text/plain", 404)


def already_running(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return json.load(r).get("app") == "tokenmeter"
    except Exception:
        return False


def main():
    port = PORT
    args = sys.argv[1:]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    url = f"http://127.0.0.1:{port}"
    if already_running(port):
        print(f"tokenmeter already running at {url}")
        if "--open" in args:
            webbrowser.open(url)
        return
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t0 = time.time()
    STORE.scan()
    n = sum(len(rs) for _, rs, _ in STORE.files.values())
    print(f"tokenmeter: indexed {n} turns from {len(STORE.files)} transcripts in {time.time() - t0:.1f}s")
    print(f"tokenmeter: serving {url}", flush=True)
    if "--open" in args:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
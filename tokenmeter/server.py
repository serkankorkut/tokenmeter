#!/usr/bin/env python3
import csv
import datetime as dt
import getpass
import glob
import hashlib
import io
import json
import os
import plistlib
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

__version__ = "0.3.0"
HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR", os.path.join(HOME, ".claude"))
CODEX_DIR = os.environ.get("CODEX_HOME", os.path.join(HOME, ".codex"))
COPILOT_DB = os.environ.get("COPILOT_DB", os.path.join(HOME, ".copilot", "session-store.db"))
DATA_DIR = os.environ.get("TOKENMETER_DIR", os.path.join(HOME, ".tokenmeter"))
TEAM_DIR = os.path.join(DATA_DIR, "team")
TEXT_CAP = 600
USER = getpass.getuser()
TOKEN = os.environ.get("TOKENMETER_TOKEN", "")

with open(os.path.join(HERE, "pricing.json")) as f:
    _cfg = json.load(f)
USER_CONFIG = os.path.join(DATA_DIR, "config.json")
if os.path.exists(USER_CONFIG):
    with open(USER_CONFIG) as f:
        for k, v in json.load(f).items():
            if isinstance(v, dict) and isinstance(_cfg.get(k), dict):
                _cfg[k].update(v)
            else:
                _cfg[k] = v
PORT_SET = os.environ.get("TOKENMETER_PORT") or _cfg.get("_port")
PORT = int(PORT_SET or 7788)
PORT_SPAN = 10
PRICING = {k: v for k, v in _cfg.items() if not k.startswith("_")}
PLANS = {k: v for k, v in _cfg.get("_plans", {}).items() if not k.startswith("_")}
BUDGET = {k: v for k, v in _cfg.get("_budget", {}).items() if not k.startswith("_") and v}
CONTEXT_WINDOWS = {k: v for k, v in _cfg.get("_context_windows", {}).items() if not k.startswith("_")}


def longest_prefix(table, model):
    best = None
    for prefix in table:
        if model.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return table.get(best)


def price_for(model):
    return longest_prefix(PRICING, model)


def rates_for(rec):
    p = price_for(rec["model"])
    if p and p.get("long") and rec["in"] + rec["cr"] + rec["cw5"] + rec["cw1h"] > p["long"]["above"]:
        return dict(p, **{k: v for k, v in p["long"].items() if k != "above"})
    return p


def cost_of(rec):
    p = rates_for(rec)
    if not p:
        return None
    usd = rec["in"] * p["input"] + rec["cr"] * p["cache_read"] + rec["out"] * p["output"]
    usd += rec["cw5"] * p["cache_write_5m"] + rec["cw1h"] * p["cache_write_1h"]
    return round(usd / 1e6, 6)


def rec(ts, tool, model, project, session, i, cr, cw5, cw1h, out, reason, sub=False):
    return {"ts": ts, "tool": tool, "model": model or "unknown", "project": project or "unknown", "session": session, "in": i or 0, "cr": cr or 0, "cw5": cw5 or 0, "cw1h": cw1h or 0, "out": out or 0, "reason": reason or 0, "sub": sub, "user": USER}


def prompt(ts, tool, session, project, pid, text):
    return {"ts": ts, "tool": tool, "session": session, "project": project or "unknown", "id": pid, "text": (text or "")[:TEXT_CAP], "user": USER}


def prompt_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list) and not any(b.get("type") == "tool_result" for b in content if isinstance(b, dict)):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return None


def parse_claude(path):
    project = os.path.basename(os.path.dirname(path))
    by_msg, prompts = {}, {}
    with open(path, "rb") as f:
        for raw in f:
            if b'"usage"' not in raw and (b'"promptId"' not in raw or b'"tool_result"' in raw):
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            msg = d.get("message") or {}
            if d.get("type") == "user" and d.get("promptId") and d["promptId"] not in prompts:
                text = prompt_text(msg.get("content"))
                if text is not None:
                    prompts[d["promptId"]] = prompt(d.get("timestamp"), "claude", d.get("sessionId"), d.get("cwd") or project, d["promptId"], text)
                continue
            u = msg.get("usage")
            if d.get("type") != "assistant" or not u or msg.get("model", "").startswith("<"):
                continue
            cw = u.get("cache_creation") or {}
            cw5 = cw.get("ephemeral_5m_input_tokens")
            if cw5 is None:
                cw5 = u.get("cache_creation_input_tokens", 0)
            by_msg[msg.get("id") or d.get("uuid")] = rec(d.get("timestamp"), "claude", msg.get("model"), d.get("cwd") or project, d.get("sessionId"),
                u.get("input_tokens"), u.get("cache_read_input_tokens"), cw5, cw.get("ephemeral_1h_input_tokens"), u.get("output_tokens"),
                (u.get("output_tokens_details") or {}).get("thinking_tokens"), bool(d.get("isSidechain")))
    return list(by_msg.values()), list(prompts.values()), {}


def parse_codex(path):
    new, old, prompts, meta = [], [], [], {}
    model, cwd, session = "unknown", None, None
    with open(path, "rb") as f:
        for raw in f:
            if not any(k in raw for k in (b"token_usage_record", b"token_count", b"turn_context", b"session_meta", b"input_text")):
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
                prompts.append(prompt(d.get("timestamp"), "codex", session, cwd, p.get("turn_id"), ""))
            elif t == "response_item" and p.get("role") == "user" and prompts and not prompts[-1]["text"]:
                texts = [b.get("text", "") for b in p.get("content", []) if isinstance(b, dict) and b.get("type") == "input_text"]
                texts = [x.strip() for x in texts if x.strip() and not x.lstrip().startswith("<")]
                if texts:
                    prompts[-1]["text"] = texts[0][:TEXT_CAP]
            elif t == "token_usage_record" and p.get("usage"):
                new.append(codex_rec(d, p["usage"], model, cwd, session))
            elif t == "event_msg" and p.get("type") == "token_count":
                info = p.get("info") or {}
                if info.get("last_token_usage"):
                    old.append(codex_rec(d, info["last_token_usage"], model, cwd, session))
                if info.get("model_context_window"):
                    meta["ctx"] = info["model_context_window"]
                rl = p.get("rate_limits") or {}
                if rl.get("primary") or rl.get("secondary"):
                    meta["limits"] = {"ts": d.get("timestamp"), "plan": rl.get("plan_type"), "windows": [w for w in (rl.get("primary"), rl.get("secondary")) if w]}
    return new or old, prompts, meta


def codex_rec(d, u, model, cwd, session):
    cached = u.get("cached_input_tokens", 0) or 0
    return rec(d.get("timestamp"), "codex", model, cwd, session, max((u.get("input_tokens") or 0) - cached, 0), cached,
        u.get("cache_write_input_tokens"), 0, u.get("output_tokens"), u.get("reasoning_output_tokens"))


def parse_copilot(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cwds = dict(con.execute("select id, cwd from sessions"))
        recs = [rec(ts, "copilot", model, cwds.get(sid), sid, max((i or 0) - (cr or 0), 0), cr, cw, 0, out, reason, bool(agent))
            for sid, model, i, out, cr, cw, reason, agent, ts in
            con.execute("select session_id, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens, agent_id, created_at from assistant_usage_events")]
        prompts = [prompt(ts, "copilot", sid, cwds.get(sid), f"{sid}:{idx}", text) for sid, idx, text, ts in
            con.execute("select session_id, turn_index, user_message, timestamp from turns where user_message is not null")]
    finally:
        con.close()
    for r in recs + prompts:
        if r["ts"] and "T" not in r["ts"]:
            r["ts"] = r["ts"].replace(" ", "T") + "Z"
    return recs, prompts, {}


def parse_team(path):
    with open(path) as f:
        d = json.load(f)
    for r in d.get("records", []) + d.get("prompts", []):
        r["user"] = d["user"]
    return d.get("records", []), d.get("prompts", []), {}


class Store:
    def __init__(self):
        self.files = {}
        self.lock = threading.Lock()
        self.version = ""
        self.scanned_at = 0
        self.alerts = []
        self._claude_limits = (0, None)
        self._commits = {}
        self.indexing = True
        self.progress = (0, 0)
        self._usage = ("", b"")
        self._usage_lock = threading.Lock()

    def sources(self):
        for path in glob.glob(os.path.join(CLAUDE_DIR, "projects", "**", "*.jsonl"), recursive=True):
            yield path, parse_claude
        for path in glob.glob(os.path.join(CODEX_DIR, "sessions", "**", "*.jsonl"), recursive=True):
            yield path, parse_codex
        if os.path.exists(COPILOT_DB):
            yield COPILOT_DB, parse_copilot
        for path in glob.glob(os.path.join(TEAM_DIR, "*.json")):
            yield path, parse_team

    def scan(self):
        sources = list(self.sources())
        seen = set()
        h = hashlib.md5()
        for i, (path, parser) in enumerate(sources):
            self.progress = (i, len(sources))
            try:
                st = os.stat(path)
            except OSError:
                continue
            seen.add(path)
            key = (st.st_mtime, st.st_size)
            h.update(f"{path}{key}".encode())
            if self.files.get(path, (None,))[0] != key:
                try:
                    recs, prompts, meta = parser(path)
                except (OSError, sqlite3.Error, ValueError, KeyError):
                    continue
                recs = [r for r in recs if r["ts"]]
                for r in recs:
                    r["cost"] = cost_of(r)
                with self.lock:
                    self.files[path] = (key, recs, prompts, meta)
        with self.lock:
            for gone in set(self.files) - seen:
                del self.files[gone]
        self.progress = (len(sources), len(sources))
        self.version = h.hexdigest()[:12]
        self.scanned_at = time.time()
        self.indexing = False

    def scan_loop(self, on_first=None):
        t0 = time.time()
        while True:
            try:
                self.scan()
            except Exception as e:
                print(f"tokenmeter: scan failed: {e}", file=sys.stderr, flush=True)
            if on_first:
                on_first(time.time() - t0)
                on_first = None
            time.sleep(3)

    def usage_json(self):
        with self._usage_lock:
            if self._usage[0] != self.version:
                self._usage = (self.version, json.dumps(self.snapshot(), separators=(",", ":")).encode())
            return self._usage[1]

    def records(self):
        with self.lock:
            recs = list({(r["ts"], r["session"], r["out"], r["cr"], r["user"]): r for _, rs, _, _ in self.files.values() for r in rs}.values())
            prompts = list({(p["id"], p["user"]): p for _, _, ps, _ in self.files.values() for p in ps}.values())
            metas = [m for _, _, _, m in self.files.values() if m]
        recs.sort(key=lambda r: r["ts"])
        prompts.sort(key=lambda p: p["ts"] or "")
        return recs, prompts, metas

    def snapshot(self):
        recs, prompts, metas = self.records()
        codex_limits = max((m["limits"] for m in metas if m.get("limits")), key=lambda l: l["ts"] or "", default=None)
        ctx = dict(CONTEXT_WINDOWS)
        for m in metas:
            if m.get("ctx"):
                ctx["codex"] = m["ctx"]
        return {
            "version": self.version,
            "app_version": __version__,
            "generated": self.scanned_at,
            "records": recs,
            "prompts": prompts,
            "pricing": {m: price_for(m) for m in {r["model"] for r in recs} if price_for(m)},
            "plans": PLANS,
            "budget": BUDGET,
            "context_windows": ctx,
            "limits": {"codex": codex_limits, "claude": self.claude_limits()},
            "alerts": self.alerts[-10:],
            "users": sorted({r["user"] for r in recs}),
            "me": USER,
            "sources": {"claude": CLAUDE_DIR, "codex": CODEX_DIR, "copilot": COPILOT_DB, "team": TEAM_DIR},
        }

    def claude_limits(self):
        if time.time() - self._claude_limits[0] < 60:
            return self._claude_limits[1]
        data = None
        try:
            if sys.platform == "darwin":
                raw = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"], capture_output=True, text=True, timeout=3).stdout
            else:
                with open(os.path.join(CLAUDE_DIR, ".credentials.json")) as f:
                    raw = f.read()
            tok = json.loads(raw).get("claudeAiOauth", {}).get("accessToken")
            if tok:
                req = Request("https://api.anthropic.com/api/oauth/usage", headers={"Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20"})
                with urlopen(req, timeout=5) as r:
                    data = json.load(r)
        except Exception:
            data = None
        self._claude_limits = (time.time(), data)
        return data

    def commits(self):
        recs, _, _ = self.records()
        out = {}
        for project in {r["project"] for r in recs if r["user"] == USER}:
            if not os.path.isdir(os.path.join(project, ".git")):
                continue
            cached = self._commits.get(project)
            if cached and time.time() - cached[0] < 120:
                out[project] = cached[1]
                continue
            try:
                log = subprocess.run(["git", "-C", project, "log", "--all", "--no-merges", "--since=120.days", "-n", "500", "--format=%H%x1f%at%x1f%s"], capture_output=True, text=True, timeout=10).stdout
                commits = [{"sha": s, "ts": dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "subject": subj}
                    for s, t, subj in (l.split("\x1f") for l in log.splitlines() if l.count("\x1f") == 2)]
            except (OSError, ValueError, subprocess.TimeoutExpired):
                commits = []
            self._commits[project] = (time.time(), commits)
            out[project] = commits
        return out

    def summary(self):
        recs, prompts, metas = self.records()
        now = dt.datetime.now().astimezone()
        day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month0 = day0.replace(day=1)
        utc = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        mine = [r for r in recs if r["user"] == USER]
        since = lambda t: [r for r in mine if r["ts"] >= utc(t)]
        agg = lambda rs: {"tokens": sum(r["in"] + r["cr"] + r["cw5"] + r["cw1h"] + r["out"] for r in rs), "cost": round(sum(r["cost"] or 0 for r in rs), 4), "turns": len(rs)}
        by_tool = lambda rs: {k: agg([r for r in rs if r["tool"] == k]) for k in {r["tool"] for r in rs}}
        today, month = since(day0), since(month0)
        next_month = month0.replace(month=month0.month % 12 + 1, year=month0.year + month0.month // 12)
        elapsed = max(1 / 24, (now - month0).total_seconds() / 86400)
        return {
            "today": dict(agg(today), prompts=sum(1 for p in prompts if (p["ts"] or "") >= utc(day0) and p["user"] == USER)),
            "today_by_tool": by_tool(today),
            "last_5h": by_tool(since(now - dt.timedelta(hours=5))),
            "last_7d": by_tool(since(now - dt.timedelta(days=7))),
            "month": agg(month),
            "month_projection": round(agg(month)["cost"] / elapsed * (next_month - month0).days, 2),
            "budget": BUDGET,
            "plans": PLANS,
            "limits": {"codex": max((m["limits"] for m in metas if m.get("limits")), key=lambda l: l["ts"] or "", default=None), "claude": self.claude_limits()},
            "alerts": self.alerts[-5:],
        }


STORE = Store()
FIELDS = ["ts", "tool", "model", "project", "session", "user", "in", "cr", "cw5", "cw1h", "out", "reason", "sub", "cost"]


def notify(title, body):
    STORE.alerts.append({"ts": time.time(), "title": title, "body": body})
    print(f"tokenmeter: ALERT {title}: {body}", flush=True)
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f'display notification "{body}" with title "{title}"'], capture_output=True, timeout=5)


def budget_loop():
    notified = set()
    while True:
        try:
            s = STORE.summary()
            day = dt.date.today().isoformat()
            if BUDGET.get("daily") and s["today"]["cost"] > BUDGET["daily"] and ("d", day) not in notified:
                notified.add(("d", day))
                notify("Tokenmeter daily budget exceeded", f"${s['today']['cost']:.2f} today, budget ${BUDGET['daily']}")
            if BUDGET.get("monthly") and s["month"]["cost"] > BUDGET["monthly"] and ("m", day[:7]) not in notified:
                notified.add(("m", day[:7]))
                notify("Tokenmeter monthly budget exceeded", f"${s['month']['cost']:.2f} this month, budget ${BUDGET['monthly']}")
        except Exception as e:
            print(f"tokenmeter: budget check failed: {e}", flush=True)
        time.sleep(60)


def export_loop(url):
    while True:
        try:
            recs, prompts, _ = STORE.records()
            since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
            payload = {"user": USER, "records": [r for r in recs if r["ts"] >= since and r["user"] == USER],
                "prompts": [dict(p, text="") for p in prompts if (p["ts"] or "") >= since and p["user"] == USER]}
            req = Request(url.rstrip("/") + "/api/ingest", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "X-Tokenmeter-Token": TOKEN}, method="POST")
            with urlopen(req, timeout=30) as r:
                print(f"tokenmeter: exported {len(payload['records'])} turns to {url} ({r.status})", flush=True)
        except Exception as e:
            print(f"tokenmeter: export failed: {e}", flush=True)
        time.sleep(3600)


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
        try:
            self.route(urlparse(self.path))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception:
            err = traceback.format_exc()
            print(f"tokenmeter: error serving {self.path}\n{err}", file=sys.stderr, flush=True)
            try:
                self.send(json.dumps({"error": err.strip().splitlines()[-1], "path": self.path}), status=500)
            except OSError:
                self.close_connection = True

    def route(self, url):
        if url.path == "/":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send(f.read(), "text/html; charset=utf-8")
        if url.path == "/api/tips":
            return self.send(json.dumps({"tools": [t for t, cmd in ADVISORS.items() if shutil.which(cmd[0])]}))
        if url.path == "/api/health":
            return self.send(json.dumps({"ok": True, "app": "tokenmeter", "version": __version__, "user": USER, "pid": os.getpid()}))
        if url.path == "/api/version":
            done, total = STORE.progress
            return self.send(json.dumps({"version": STORE.version, "indexing": STORE.indexing, "done": done, "total": total}))
        if url.path == "/api/usage":
            return self.send(STORE.usage_json())
        if url.path == "/api/summary":
            return self.send(json.dumps(STORE.summary()))
        if url.path == "/api/commits":
            return self.send(json.dumps(STORE.commits(), separators=(",", ":")))
        if url.path == "/api/export.csv":
            since = parse_qs(url.query).get("since", [""])[0]
            out = io.StringIO()
            w = csv.DictWriter(out, FIELDS)
            w.writeheader()
            for r in STORE.snapshot()["records"]:
                if r["ts"] >= since:
                    w.writerow(r)
            return self.send(out.getvalue(), "text/csv", extra={"Content-Disposition": "attachment; filename=tokenmeter.csv"})
        self.send("not found", "text/plain", 404)

    def do_POST(self):
        if urlparse(self.path).path == "/api/tips":
            return self.tips()
        if urlparse(self.path).path != "/api/ingest":
            return self.send("not found", "text/plain", 404)
        if TOKEN and self.headers.get("X-Tokenmeter-Token") != TOKEN:
            return self.send("forbidden", "text/plain", 403)
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            user = d["user"]
            if not re.fullmatch(r"[\w.\-]{1,64}", user):
                raise ValueError("bad user")
            recs = [rec(r["ts"], r["tool"], r["model"], r["project"], r["session"], r["in"], r["cr"], r["cw5"], r["cw1h"], r["out"], r["reason"], bool(r.get("sub"))) for r in d.get("records", [])]
            prompts = [prompt(p["ts"], p["tool"], p["session"], p["project"], p["id"], "") for p in d.get("prompts", [])]
        except (ValueError, KeyError, TypeError) as e:
            return self.send(f"bad request: {e}", "text/plain", 400)
        os.makedirs(TEAM_DIR, exist_ok=True)
        path = os.path.join(TEAM_DIR, f"{user}.json")
        with open(path + ".tmp", "w") as f:
            json.dump({"user": user, "updated": time.time(), "records": recs, "prompts": prompts}, f)
        os.replace(path + ".tmp", path)
        self.send(json.dumps({"ok": True, "records": len(recs)}))

    def tips(self):
        origin = urlparse(self.headers.get("Origin") or "http://" + (self.headers.get("Host") or "")).netloc
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if origin != self.headers.get("Host") or host not in ("127.0.0.1", "localhost", "[::1]") or self.headers.get("Content-Type") != "application/json":
            return self.send(json.dumps({"error": "Tips can only be requested from the dashboard page."}), status=403)
        try:
            d = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 200000)))
            self.send(json.dumps(ask_advisor(d["tool"], d["prompt"])))
        except (ValueError, KeyError, TypeError) as e:
            self.send(json.dumps({"error": f"Bad request: {e}"}), status=400)


ADVISORS = {
    "claude": ["claude", "-p", "--tools", ""],
    "codex": ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-"],
    "copilot": ["copilot", "-p"],
}


def ask_advisor(tool, text):
    cmd = ADVISORS.get(tool)
    if not cmd or not shutil.which(cmd[0]):
        return {"error": f"The {cmd[0] if cmd else tool} command was not found on this machine, so Tokenmeter cannot ask it. Use Copy prompt and paste it into your AI tool instead."}
    args, stdin = (cmd + [text], None) if tool == "copilot" else (cmd, text)
    try:
        r = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=300, cwd=tempfile.gettempdir(), stdin=None if stdin is not None else subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"error": f"{cmd[0]} did not answer within 5 minutes. Try again, or use Copy prompt."}
    out = r.stdout.strip()
    if r.returncode or not out:
        why = (r.stderr.strip() or out or "no output").splitlines()[-1][:300]
        return {"error": f"{cmd[0]} stopped with an error: {why}. If it asks you to log in, run {cmd[0]} once in a terminal, then try again."}
    return {"text": out}


def health(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as r:
            d = json.load(r)
            return d if d.get("app") == "tokenmeter" else None
    except Exception:
        return None


def ports_to_try(port_arg=None):
    if port_arg or PORT_SET:
        return [int(port_arg or PORT)]
    return list(range(PORT, PORT + PORT_SPAN + 1))


def find_running(ports):
    for p in ports:
        h = health(p)
        if h:
            return p, h
    return None, None


def taken(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def bind(host, ports):
    for p in ports:
        if taken(p):
            continue
        try:
            return p, ThreadingHTTPServer((host, p), Handler)
        except OSError:
            continue
    return None, None


def busy(ports):
    which = f"Port {ports[0]} is" if len(ports) == 1 else f"Ports {ports[0]}-{ports[-1]} are all"
    free = next((p for p in range(max(ports) + 1, max(ports) + 200) if not taken(p)), None)
    hint = f" Pick a free one, for example: tokenmeter start --port {free}" if free else " Pick a free one with: tokenmeter start --port N"
    return f"tokenmeter: {which} in use by other apps.{hint}"


def save_port(port):
    cfg = {}
    if os.path.exists(USER_CONFIG):
        with open(USER_CONFIG) as f:
            cfg = json.load(f)
    cfg["_port"] = port
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USER_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


LABEL = "fyi.tokenmeter"
LEGACY_LABELS = ("sh.brew.tokenmeter", "homebrew.mxcl.tokenmeter")
AGENTS_DIR = os.path.join(HOME, "Library", "LaunchAgents")
UNIT = os.path.join(HOME, ".config", "systemd", "user", "tokenmeter.service")
LOG = os.path.join(DATA_DIR, "server.log")
PASS_ENV = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "COPILOT_DB", "TOKENMETER_DIR", "TOKENMETER_TOKEN")


def program():
    if "/Cellar/tokenmeter/" in HERE:
        opt = HERE.split("/Cellar/")[0] + "/opt/tokenmeter/bin/tokenmeter"
        if os.path.exists(opt):
            return [opt]
    return [sys.executable, os.path.join(HERE, "server.py")]


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True).returncode == 0
    except OSError:
        return False


def launchd(cmd):
    uid = os.getuid()
    for label in LEGACY_LABELS + (LABEL,):
        run("launchctl", "bootout", f"gui/{uid}/{label}")
    for label in LEGACY_LABELS:
        legacy = os.path.join(AGENTS_DIR, label + ".plist")
        if os.path.exists(legacy):
            os.remove(legacy)
    plist = os.path.join(AGENTS_DIR, LABEL + ".plist")
    if cmd == "stop":
        if os.path.exists(plist):
            os.remove(plist)
        return True
    prog = program()
    os.makedirs(AGENTS_DIR, exist_ok=True)
    job = {"Label": LABEL, "ProgramArguments": prog, "RunAtLoad": True, "KeepAlive": {"PathState": {prog[-1]: True}}, "StandardOutPath": LOG, "StandardErrorPath": LOG}
    env = {k: os.environ[k] for k in PASS_ENV if os.environ.get(k)}
    if env:
        job["EnvironmentVariables"] = env
    with open(plist, "wb") as f:
        plistlib.dump(job, f)
    if run("launchctl", "bootstrap", f"gui/{uid}", plist):
        return True
    os.remove(plist)
    return False


def systemd(cmd):
    if not shutil.which("systemctl"):
        return False
    if cmd == "stop":
        run("systemctl", "--user", "disable", "--now", "tokenmeter")
        if os.path.exists(UNIT):
            os.remove(UNIT)
            run("systemctl", "--user", "daemon-reload")
        return True
    os.makedirs(os.path.dirname(UNIT), exist_ok=True)
    env = "".join(f"Environment={k}={shlex.quote(os.environ[k])}\n" for k in PASS_ENV if os.environ.get(k))
    with open(UNIT, "w") as f:
        f.write(f"[Unit]\nDescription=Tokenmeter dashboard\n\n[Service]\nExecStart={shlex.join(program())}\nRestart=always\n{env}\n[Install]\nWantedBy=default.target\n")
    if run("systemctl", "--user", "daemon-reload") and run("systemctl", "--user", "enable", "tokenmeter") and run("systemctl", "--user", "restart", "tokenmeter"):
        return True
    os.remove(UNIT)
    return False


def service(cmd):
    if sys.platform == "darwin":
        return launchd(cmd)
    if sys.platform.startswith("linux"):
        return systemd(cmd)
    return False


def service_installed():
    return os.path.exists(os.path.join(AGENTS_DIR, LABEL + ".plist")) or os.path.exists(UNIT)


def stop_all(ports):
    service("stop")
    for p in sorted(set(ports) | set(range(PORT, PORT + PORT_SPAN + 1))):
        h = health(p)
        if h:
            try:
                os.kill(h["pid"], 15)
            except OSError:
                pass
    for p in ports:
        for _ in range(40):
            if not health(p):
                break
            time.sleep(0.25)


def control(cmd, port_arg):
    ports = ports_to_try(port_arg)
    if cmd == "stop":
        stop_all(ports)
        print("tokenmeter stopped")
        return
    p, h = find_running(ports)
    if p and (h.get("version") != __version__ or not service_installed()):
        if h.get("version") != __version__:
            print(f"tokenmeter: restarting the running {h.get('version', 'older')} dashboard on {__version__}")
        stop_all(ports)
        p, h = None, None
    elif not p:
        stop_all(ports)
    if not p and not any(not taken(q) for q in ports):
        print(busy(ports), file=sys.stderr)
        sys.exit(1)
    if port_arg:
        save_port(int(port_arg))
        print(f"tokenmeter: saved port {port_arg} to {USER_CONFIG}")
    login = service_installed()
    if not p:
        login = service("start")
        if not login:
            os.makedirs(DATA_DIR, exist_ok=True)
            log = open(LOG, "a")
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(program() + (["--port", str(port_arg)] if port_arg else []), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, creationflags=flags)
        for _ in range(60):
            p, h = find_running(ports)
            if p:
                break
            time.sleep(0.25)
        else:
            print(f"tokenmeter did not start. See {LOG}", file=sys.stderr)
            sys.exit(1)
    url = f"http://127.0.0.1:{p}"
    if p != ports[0]:
        print(f"\n  Port {ports[0]} is used by another app, so Tokenmeter is on {p}.")
    print("\n  Tokenmeter is running in the background" + (" and starts again at login." if login else ".") + "\n  Stop it with: tokenmeter stop\n")
    print(f"  Your dashboard: {url}\n")
    print(path_hint(), end="")
    webbrowser.open(url)


def path_hint():
    launcher = os.path.abspath(sys.argv[0])
    if os.path.splitext(os.path.basename(launcher))[0] != "tokenmeter" or shutil.which("tokenmeter"):
        return ""
    fix = "pipx ensurepath" if "pipx" in os.path.realpath(launcher) else f'add {os.path.dirname(launcher)} to your PATH'
    return f"  Typing just `tokenmeter` will not work yet: {os.path.dirname(launcher)} is not on your PATH.\n  To fix it, run `{fix}`, then open a new terminal.\n\n"


def arg(name, default=None):
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


def main():
    global USER
    if "--version" in sys.argv:
        print(f"tokenmeter {__version__}")
        return
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""usage: tokenmeter start | stop
       tokenmeter [--open] [--port N] [--host ADDR] [--user NAME] [--export URL] [--version]

  start   run the dashboard in the background and open it in your browser
  stop    stop the background dashboard
  (none)  run in this terminal until Ctrl+C

  --port N  use this port instead of 7788. With start it is saved, so later runs
            and the background service use it too. Without a saved port, Tokenmeter
            tries 7788 and, if another app has it, the next 10 ports.

The dashboard is at http://127.0.0.1:7788 unless that port was taken.""")
        return
    port_arg = arg("--port")
    if len(sys.argv) > 1 and sys.argv[1] in ("start", "stop"):
        return control(sys.argv[1], port_arg)
    host = arg("--host", "127.0.0.1")
    USER = arg("--user", USER)
    ports = ports_to_try(port_arg)
    port, running = find_running(ports)
    if running:
        print(f"tokenmeter already running at http://127.0.0.1:{port}")
        if running.get("version") != __version__:
            print(f"tokenmeter: that is version {running.get('version')}; run tokenmeter start to restart it on {__version__}")
        if "--open" in sys.argv:
            webbrowser.open(f"http://127.0.0.1:{port}")
        return
    port, server = bind(host, ports)
    if not server:
        print(busy(ports), file=sys.stderr)
        sys.exit(1)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{port}"
    if port != ports[0]:
        print(f"\n  Port {ports[0]} is used by another app, so Tokenmeter is on {port}.", flush=True)
    print(f"\n  Tokenmeter dashboard: {url}" + (f"  (bound to {host})" if host != "127.0.0.1" else "") + "\n  Open it in your browser. Press Ctrl+C to stop, or use tokenmeter start to run it in the background.\n", flush=True)
    done = lambda secs: print(f"tokenmeter: indexed {len(STORE.records()[0])} turns from {len(STORE.files)} sources in {secs:.1f}s", flush=True)
    threading.Thread(target=STORE.scan_loop, args=(done,), daemon=True).start()
    if BUDGET:
        threading.Thread(target=budget_loop, daemon=True).start()
    if arg("--export"):
        threading.Thread(target=export_loop, args=(arg("--export"),), daemon=True).start()
    if "--open" in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
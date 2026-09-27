import datetime as dt
import json
import os
import random
import sqlite3
import sys
import uuid

OUT = sys.argv[1] if len(sys.argv) > 1 else "demo"
random.seed(7)
NOW = dt.datetime.now(dt.timezone.utc)
PROJECTS = ["/Users/demo/code/acme-api", "/Users/demo/code/web-app", "/Users/demo/code/infra", "/Users/demo/code/mobile"]
PROMPTS = [
    "fix the flaky auth test",
    "add pagination to the orders endpoint",
    "why is the CI build so slow now?",
    "write tests for the retry logic in the http client",
    "refactor the payment webhook handler, it's getting hard to follow",
    "explain this stack trace and fix the root cause",
    "migrate the config loader to pydantic settings",
    "add dark mode to the settings page",
    "review this diff for race conditions",
    "bump dependencies and fix whatever breaks",
    "add a health check endpoint for the load balancer",
    "the signup form double-submits on slow networks, fix it",
    "write a migration to backfill the missing created_at values",
    "make the image upload resumable",
    "profile the search query and add the right index",
    "split the monolithic utils module into something sane",
    "add structured logging with request ids",
    "set up a staging deploy workflow",
]
CLAUDE_MODELS = [("claude-opus-5-5", 5), ("claude-fable-5-1", 3), ("claude-sonnet-5", 2), ("claude-haiku-4-5-20251001", 1)]
CODEX_MODELS = ["gpt-5.6-sol", "gpt-6-astra"]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def pick_model():
    return random.choices([m for m, _ in CLAUDE_MODELS], [w for _, w in CLAUDE_MODELS])[0]


def session_starts():
    starts = []
    for d in range(60, -1, -1):
        day = NOW - dt.timedelta(days=d)
        weight = 1 + (60 - d) / 24
        for _ in range(random.choices([0, 1, 2, 3, 4], [2, 3, 3, 2, 1 * weight])[0] + (1 if d < 7 else 0)):
            t = day.replace(hour=random.randint(8, 21), minute=random.randint(0, 59), second=random.randint(0, 59))
            if t < NOW - dt.timedelta(minutes=20):
                starts.append(t)
    starts += [NOW - dt.timedelta(minutes=m) for m in (95, 40)]
    return sorted(starts)


def turns(start, ctx, model, cap=900_000):
    t, rows = start, []
    for i in range(random.randint(2, 14)):
        t += dt.timedelta(seconds=random.randint(4, 40))
        if ctx > cap:
            ctx = int(cap * random.uniform(0.2, 0.35))
            miss = True
        else:
            miss = i > 0 and ctx > 120_000 and random.random() < 0.05
        fresh = ctx if miss else random.randint(800, 18_000)
        cached = random.randint(1000, 4000) if miss else ctx
        out = random.randint(120, 3200)
        rows.append((t, 2 if i else random.randint(3, 40), cached, fresh, out, int(out * random.uniform(0.1, 0.5)), model))
        ctx = cached + fresh + out
    return rows, ctx, t


def write_claude(root):
    for start in session_starts():
        sid = str(uuid.uuid4())
        cwd = random.choice(PROJECTS)
        model = pick_model()
        ctx = random.randint(18_000, 60_000)
        lines, t = [], start
        for _ in range(random.randint(1, 5)):
            pid = str(uuid.uuid4())
            lines.append({"type": "user", "promptId": pid, "timestamp": iso(t), "sessionId": sid, "cwd": cwd, "message": {"role": "user", "content": random.choice(PROMPTS)}})
            rows, ctx, t = turns(t, ctx, model)
            for (ts, inp, cr, cw, out, think, m) in rows:
                lines.append({"type": "assistant", "timestamp": iso(ts), "sessionId": sid, "cwd": cwd, "isSidechain": False, "message": {"id": "msg_" + uuid.uuid4().hex[:20], "model": m, "usage": {
                    "input_tokens": inp, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw, "output_tokens": out,
                    "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": cw}, "output_tokens_details": {"thinking_tokens": think}}}})
            t += dt.timedelta(minutes=random.randint(1, 25))
            if t > NOW:
                break
        d = os.path.join(root, "claude", "projects", cwd.replace("/", "-"))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "w") as f:
            f.write("\n".join(json.dumps(l) for l in lines) + "\n")


def write_codex(root):
    last = None
    for start in session_starts()[::3]:
        sid = str(uuid.uuid4())
        cwd = random.choice(PROJECTS)
        model = random.choice(CODEX_MODELS)
        ctx = random.randint(12_000, 40_000)
        lines, t = [{"type": "session_meta", "timestamp": iso(start), "payload": {"id": sid, "cwd": cwd}}], start
        for _ in range(random.randint(1, 3)):
            lines.append({"type": "turn_context", "timestamp": iso(t), "payload": {"turn_id": str(uuid.uuid4()), "model": model}})
            lines.append({"type": "response_item", "timestamp": iso(t), "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": random.choice(PROMPTS)}]}})
            rows, ctx, t = turns(t, ctx, model, 220_000)
            for (ts, inp, cr, cw, out, think, m) in rows:
                lines.append({"type": "token_usage_record", "timestamp": iso(ts), "payload": {"usage": {"input_tokens": inp + cr + cw, "cached_input_tokens": cr, "cache_write_input_tokens": 0, "output_tokens": out, "reasoning_output_tokens": think}}})
            t += dt.timedelta(minutes=random.randint(2, 20))
        last = max(last or t, t)
        lines.append({"type": "event_msg", "timestamp": iso(min(t, NOW - dt.timedelta(minutes=50))), "payload": {"type": "token_count", "info": {"model_context_window": 258400}, "rate_limits": {"plan_type": "plus",
            "primary": {"used_percent": 81.0, "window_minutes": 300, "resets_at": int((NOW + dt.timedelta(hours=1.4)).timestamp())},
            "secondary": {"used_percent": 24.0, "window_minutes": 10080, "resets_at": int((NOW + dt.timedelta(days=3.2)).timestamp())}}}})
        day = start.strftime("%Y/%m/%d")
        d = os.path.join(root, "codex", "sessions", day)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"rollout-{start.strftime('%Y-%m-%dT%H-%M-%S')}-{sid}.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(l) for l in lines) + "\n")


def write_copilot(root):
    os.makedirs(os.path.join(root, "copilot"), exist_ok=True)
    path = os.path.join(root, "copilot", "session-store.db")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.executescript("""create table sessions(id text, cwd text);
create table turns(session_id text, turn_index int, user_message text, timestamp text);
create table assistant_usage_events(session_id text, model text, input_tokens int, output_tokens int, cache_read_tokens int, cache_write_tokens int, reasoning_tokens int, agent_id text, created_at text);""")
    for start in session_starts()[1::4]:
        sid = str(uuid.uuid4())
        con.execute("insert into sessions values (?, ?)", (sid, random.choice(PROJECTS)))
        ctx, t = random.randint(15_000, 50_000), start
        for idx in range(random.randint(1, 3)):
            con.execute("insert into turns values (?, ?, ?, ?)", (sid, idx, random.choice(PROMPTS), t.strftime("%Y-%m-%d %H:%M:%S")))
            rows, ctx, t = turns(t, ctx, "gpt-5.5", 230_000)
            for (ts, inp, cr, cw, out, think, m) in rows:
                con.execute("insert into assistant_usage_events values (?, ?, ?, ?, ?, ?, ?, ?, ?)", (sid, m, inp + cr + cw, out, cr, 0, think, None, iso(ts)))
            t += dt.timedelta(minutes=random.randint(2, 20))
    con.commit()
    con.close()


os.makedirs(OUT, exist_ok=True)
write_claude(OUT)
write_codex(OUT)
write_copilot(OUT)
os.makedirs(os.path.join(OUT, "tokenmeter"), exist_ok=True)
with open(os.path.join(OUT, "tokenmeter", "config.json"), "w") as f:
    json.dump({"_plans": {"claude": 100, "codex": 20}}, f)
print(f"demo data written to {OUT}")
print(f"CLAUDE_CONFIG_DIR={OUT}/claude CODEX_HOME={OUT}/codex COPILOT_DB={OUT}/copilot/session-store.db TOKENMETER_DIR={OUT}/tokenmeter python3 -m tokenmeter --port 7801 --user demo")
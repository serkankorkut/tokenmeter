import json
import os
import sys
import tempfile

sys.argv = ["test"]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tokenmeter import server

CLAUDE_LINES = [
    {"type": "user", "promptId": "p1", "timestamp": "2026-09-20T10:00:00Z", "sessionId": "s1", "cwd": "/w", "message": {"role": "user", "content": "hi"}},
    {"type": "user", "promptId": "p1", "timestamp": "2026-09-20T10:00:05Z", "sessionId": "s1", "message": {"role": "user", "content": [{"type": "tool_result"}]}},
    {"type": "user", "promptId": "p2", "timestamp": "2026-09-20T10:00:06Z", "sessionId": "s1", "message": {"role": "user", "content": [{"type": "tool_result"}]}},
    {"type": "assistant", "timestamp": "2026-09-20T10:00:01Z", "sessionId": "s1", "cwd": "/w", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50, "output_tokens": 5, "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 30}}}},
    {"type": "assistant", "timestamp": "2026-09-20T10:00:02Z", "sessionId": "s1", "cwd": "/w", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50, "output_tokens": 40, "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 30}}}},
    {"type": "assistant", "timestamp": "2026-09-20T10:00:03Z", "sessionId": "s1", "message": {"id": "m2", "model": "<synthetic>", "usage": {"input_tokens": 1, "output_tokens": 1}}},
]
CODEX_NEW = [
    {"type": "session_meta", "timestamp": "2026-09-20T11:00:00Z", "payload": {"id": "c1", "cwd": "/x"}},
    {"type": "turn_context", "timestamp": "2026-09-20T11:00:01Z", "payload": {"model": "gpt-6-astra", "turn_id": "t1"}},
    {"type": "response_item", "timestamp": "2026-09-20T11:00:01Z", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context/>"}, {"type": "input_text", "text": "fix the bug"}]}},
    {"type": "event_msg", "timestamp": "2026-09-20T11:00:02Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 999, "cached_input_tokens": 0, "output_tokens": 999}}}},
    {"type": "token_usage_record", "timestamp": "2026-09-20T11:00:02Z", "payload": {"usage": {"input_tokens": 300, "cached_input_tokens": 200, "cache_write_input_tokens": 0, "output_tokens": 20, "reasoning_output_tokens": 7}}},
]
CODEX_OLD = [
    {"type": "session_meta", "timestamp": "2026-08-01T11:00:00Z", "payload": {"id": "c2", "cwd": "/y"}},
    {"type": "event_msg", "timestamp": "2026-08-01T11:00:02Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}, "model_context_window": 258400}, "rate_limits": {"plan_type": "plus", "primary": {"used_percent": 42, "window_minutes": 300, "resets_at": 1}, "secondary": None}}},
    {"type": "event_msg", "timestamp": "2026-08-01T11:00:03Z", "payload": {"type": "token_count", "info": None}},
]


def write(lines):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("\n".join(json.dumps(l) for l in lines) + "\n")
    f.close()
    return f.name


recs, prompts, _ = server.parse_claude(write(CLAUDE_LINES))
assert len(prompts) == 1 and prompts[0]["text"] == "hi" and prompts[0]["id"] == "p1", prompts
assert len(recs) == 1, recs
r = recs[0]
assert (r["in"], r["cr"], r["cw5"], r["cw1h"], r["out"]) == (10, 100, 20, 30, 40), r
assert abs(server.cost_of(r) - (10 * 5 + 100 * 0.5 + 20 * 6.25 + 30 * 10 + 40 * 25) / 1e6) < 1e-9

recs, prompts, meta = server.parse_codex(write(CODEX_NEW))
assert len(recs) == 1 and len(prompts) == 1, (recs, prompts)
assert prompts[0]["text"] == "fix the bug" and prompts[0]["id"] == "t1", prompts
assert (recs[0]["in"], recs[0]["cr"], recs[0]["out"], recs[0]["reason"]) == (100, 200, 20, 7), recs
assert recs[0]["model"] == "gpt-6-astra" and recs[0]["project"] == "/x"
assert abs(server.cost_of(recs[0]) - (100 * 10 + 200 * 1 + 20 * 50) / 1e6) < 1e-9

recs, _, meta = server.parse_codex(write(CODEX_OLD))
assert meta["limits"]["windows"][0]["used_percent"] == 42 and meta["ctx"] == 258400, meta
assert len(recs) == 1 and (recs[0]["in"], recs[0]["cr"]) == (60, 40), recs

import sqlite3
db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
con = sqlite3.connect(db)
con.executescript("""create table sessions(id text, cwd text); create table turns(session_id text, turn_index int, user_message text, timestamp text);
create table assistant_usage_events(session_id text, model text, input_tokens int, output_tokens int, cache_read_tokens int, cache_write_tokens int, reasoning_tokens int, agent_id text, created_at text);
insert into sessions values('s9','/cp'); insert into turns values('s9',0,'make it fast','2026-08-21 12:00:00');
insert into assistant_usage_events values('s9','gpt-5.5',1000,50,900,0,10,null,'2026-08-21T12:00:05.000Z');""")
con.commit(); con.close()
recs, prompts, _ = server.parse_copilot(db)
assert (recs[0]["in"], recs[0]["cr"], recs[0]["out"], recs[0]["project"], recs[0]["tool"]) == (100, 900, 50, "/cp", "copilot"), recs
assert prompts[0]["text"] == "make it fast" and prompts[0]["ts"] == "2026-08-21T12:00:00Z", prompts
assert server.price_for("gpt-5.5-cyber")["output"] == 75 and server.price_for("gpt-5.5")["output"] == 30
assert server.longest_prefix(server.CONTEXT_WINDOWS, "claude-haiku-4-5") == 200000
assert server.price_for("claude-haiku-4-5-20251001")["output"] == 5
assert server.price_for("claude-fable-5-1")["cache_read"] == 0.25
assert server.price_for("claude-fable-5")["cache_read"] == 1
assert server.price_for("claude-opus-5-5")["output"] == 20 and server.price_for("claude-opus-5")["output"] == 25
short = server.rec("t", "codex", "gpt-6-sol", "/p", "s", 1000, 100000, 0, 0, 1000, 0)
long = server.rec("t", "codex", "gpt-6-sol", "/p", "s", 1000, 300000, 0, 0, 1000, 0)
assert abs(server.cost_of(short) - (1000 * 2 + 100000 * 0.2 + 1000 * 10) / 1e6) < 1e-9, server.cost_of(short)
assert abs(server.cost_of(long) - (1000 * 4 + 300000 * 0.4 + 1000 * 15) / 1e6) < 1e-9, server.cost_of(long)
assert server.price_for("gpt-6-luna")["output"] == 0.5 and server.price_for("gpt-6-astra-2026")["input"] == 10
import socket
blocker = socket.socket(); blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); blocker.bind(("0.0.0.0", 0)); blocker.listen()
busy_port = blocker.getsockname()[1]
got, srv = server.bind("127.0.0.1", [busy_port, busy_port + 1, busy_port + 2])
assert got in (busy_port + 1, busy_port + 2) and srv, got
srv.server_close(); blocker.close()
assert server.ports_to_try("9000") == [9000] and len(server.ports_to_try()) == 11 or server.PORT_SET
print("ok")
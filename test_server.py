import json
import os
import sys
import tempfile

sys.argv = ["test"]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server

CLAUDE_LINES = [
    {"type": "user", "promptId": "p1", "timestamp": "2026-09-20T10:00:00Z", "sessionId": "s1", "cwd": "/w", "message": {"role": "user", "content": "hi"}},
    {"type": "user", "timestamp": "2026-09-20T10:00:05Z", "sessionId": "s1", "message": {"role": "user", "content": [{"type": "tool_result"}]}},
    {"type": "assistant", "timestamp": "2026-09-20T10:00:01Z", "sessionId": "s1", "cwd": "/w", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50, "output_tokens": 5, "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 30}}}},
    {"type": "assistant", "timestamp": "2026-09-20T10:00:02Z", "sessionId": "s1", "cwd": "/w", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50, "output_tokens": 40, "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 30}}}},
    {"type": "assistant", "timestamp": "2026-09-20T10:00:03Z", "sessionId": "s1", "message": {"id": "m2", "model": "<synthetic>", "usage": {"input_tokens": 1, "output_tokens": 1}}},
]
CODEX_NEW = [
    {"type": "session_meta", "timestamp": "2026-09-20T11:00:00Z", "payload": {"id": "c1", "cwd": "/x"}},
    {"type": "turn_context", "timestamp": "2026-09-20T11:00:01Z", "payload": {"model": "gpt-6-astra"}},
    {"type": "event_msg", "timestamp": "2026-09-20T11:00:02Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 999, "cached_input_tokens": 0, "output_tokens": 999}}}},
    {"type": "token_usage_record", "timestamp": "2026-09-20T11:00:02Z", "payload": {"usage": {"input_tokens": 300, "cached_input_tokens": 200, "cache_write_input_tokens": 0, "output_tokens": 20, "reasoning_output_tokens": 7}}},
]
CODEX_OLD = [
    {"type": "session_meta", "timestamp": "2026-08-01T11:00:00Z", "payload": {"id": "c2", "cwd": "/y"}},
    {"type": "event_msg", "timestamp": "2026-08-01T11:00:02Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}}}},
    {"type": "event_msg", "timestamp": "2026-08-01T11:00:03Z", "payload": {"type": "token_count", "info": None}},
]


def write(lines):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("\n".join(json.dumps(l) for l in lines) + "\n")
    f.close()
    return f.name


recs, prompts = server.parse_claude(write(CLAUDE_LINES))
assert len(prompts) == 1, prompts
assert len(recs) == 1, recs
r = recs[0]
assert (r["in"], r["cr"], r["cw5"], r["cw1h"], r["out"]) == (10, 100, 20, 30, 40), r
assert abs(server.cost_of(r) - (10 * 5 + 100 * 0.5 + 20 * 6.25 + 30 * 10 + 40 * 25) / 1e6) < 1e-9

recs, prompts = server.parse_codex(write(CODEX_NEW))
assert len(recs) == 1 and len(prompts) == 1, (recs, prompts)
assert (recs[0]["in"], recs[0]["cr"], recs[0]["out"], recs[0]["reason"]) == (100, 200, 20, 7), recs
assert recs[0]["model"] == "gpt-6-astra" and recs[0]["project"] == "/x"
assert server.cost_of(recs[0]) is None

recs, _ = server.parse_codex(write(CODEX_OLD))
assert len(recs) == 1 and (recs[0]["in"], recs[0]["cr"]) == (60, 40), recs

assert server.price_for("claude-haiku-4-5-20251001")["output"] == 5
assert server.price_for("claude-fable-5-1")["cache_read"] == 0.25
assert server.price_for("claude-fable-5")["cache_read"] == 1
print("ok")
---
name: tokenmeter
description: Open the Tokenmeter dashboard, a local web page that tracks token usage, cost, rate-limit windows and cache misses for every prompt in Claude Code, Codex and Copilot CLI. Use when the user asks about token usage, token spend, cost per prompt or per commit, cache hit rate, usage limits or 5-hour window, usage per project or model, a usage dashboard, or says "tokenmeter", "how many tokens", "how much am I spending", "show usage", "open the dashboard".
---

# Tokenmeter

Tokenmeter reads the transcripts Claude Code, Codex and Copilot CLI already write to disk, so no hook or instrumentation is needed. Every completed model turn shows up in the dashboard within a few seconds.

## Start the dashboard

Run the server in the background (it is safe to run repeatedly, a second start just reports the existing URL). Try these in order and use the first that exists:

```bash
(command -v tokenmeter && nohup tokenmeter --open >/dev/null 2>&1 &) || (nohup python3 ~/.claude/skills/tokenmeter/tokenmeter/server.py --open >/dev/null 2>&1 &) || (nohup python3 ~/.codex/skills/tokenmeter/tokenmeter/server.py --open >/dev/null 2>&1 &)
```

The `tokenmeter` command exists when installed with pip, pipx, uv or Homebrew. The two paths are the plugin checkouts for Claude Code and Codex.

Then tell the user the dashboard is at http://127.0.0.1:7788 and stop. Do not paste usage numbers into chat unless asked; the dashboard is the deliverable.

## Answer a usage question directly

If the user asks a specific question ("how much did I spend today", "which project uses the most tokens", "am I close to my limit"), start the server as above, then read `http://127.0.0.1:7788/api/summary` for today, last 5 hours, month, projection and limits, or `http://127.0.0.1:7788/api/usage` for every turn, and answer from the JSON. Records carry `tool`, `model`, `project`, `ts`, token fields `in`, `cr` (cache read), `cw5`/`cw1h` (cache write), `out`, `reason`, and `cost` in USD (null when the model has no entry in `pricing.json`).

## Configuration

- `TOKENMETER_PORT` or `--port N` changes the port.
- `pricing.json` inside the `tokenmeter` package holds USD per million tokens by model-id prefix, plus `_plans` (what the user pays), `_budget` (alert caps) and `_context_windows`.
- `--export URL` pushes aggregates to a team server; `--host 0.0.0.0` runs one.
- `CLAUDE_CONFIG_DIR` and `CODEX_HOME` override the transcript locations.
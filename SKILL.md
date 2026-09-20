---
name: tokenmeter
description: Open the Tokenmeter dashboard, a local web page that tracks token usage and estimated cost for every prompt in Claude Code and Codex. Use when the user asks about token usage, token spend, cost per prompt, cache hit rate, usage per project or model, a usage dashboard, or says "tokenmeter", "how many tokens", "how much am I spending", "show usage", "open the dashboard".
---

# Tokenmeter

Tokenmeter reads the transcripts Claude Code and Codex already write to disk, so no hook or instrumentation is needed. Every completed model turn shows up in the dashboard within a few seconds.

## Start the dashboard

Run the server in the background (it is safe to run repeatedly, a second start just reports the existing URL):

```bash
nohup python3 ~/.claude/skills/tokenmeter/server.py --open >/dev/null 2>&1 &
```

If that path does not exist, use `~/.codex/skills/tokenmeter/server.py` instead. Both point at the same install.

Then tell the user the dashboard is at http://127.0.0.1:7788 and stop. Do not paste usage numbers into chat unless asked; the dashboard is the deliverable.

## Answer a usage question directly

If the user asks a specific question ("how much did I spend today", "which project uses the most tokens"), start the server as above, then read `http://127.0.0.1:7788/api/usage` with curl and answer from the JSON. Records carry `tool`, `model`, `project`, `ts`, token fields `in`, `cr` (cache read), `cw5`/`cw1h` (cache write), `out`, `reason`, and `cost` in USD (null when the model has no entry in `pricing.json`).

## Configuration

- `TOKENMETER_PORT` or `--port N` changes the port.
- `pricing.json` next to `server.py` holds USD per million tokens by model-id prefix. Add a prefix to price a new model.
- `CLAUDE_CONFIG_DIR` and `CODEX_HOME` override the transcript locations.
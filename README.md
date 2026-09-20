# Tokenmeter

![Tokenmeter demo](docs/demo.gif)

A local dashboard that shows token usage and estimated cost for every prompt you send in **Claude Code** and **Codex**. Zero dependencies: one Python file, one HTML file, nothing leaves your machine.

## What you get

- Live feed of every model turn, updated a few seconds after each prompt finishes
- Totals, estimated API-equivalent cost, prompt count, cache hit rate, and period-over-period deltas
- Usage over time by tool (hourly today, daily otherwise), with a table view for accessibility
- Token mix: fresh input, cache reads, cache writes, output and thinking
- Breakdown by model, project and session
- Filters for time range, tool, project and model, plus CSV export
- Light and dark themes

## How it works

Nothing is installed inside Claude Code or Codex. Both tools already save every conversation to a log file on your disk, and each model reply in that log includes how many tokens it used. Tokenmeter just reads those logs.

1. Claude Code saves logs in `~/.claude/projects/`. Codex saves them in `~/.codex/sessions/`.
2. `server.py` reads every log once, pulls out each prompt and each model reply with its token counts, and keeps them in memory.
3. It multiplies tokens by the prices in `pricing.json` to estimate cost.
4. It serves a web page at `http://127.0.0.1:7788`. The page asks the server every 4 seconds if anything changed and redraws when it has.

When you send a new prompt, the tool appends to its log, Tokenmeter notices the file grew, re-reads that one file, and the new turn shows up. Only your machine is involved. Nothing is sent anywhere.

The `/tokenmeter` skill is just a shortcut that starts `server.py` and gives you the link.

## Install

```bash
git clone https://github.com/serkankorkut/tokenmeter ~/repo/tokenmeter
~/repo/tokenmeter/install.sh
```

The installer symlinks the plugin into `~/.claude/skills/tokenmeter` (auto-loads in Claude Code as `tokenmeter@skills-dir`) and `~/.codex/skills/tokenmeter` (Codex skill), and puts a `tokenmeter` command in `~/.local/bin`.

Then in either tool:

```
/tokenmeter
```

or from a shell:

```bash
tokenmeter --open
```

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `TOKENMETER_PORT` / `--port` | `7788` | Listen port (always bound to 127.0.0.1) |
| `CLAUDE_CONFIG_DIR` | `~/.claude` | Where Claude Code keeps transcripts |
| `CODEX_HOME` | `~/.codex` | Where Codex keeps sessions |
| `pricing.json` | Anthropic list prices | USD per million tokens by model-id prefix |

Codex models ship unpriced. Add a prefix like `"gpt-6": {...}` to `pricing.json` with your plan's rates to include them in cost totals.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/usage` | All records, prompts, and metadata as JSON |
| `GET /api/version` | Cheap change token, polled by the UI |
| `GET /api/export.csv?since=ISO` | CSV of records |
| `GET /api/health` | `{"ok": true, "app": "tokenmeter"}` |

## Development

```bash
python3 test_server.py
python3 server.py --open
```

## Roadmap

- Budget alerts (daily or weekly cap with a desktop notification)
- Per-team roll-ups by shipping an optional exporter to a shared endpoint
- Menu-bar widget showing today's spend
- Support for more agents that write local transcripts (Gemini CLI, Cursor agent)

## License

MIT
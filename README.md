# Tokenmeter

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

Claude Code writes a JSONL transcript per session under `~/.claude/projects`, and Codex writes rollouts under `~/.codex/sessions`. Both include per-turn `usage` blocks. Tokenmeter tails those files, dedupes streamed message chunks, normalizes both formats into one record shape, prices them with `pricing.json`, and serves the result at `http://127.0.0.1:7788`. No hooks, no wrappers, no telemetry.

Files are re-read only when their size or mtime changes, so the first index takes about a second and every refresh after that is instant.

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
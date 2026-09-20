# Tokenmeter

![Tokenmeter demo](docs/demo.gif)

A local dashboard that shows token usage and estimated cost for every prompt you send in **Claude Code** and **Codex**. Zero dependencies: one Python file, one HTML file, nothing leaves your machine.

## What you get

- Live feed of every model turn from **Claude Code**, **Codex** and **GitHub Copilot CLI**, updated a few seconds after each prompt finishes
- Spend tile that shows what you actually pay first (your subscription, prorated to the range) with the API-equivalent cost underneath, or the API cost on top if you have no plan configured
- Usage limits: Codex 5-hour and weekly windows as Codex reports them, plus rolling 5-hour and 7-day usage for every tool
- Active sessions with a context-fill gauge, so you see compaction coming
- Every prompt with its text, the turns it triggered, tokens, cost and duration, plus a resume command. Click any header to sort by date, tokens, cost, turns or duration
- Cache-miss detector: turns where the cached prefix collapsed and had to be re-written, with the prompt that was in progress and what the re-write cost
- Most expensive prompts, cost per git commit, cost mix by token type, and breakdowns by model, project and session
- Budget alerts: set a daily or monthly cap and get a desktop notification when you cross it
- Team mode: teammates export daily aggregates to one shared Tokenmeter and you filter by person
- Menu bar widget for SwiftBar or xbar showing today's spend
- Filters for time range, tool, project, model and user, kept in the URL so views are bookmarkable, plus CSV export and light and dark themes

## How it works

Nothing is installed inside Claude Code or Codex. Both tools already save every conversation to a log file on your disk, and each model reply in that log includes how many tokens it used. Tokenmeter just reads those logs.

1. Claude Code saves logs in `~/.claude/projects/`, Codex in `~/.codex/sessions/`, Copilot CLI in `~/.copilot/session-store.db`.
2. `server.py` reads every log once, pulls out each prompt and each model reply with its token counts, and keeps them in memory.
3. It multiplies tokens by the prices in `pricing.json` to estimate cost.
4. It serves a web page at `http://127.0.0.1:7788`. The page asks the server every 4 seconds if anything changed and redraws when it has.

When you send a new prompt, the tool appends to its log, Tokenmeter notices the file grew, re-reads that one file, and the new turn shows up. Only your machine is involved. Nothing is sent anywhere.

The `/tokenmeter` skill is just a shortcut that starts `server.py` and gives you the link.

## Install

Any machine with Python 3.9 or newer. Pick one:

```bash
brew install serkankorkut/tap/tokenmeter
```

```bash
pipx install tokenmeter-dashboard
```

```bash
uvx tokenmeter-dashboard
```

Or, as a Claude Code plugin straight from GitHub:

```bash
claude plugin marketplace add serkankorkut/tokenmeter
claude plugin install tokenmeter@tokenmeter
```

Or clone and link, which also installs the Codex skill and the `tokenmeter` command:

```bash
git clone https://github.com/serkankorkut/tokenmeter ~/repo/tokenmeter
~/repo/tokenmeter/install.sh
```

With Homebrew you can keep it running in the background: `brew services start tokenmeter`.

Then in either tool:

```
/tokenmeter
```

or from a shell:

```bash
tokenmeter --open
```

## Configuration

Everything lives in `pricing.json` next to `server.py`:

| Key | Purpose |
|---|---|
| model prefixes | USD per million tokens: input, cache_read, cache_write_5m, cache_write_1h, output. Anthropic and OpenAI list prices are included |
| `_plans` | What you pay per month per tool. Drives the Subscription spend tile |
| `_budget` | `daily` and `monthly` caps in API-equivalent USD. Desktop notification once per period when exceeded |
| `_context_windows` | Context size by model prefix, for the context-fill gauge |

Environment and flags:

| Setting | Default | Purpose |
|---|---|---|
| `TOKENMETER_PORT` / `--port` | `7788` | Listen port |
| `--host` | `127.0.0.1` | Bind address. Use `0.0.0.0` only for a team server |
| `--open` | | Open the browser after starting |
| `--user NAME` | your login | Name shown in team mode |
| `--export URL` | | Push your last 30 days to a team server every hour. Prompt text is never sent |
| `TOKENMETER_TOKEN` | | Shared secret for team ingest, sent as `X-Tokenmeter-Token` |
| `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `COPILOT_DB` | `~/.claude`, `~/.codex`, `~/.copilot/session-store.db` | Where each tool keeps its logs |
| `TOKENMETER_DIR` | `~/.tokenmeter` | Where team data is stored |

### What "% of tokens" means

In the model, project and session tables it is that row's share of all tokens in the current filter. It always sums to 100 percent across a table.

### Limits

Codex writes its 5-hour and weekly quota usage into every session log, so Tokenmeter shows the real percentages and reset times, as of the last Codex turn. Anthropic does not write Claude plan usage to disk. If a Claude Code OAuth token is present in the macOS keychain Tokenmeter queries the usage endpoint; otherwise it shows rolling 5-hour and 7-day totals from the logs.

### Team mode

On a shared machine: `tokenmeter --host 0.0.0.0` with `TOKENMETER_TOKEN` set. On each laptop: `tokenmeter --export http://that-host:7788` with the same token. The shared dashboard gains a user filter. Only token counts, models, project paths and timestamps travel; prompt text stays local.

### Menu bar

Copy `menubar/tokenmeter.1m.sh` into your SwiftBar or xbar plugin folder. It shows today's spend and, on click, the 5-hour and monthly numbers.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/usage` | All records, prompts, and metadata as JSON |
| `GET /api/version` | Cheap change token, polled by the UI |
| `GET /api/export.csv?since=ISO` | CSV of records |
| `GET /api/summary` | Today, last 5 hours, month, projection, limits. Used by the menu bar widget |
| `GET /api/commits` | Recent commits per repo, for cost-per-commit |
| `POST /api/ingest` | Team mode receiver |
| `GET /api/health` | `{"ok": true, "app": "tokenmeter"}` |

## Development

```bash
python3 test_server.py
python3 -m tokenmeter --open
```

Release: bump the version in `pyproject.toml` and `tokenmeter/__init__.py`, tag `vX.Y.Z` and push. The GitHub Action publishes to PyPI via trusted publishing. Then regenerate the Homebrew formula with `release/brew-formula.sh > ../homebrew-tap/Formula/tokenmeter.rb`.

## Roadmap

- Gemini CLI, Cursor agent and OpenCode parsers once their transcript formats are pinned down
- Slack or email weekly digest
- Windows notification support for budget alerts

## License

MIT
# Tokenmeter: context for agents

Read this before changing anything. It records what exists, where it lives, how it ships, and the owner's rules. Last updated 2026-09-27, at version 0.2.2 on PyPI and Homebrew, with unreleased changes in the working tree.

## What it is

A local web dashboard showing token usage, cost, cache misses and rate-limit windows for every prompt in Claude Code, Codex and GitHub Copilot CLI. It reads the logs those tools already write to disk. No hooks, no instrumentation, nothing sent anywhere. Python 3.9+ standard library only, plus one HTML file. The owner, Serkan Korkut, wants it to become a publishable, pitchable product.

## Repositories

| Path | Remote | Visibility | Role |
|---|---|---|---|
| `~/repo/tokenmeter` | `serkankorkut/tokenmeter` | private | the app, this repo |
| `~/repo/homebrew-tap` | `serkankorkut/homebrew-tap` | public | Homebrew formula, public README, demo GIF, release tarballs |
| `~/repo/tokenmeter-site` | none, not a git repo yet | local | marketing and docs site for Cloudflare Workers |
| `~/repo/serkan.fyi` | private | | owner's personal site; tokenmeter-site copies its build setup and style |

Because this repo is private, anything the public must see (README image, install docs) lives in or points at the public tap repo. The PyPI README image URL is `https://raw.githubusercontent.com/serkankorkut/homebrew-tap/main/docs/demo.gif` for that reason. Do not link the private repo from public surfaces expecting it to load.

## Layout of this repo

- `tokenmeter/server.py` — everything server side: parsers, store, HTTP handler, budget and export threads, CLI. About 500 lines.
- `tokenmeter/index.html` — the whole dashboard, vanilla JS and inline CSS. About 600 lines.
- `tokenmeter/pricing.json` — bundled list prices per model prefix plus `_plans`, `_budget`, `_context_windows`. `_plans` ships as zeros on purpose.
- `tokenmeter/__init__.py`, `__main__.py` — package glue; `__version__` lives in `server.py`.
- `test_server.py` — the single assert-based self-check. Run `python3 test_server.py`, expect `ok`.
- `SKILL.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `install.sh` — Claude Code plugin and Codex skill packaging. The owner asked not to promote the skill publicly for now.
- `menubar/tokenmeter.1m.sh` — SwiftBar/xbar plugin reading `/api/summary`. Not included in the PyPI package.
- `release/brew-formula.sh`, `release/brew-stats.sh` — Homebrew release and download stats.
- `.github/workflows/publish.yml` — publishes to PyPI on any `v*` tag via trusted publishing, environment `pypi`.
- `docs/demo.gif` — also copied to the tap repo, which is where the public README reads it from.
- `release/demo_data.py` — writes a synthetic 60-day dataset for Claude Code, Codex and Copilot. All marketing images come from a Tokenmeter instance running on it. Never capture screenshots or GIFs from the owner's real data: it contains employer repo names, PR links, ticket keys and colleagues' names. A GIF made from real data was public for a week and had to be replaced on 2026-09-27; it still exists in the tap repo's git history.

## How the data flows

1. `Store.sources()` yields Claude JSONL under `~/.claude/projects/**`, Codex JSONL under `~/.codex/sessions/**`, the Copilot SQLite at `~/.copilot/session-store.db`, and team files under `~/.tokenmeter/team/*.json`.
2. A background thread (`Store.scan_loop`) runs `Store.scan()` every 3 s; request handlers never scan. The server answers immediately at startup and `/api/version` reports `indexing`, `done` and `total` so the page can show progress. `scan()` re-parses a source only when its mtime or size changed, parses outside the lock, and swaps results in under it. Large histories exist: one user has 108k turns in 1,915 files and a 67 s first index. Claude tool-result lines are skipped before `json.loads`. `/api/usage` is serialized once per data version and cached.
3. Each parser returns `(records, prompts, meta)`. A record is one model turn: `ts, tool, model, project, session, in, cr, cw5, cw1h, out, reason, sub, user, cost`. `in` is uncached input, `cr` cache read, `cw5`/`cw1h` cache writes, `out` output including thinking, `reason` thinking only.
4. `Store.records()` dedupes across files, because resumed sessions copy history into new files. Record key `(ts, session, out, cr, user)`, prompt key `(id, user)`.
5. The page polls `/api/version` every 4 s and refetches `/api/usage` only when it changes. All filtering, grouping and sorting happens in the browser.

Parser specifics worth knowing:

- Claude streams one message as several lines with the same `message.id`; the last one wins. Models starting with `<` are synthetic and skipped. A prompt is a `type: user` line with a `promptId` whose content is a string or text blocks without `tool_result`.
- Codex has two formats. Newer logs carry `token_usage_record` and those are used; older ones only `event_msg` of type `token_count`, used as a fallback. Codex `input_tokens` includes cached tokens, so `in = input - cached`. `rate_limits` in `token_count` events feed the Codex limits card. User text is the first `input_text` that does not start with `<`.
- Copilot stores `input_tokens` including cache reads, same subtraction. Timestamps without `T` are converted to ISO.

## Cost

`cost = in × input + cr × cache_read + cw5 × cache_write_5m + cw1h × cache_write_1h + out × output`, per million tokens, from the longest matching model prefix in pricing. Claude Code writes cache at the 1-hour rate. OpenAI entries have zero cache-write prices. Unknown models get `cost: null` and are shown as unpriced, never as zero.

The UI splits tokens into Cached (`cr`), Fresh (`in + cw5 + cw1h`) and Output (`out`), because cache reads dominate token counts while cache writes dominate cost. The owner asked for this explicitly after noticing token totals and costs did not line up; keep the split and the per-prompt arithmetic shown in expanded rows.

Spend tile rule, owner's explicit request: if `_plans` has a nonzero price for the filtered tools, show the prorated subscription price on top and API-equivalent smaller below; otherwise show API-equivalent on top. Never show a plan the user did not configure.

## Configuration

`~/.tokenmeter/config.json` is merged over the bundled `pricing.json` at startup: dict values merge one level deep, others replace. This machine has `{"_plans": {"claude": 100, "codex": 20}}`. Do not put personal plan values back into the bundled file.

## Release process

1. Bump the version in `pyproject.toml`, `__version__` in `tokenmeter/server.py`, and `.claude-plugin/plugin.json`.
2. Run `python3 test_server.py`.
3. Commit, `git tag -a vX.Y.Z -m vX.Y.Z`, push the branch and the tag. The Action publishes to PyPI in about a minute. Poll `https://pypi.org/pypi/tokenmeter-dashboard/json` until the version shows.
4. `release/brew-formula.sh X.Y.Z > ../homebrew-tap/Formula/tokenmeter.rb`. The script downloads the PyPI sdist, checks its sha256, uploads it to a GitHub Release `vX.Y.Z` on the tap repo, and prints a formula pointing at that asset.
5. Commit and push the tap. Verify with `brew update && brew upgrade tokenmeter && tokenmeter --version` and `brew audit --strict serkankorkut/tap/tokenmeter`. Keep `desc` under 80 characters or audit fails.

Names: PyPI distribution `tokenmeter-dashboard` (bare `tokenmeter` is taken on PyPI and npm), command `tokenmeter`, tap `serkankorkut/tap`. The uv form is `uvx --from tokenmeter-dashboard tokenmeter`; plain `uvx tokenmeter-dashboard` fails.

Download stats: PyPI at pypistats.org or pepy.tech. Homebrew via `release/brew-stats.sh`, which reads download counts of the tap's release assets. Homebrew has no analytics for taps; routing the formula through release assets is how installs are counted.

## Demo data and marketing images

```bash
python3 release/demo_data.py /some/tmp/demo
CLAUDE_CONFIG_DIR=/some/tmp/demo/claude CODEX_HOME=/some/tmp/demo/codex COPILOT_DB=/some/tmp/demo/copilot/session-store.db TOKENMETER_DIR=/some/tmp/demo/tokenmeter python3 -m tokenmeter --port 7801 --user demo
```

Then capture with headless Chrome against port 7801 (`--window-size=1280,860`, `--virtual-time-budget=8000`, `#range=30&theme=light` style hashes) and build the GIF with ffmpeg palettegen. The demo projects are not git repos, so the Cost per commit card is empty in demo shots.

## Feedback and CI

- Issue forms live in the public tap repo: install failure (asks for `brew gist-logs` link and `brew config`), bug (prefilled `version` field), idea. The dashboard footer's Report an issue button links to the bug form with the version prefilled; Contact is `mailto:korkutserkan@outlook.com`.
- `.github/workflows/health.yml` in the tap runs `brew install`, `brew test`, `brew audit --strict --online` and a live HTTP check on Apple Silicon, Intel and Linux, on every push and Monday and Thursday at 06:00 UTC. GitHub emails the owner when a scheduled run fails. Intel builds Python from source and takes much longer than the others.

## Website

`~/repo/tokenmeter-site` is live at https://tokenmeter.fyi and www.tokenmeter.fyi (first deployed 2026-09-28 with the owner's DEPLOY ET). It uses serkan.fyi's build: `build.mjs` turns `src/pages/*.html` plus `src/layout.html` into `public/`, served by Cloudflare Workers static assets. The landing page is modeled on brew.sh's structure: centered hero, one-line install with a copy button and macOS/Windows/Linux switcher (`src/static/site.js`), alternating feature rows with terminal examples, and a footer with Report an issue and Contact buttons. It links only to public places: the tap repo, PyPI and the owner's email. The Claude Code plugin and skill are deliberately not mentioned on public surfaces for now. `npm run dev` for local preview; `npm run deploy` publishes. Domain not chosen, so `wrangler.toml` uses workers.dev and the canonical URL defaults to `tokenmeter.serkan.fyi` in `build.mjs`. Redeploy with `npm run deploy`, only after the owner writes DEPLOY ET.

## Owner's rules

- No code comments unless unavoidable. No trailing whitespace, no double blank lines, no blank line after `{` or before `}`. No newline at end of file, in every file.
- Never commit unless explicitly asked. Commit messages are short and plain, like `feat: Add market finder endpoints`, capital letter after the colon. No `Co-Authored-By`, no mention of Claude or Anthropic in commits or PR bodies.
- Never deploy unless the owner writes "DEPLOY ET" in capitals. Publishing to PyPI or Homebrew has been done on explicit request each time; treat it the same way.
- PR bodies use the repo's pull request template unchanged.
- Prefers the smallest working change, standard library over dependencies, and short explanations.

## Known gaps

- Claude plan limit percentage: Anthropic does not write it to disk. The server tries the OAuth usage endpoint with a keychain token on macOS; on this machine the token is empty, so the card shows rolling 5-hour and 7-day totals.
- Windows is expected to work but has not been run. Budget notifications use `osascript` and are macOS only.
- Model prices: `claude-opus-5-5` was added on 2026-09-27 at $4 input, $5 / $8 cache writes, $0.20 cache read, $20 output. Before that it silently matched the `claude-opus-5` prefix and was overpriced by about 25 percent. When a new model id appears, add its exact prefix; do not rely on a shorter prefix matching.
- The menu bar script is not in the PyPI package, so public users cannot get it.
- Unreleased in this repo's working tree: background indexing and silent handling of closed connections (fixes the Broken pipe tracebacks a user reported on 0.2.2), the `uvx` command fix in `README.md`, the dashboard's Report an issue and Contact buttons, `app_version` in `/api/usage` and `/api/health`, Opus 5.5 pricing, wrapping table headers so Cost stays visible in half-width tables, `release/demo_data.py`, the clean `docs/demo.gif`, and the tap homepage URL in `release/brew-formula.sh`. They reach users only with the next tagged release.
- `tokenmeter-site` is not under version control. Preview with `npm run dev` (it may need `--port 8790 --inspector-port 9239` if another wrangler instance holds the defaults).
- The main repo is private. Making it public would let the README, `git clone` instructions and the plugin marketplace work for others.

## Local processes that may be running

- Port 7788: the dashboard, started from this repo with `python3 -m tokenmeter`, logging to `~/.tokenmeter/server.log`. Homebrew 0.2.2 is also installed; `brew services start tokenmeter` would run that instead.
- Port 8790: `wrangler dev` for the site preview.
- Port 7801: the demo-data instance used for marketing images.

If the dashboard returns an empty response after files move, it is a stale process from an old layout. Kill whatever holds 7788 and restart.
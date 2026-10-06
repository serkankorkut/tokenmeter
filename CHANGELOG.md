# Changelog

## 0.3.3 · 2026-10-06

- Limits up front: your 5-hour and weekly limits for Claude Code and Codex now sit at the top of the dashboard, with the same labels for both.

## 0.3.2 · 2026-10-06

- Easier to read tips: the answer now appears right under its label, above What will be sent.

## 0.3.1 · 2026-10-06

- Get tips works in the background: Tokenmeter now finds Claude Code, Codex or Copilot when it runs as a service. Run `tokenmeter start` once after upgrading.
- A progress spinner while the AI answers, and clearer privacy wording.

## 0.3.0 · 2026-10-06

- Tips to spend less: one click sends your 5 or 10 most expensive prompts to Claude Code, Codex or Copilot CLI on your machine and shows what to change. Or copy the prompt into any AI.

## 0.2.10 · 2026-10-04

- Clearer setup: `tokenmeter start` explains when the command is not on your PATH yet, and how to fix it.
- The Spend tile links to plan setup when no subscription is configured.

## 0.2.6 · 2026-09-28

- Starts at login: Tokenmeter runs its own login service on macOS and Linux, so it starts again after a reboot without Homebrew services.

## 0.2.5 · 2026-09-28

- Smoother upgrades: `tokenmeter start` restarts an older running copy after an upgrade.

## 0.2.4 · 2026-09-28

- Start and stop: new `tokenmeter start` and `tokenmeter stop`. If port 7788 is taken, Tokenmeter uses the next free port, and `--port` saves your choice.

## 0.2.3 · 2026-09-28

- Instant start: the dashboard opens instantly and indexes large histories in the background.
- Prices for GPT-6 Sol and Luna, with OpenAI long-context rates.

## 0.2.1 · 2026-09-22

- Cost you can check: tokens are split into cached, fresh and output, with the cost math shown for every prompt.
- Your own settings live in `~/.tokenmeter/config.json`.

## 0.2.0 · 2026-09-20

- First release: on PyPI and Homebrew, with per-prompt cost, usage limits, cache misses, cost per commit, Copilot CLI support, team mode and a menu bar widget.
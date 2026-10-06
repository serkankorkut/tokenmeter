# Changelog

## 0.3.1 · 2026-10-06

- Get tips now finds Claude Code, Codex or Copilot when Tokenmeter runs in the background. Run `tokenmeter start` once after upgrading.
- A progress spinner while the AI answers, and clearer privacy wording.

## 0.3.0 · 2026-10-06

- Tips to spend less: one click sends your 5 or 10 most expensive prompts to Claude Code, Codex or Copilot CLI on your machine and shows what to change. Or copy the prompt into any AI.

## 0.2.10 · 2026-10-04

- `tokenmeter start` explains when the command is not on your PATH yet, and how to fix it.
- The Spend tile links to plan setup when no subscription is configured.

## 0.2.6 · 2026-09-28

- Tokenmeter runs its own login service on macOS and Linux, so it starts again after a reboot without Homebrew services.

## 0.2.5 · 2026-09-28

- `tokenmeter start` restarts an older running copy after an upgrade.

## 0.2.4 · 2026-09-28

- New `tokenmeter start` and `tokenmeter stop`. If port 7788 is taken, Tokenmeter uses the next free port, and `--port` saves your choice.

## 0.2.3 · 2026-09-28

- The dashboard opens instantly and indexes large histories in the background.
- Prices for GPT-6 Sol and Luna, with OpenAI long-context rates.

## 0.2.1 · 2026-09-22

- Tokens are split into cached, fresh and output, with the cost math shown for every prompt.
- Your own settings live in `~/.tokenmeter/config.json`.

## 0.2.0 · 2026-09-20

- First release on PyPI and Homebrew: per-prompt cost, usage limits, cache misses, cost per commit, Copilot CLI support, team mode and a menu bar widget.
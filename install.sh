#!/bin/sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.claude/skills" "$HOME/.codex/skills" "$HOME/.local/bin"
ln -sfn "$HERE" "$HOME/.claude/skills/tokenmeter"
ln -sfn "$HERE" "$HOME/.codex/skills/tokenmeter"
printf '#!/bin/sh\nexec python3 "%s/tokenmeter/server.py" "$@"\n' "$HERE" > "$HOME/.local/bin/tokenmeter"
chmod +x "$HOME/.local/bin/tokenmeter" "$HERE/tokenmeter/server.py"
echo "tokenmeter installed."
echo "  Claude Code: /tokenmeter   (loads next session, or /reload-plugins)"
echo "  Codex:       /tokenmeter"
echo "  Shell:       tokenmeter --open   (ensure ~/.local/bin is on PATH)"
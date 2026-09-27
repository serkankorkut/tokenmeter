#!/bin/sh
# Mirrors the PyPI sdist of tokenmeter-dashboard to a GitHub Release on the public tap repo
# (so Homebrew installs are counted as asset downloads) and prints the Homebrew formula.
# Usage: release/brew-formula.sh [version] > ../homebrew-tap/Formula/tokenmeter.rb
set -e
TAP="serkankorkut/homebrew-tap"
V="${1:-$(curl -s https://pypi.org/pypi/tokenmeter-dashboard/json | python3 -c 'import sys,json; print(json.load(sys.stdin)["info"]["version"])')}"
JSON=$(curl -s "https://pypi.org/pypi/tokenmeter-dashboard/$V/json")
SRC=$(printf "%s" "$JSON" | python3 -c 'import sys,json; print([u for u in json.load(sys.stdin)["urls"] if u["packagetype"]=="sdist"][0]["url"])')
SHA=$(printf "%s" "$JSON" | python3 -c 'import sys,json; print([u for u in json.load(sys.stdin)["urls"] if u["packagetype"]=="sdist"][0]["digests"]["sha256"])')
FILE="tokenmeter_dashboard-$V.tar.gz"
TMP=$(mktemp -d)
curl -sL "$SRC" -o "$TMP/$FILE"
GOT=$(shasum -a 256 "$TMP/$FILE" | cut -d' ' -f1)
[ "$GOT" = "$SHA" ] || { echo "sha mismatch for $FILE" >&2; exit 1; }
if ! gh release view "v$V" --repo "$TAP" >/dev/null 2>&1; then
  gh release create "v$V" "$TMP/$FILE" --repo "$TAP" --title "Tokenmeter $V" --notes "Mirror of https://pypi.org/project/tokenmeter-dashboard/$V/ for Homebrew. Install: brew install serkankorkut/tap/tokenmeter" >&2
fi
rm -rf "$TMP"
cat <<RUBY
class Tokenmeter < Formula
  include Language::Python::Virtualenv

  desc "Token usage, cost and limits dashboard for Claude Code, Codex and Copilot CLI"
  homepage "https://github.com/serkankorkut/homebrew-tap"
  url "https://github.com/$TAP/releases/download/v$V/$FILE"
  sha256 "$SHA"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      Start Tokenmeter and open your dashboard in the browser:
        tokenmeter start

      Your dashboard lives at http://127.0.0.1:7788
      It keeps running in the background and starts again at login.
      Stop it any time with: tokenmeter stop
      After an upgrade, run tokenmeter start again to switch to the new version.
    EOS
  end

  service do
    run [opt_bin/"tokenmeter"]
    keep_alive true
    log_path var/"log/tokenmeter.log"
    error_log_path var/"log/tokenmeter.log"
  end

  test do
    assert_match "tokenmeter $V", shell_output("#{bin}/tokenmeter --version")
  end
end
RUBY
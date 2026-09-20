#!/bin/sh
# Prints a Homebrew formula for the tokenmeter-dashboard release currently on PyPI.
# Usage: release/brew-formula.sh [version] > Formula/tokenmeter.rb
set -e
V="${1:-$(curl -s https://pypi.org/pypi/tokenmeter-dashboard/json | python3 -c 'import sys,json; print(json.load(sys.stdin)["info"]["version"])')}"
JSON=$(curl -s "https://pypi.org/pypi/tokenmeter-dashboard/$V/json")
URL=$(printf "%s" "$JSON" | python3 -c 'import sys,json; print([u for u in json.load(sys.stdin)["urls"] if u["packagetype"]=="sdist"][0]["url"])')
SHA=$(printf "%s" "$JSON" | python3 -c 'import sys,json; print([u for u in json.load(sys.stdin)["urls"] if u["packagetype"]=="sdist"][0]["digests"]["sha256"])')
cat <<RUBY
class Tokenmeter < Formula
  include Language::Python::Virtualenv

  desc "Token usage, cost and limits dashboard for Claude Code, Codex and Copilot CLI"
  homepage "https://github.com/serkankorkut/tokenmeter"
  url "$URL"
  sha256 "$SHA"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
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
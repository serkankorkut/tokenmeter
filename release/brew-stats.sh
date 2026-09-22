#!/bin/sh
# Homebrew install counts: every brew install or upgrade downloads the release asset once.
gh api repos/serkankorkut/homebrew-tap/releases --paginate -q '.[] | "\(.tag_name)\t\(.assets[0].download_count // 0) downloads\t\(.published_at[:10])"'
echo "---"
echo "PyPI (separate channel): https://pypistats.org/packages/tokenmeter-dashboard"
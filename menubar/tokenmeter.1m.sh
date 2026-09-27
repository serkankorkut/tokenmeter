#!/bin/sh
# <xbar.title>Tokenmeter</xbar.title>
# <xbar.desc>Today's AI coding spend from the local Tokenmeter server.</xbar.desc>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
SAVED=$(python3 -c 'import json,os; print(json.load(open(os.path.expanduser("~/.tokenmeter/config.json"))).get("_port", ""))' 2>/dev/null)
BASE="${TOKENMETER_PORT:-${SAVED:-7788}}"
S=""
for PORT in $(seq "$BASE" $((BASE + 10))); do
  S=$(curl -sf --max-time 1 "http://127.0.0.1:$PORT/api/summary") && break
done
[ -n "$S" ] || { echo "◔ off"; echo "---"; echo "Tokenmeter is not running | bash=tokenmeter param1=start terminal=false"; exit 0; }
echo "$S" | python3 -c '
import sys, json
s = json.load(sys.stdin)
u = lambda v: "$%.0f" % v if v >= 100 else "$%.2f" % v
print("◔ %s" % u(s["today"]["cost"]))
print("---")
print("Today: %s · %d prompts · %.1fM tokens" % (u(s["today"]["cost"]), s["today"]["prompts"], s["today"]["tokens"] / 1e6))
for k, v in sorted(s["today_by_tool"].items()):
    print("--%s: %s" % (k, u(v["cost"])))
print("Last 5h: %s" % u(sum(v["cost"] for v in s["last_5h"].values())))
print("Month: %s · on pace for %s" % (u(s["month"]["cost"]), u(s["month_projection"])))
if s.get("budget"):
    print("Budget: %s" % ", ".join("%s $%s" % (k, v) for k, v in s["budget"].items()))
cx = (s.get("limits") or {}).get("codex")
if cx:
    for w in cx["windows"]:
        print("Codex %s window: %.0f%% used" % ("5h" if w["window_minutes"] == 300 else "weekly" if w["window_minutes"] == 10080 else str(w["window_minutes"]) + "m", w["used_percent"]))
print("---")
print("Open dashboard | href=http://127.0.0.1:%s" % "'"$PORT"'")
'
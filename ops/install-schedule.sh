#!/usr/bin/env bash
# Install (or reinstall) the monthly launchd job.
#
#   ./ops/install-schedule.sh            # install / update
#   ./ops/install-schedule.sh --status   # is it loaded, when does it next run
#   ./ops/install-schedule.sh --remove
#
# Nothing here touches sudo or system directories: the job is a per-user agent
# under ~/Library/LaunchAgents, and it runs as you, with your network access.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.sunqi.auckland-pipeline"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

case "${1:-install}" in
  --status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | sed -n '1,25p' \
      || echo "not loaded"
    exit 0 ;;
  --remove)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$TARGET"
    echo "removed $LABEL"
    exit 0 ;;
esac

PYTHON="$(command -v python3)"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"

sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__ROOT__|$ROOT|g" \
    "$ROOT/ops/$LABEL.plist" > "$TARGET"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$TARGET"

echo "installed $LABEL"
echo "  python : $PYTHON"
echo "  root   : $ROOT"
echo "  runs   : 06:10 on the 2nd of each month (catches up after sleep)"
echo "  logs   : $ROOT/logs/launchd.{out,err}.log  and  $ROOT/logs/pipeline.jsonl"
echo
echo "run it once now:   launchctl kickstart -p $DOMAIN/$LABEL"
echo "check state:       python3 scripts/pipeline.py status"

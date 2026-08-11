#!/usr/bin/env bash
# Serve heatmap.html over http://localhost and open it.
#
# Opening the file directly (open heatmap.html) works for everything except the
# optional model call: a file:// page sends "Origin: null", which the API
# rejects. Serving over localhost gives it a real origin.
#
#   ./ops/serve.sh          # port 8000
#   ./ops/serve.sh 8123
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8000}"

[ -f "$ROOT/heatmap.html" ] || {
  echo "heatmap.html not found — run: python3 scripts/pipeline.py run --rebuild" >&2
  exit 1
}

echo "http://localhost:$PORT/heatmap.html   (ctrl-c to stop)"
( sleep 1 && open "http://localhost:$PORT/heatmap.html" ) &
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT"

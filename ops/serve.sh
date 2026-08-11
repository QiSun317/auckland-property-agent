#!/usr/bin/env bash
# Serve heatmap.html over http://localhost and open it.
#
# Opening the file directly (open heatmap.html) works for everything except the
# optional model call: a file:// page sends "Origin: null", which the API
# rejects. Serving over localhost gives it a real origin.
#
#   ./ops/serve.sh          # first free port from 8000
#   ./ops/serve.sh 8123     # start looking from 8123
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_PORT="${1:-8000}"

[ -f "$ROOT/heatmap.html" ] || {
  echo "heatmap.html not found." >&2
  echo "  build it:  python3 scripts/pipeline.py run --rebuild" >&2
  exit 1
}

# Take the first port nobody is listening on. Ports get squatted by other
# projects, and the old version of this script opened the browser before
# checking, so you'd land on someone else's 404.
port=""
for p in $(seq "$START_PORT" $((START_PORT + 20))); do
  if ! lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then port="$p"; break; fi
done
[ -n "$port" ] || { echo "no free port in $START_PORT..$((START_PORT + 20))" >&2; exit 1; }
[ "$port" = "$START_PORT" ] || echo "port $START_PORT is taken, using $port"

python3 -m http.server "$port" --bind 127.0.0.1 --directory "$ROOT" &
server=$!
trap 'kill $server 2>/dev/null || true' EXIT INT TERM

url="http://127.0.0.1:$port/heatmap.html"

# Only open the browser once the server actually answers for this file.
for _ in $(seq 1 40); do
  if curl -fsS -o /dev/null --max-time 1 "$url" 2>/dev/null; then
    echo "serving $url   (ctrl-c to stop)"
    open "$url"
    wait $server
    exit 0
  fi
  kill -0 $server 2>/dev/null || { echo "server exited before it was ready" >&2; exit 1; }
  sleep 0.25
done

echo "server did not come up on $url" >&2
exit 1

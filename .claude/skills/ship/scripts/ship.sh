#!/usr/bin/env bash
# Take the working tree all the way to a verified live site, in one command.
#
#   .claude/skills/ship/scripts/ship.sh "Let the assistant carry a conversation"
#
# The order matters and is not obvious: the page has to be built before the
# tests run, because the suite loads heatmap.html through jsdom and exercises
# the code that actually shipped rather than a copy of it. Building second
# would test the previous build and pass while shipping something else.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT"

MSG="${1:-}"
if [ -z "$MSG" ]; then
  echo "give a message saying what the page gained, e.g." >&2
  echo "  ship.sh \"Let the assistant carry a conversation\"" >&2
  echo "The site repo's history is the only record of what the public page" >&2
  echo "actually changed, and \"Refresh data\" is a lie when it grew a feature." >&2
  exit 1
fi

# The proxy URL is the single most dangerous thing to forget. Building without
# it writes "proxy":"" into the page, which sets MODEL_ON=false and silently
# turns the assistant back into rules-only — no error, no warning, the page
# just quietly loses the model. It shipped that way once for weeks.
PROXY="${AKL_AGENT_PROXY:-https://auckland-suburb-agent.qisun317.workers.dev}"

echo "==> building with proxy $PROXY"
AKL_AGENT_PROXY="$PROXY" python3 scripts/build_map.py

echo "==> checking the proxy actually landed in the build"
if ! grep -q "\"proxy\":\"https" heatmap.html; then
  echo "heatmap.html has an empty proxy — the assistant would ship without the model." >&2
  echo "This means AKL_AGENT_PROXY was not picked up. Not publishing." >&2
  exit 1
fi

echo "==> running the gate suite against the build"
node evals/run.mjs heatmap.html evals/cases.jsonl > /tmp/ship-evals.json
python3 - <<'PY'
import json, sys
d = json.load(open('/tmp/ship-evals.json'))
bad = [r for r in d['results'] if not r['ok']]
print(f"    {d['n'] - len(bad)}/{d['n']} pass")
for r in bad:
    print(f"    FAIL {r['id']}: got {r['got']!r}, want {r['expect']!r}")
if bad:
    print("\nNot publishing. These gates are the page's claim to being trustworthy —\n"
          "every case in the file is a way this thing has actually been wrong before.",
          file=sys.stderr)
    sys.exit(1)
PY

# The worker is a separate deploy target and does not go out with the page.
# Flagging it here rather than running it: `wrangler deploy` needs its own
# approval, so burying it inside this script would make the whole script fail.
#
# This can only see uncommitted edits, which is not the same question as
# "is the deployed worker current" — you may well have deployed already and
# simply not committed yet. Hence a question rather than an assertion.
if ! git diff --quiet -- ops/worker/ || ! git diff --cached --quiet -- ops/worker/; then
  echo
  echo "?? ops/worker/ has uncommitted edits. If they are not deployed yet, the"
  echo "?? page ships against the old worker. Deploy, then re-run:"
  echo "??     cd ops/worker && npx wrangler deploy"
  echo "?? (already deployed? ignore this)"
  echo
fi

if [ "${SHIP_DRY_RUN:-}" = "1" ]; then
  echo
  echo "==> dry run: built and tested, stopping before commit/push/publish"
  exit 0
fi

echo "==> committing and pushing the source repo"
if git diff --quiet && git diff --cached --quiet; then
  echo "    working tree clean, nothing to commit"
else
  git add -A
  git commit -q -m "$MSG

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
  echo "    committed"
fi
git push -q origin main
echo "    pushed to origin/main"

echo "==> publishing the page"
./ops/publish.sh "$MSG"

echo "==> verifying the live site serves this exact build"
LOCAL="$(shasum -a 256 heatmap.html | cut -d' ' -f1)"
URL="https://QiSun317.github.io/auckland-house-heatmap/"
for i in 1 2 3 4 5 6; do
  LIVE="$(curl -sS "$URL" | shasum -a 256 | cut -d' ' -f1)"
  if [ "$LIVE" = "$LOCAL" ]; then
    echo "    live and matching after $((i * 20))s: $URL"
    exit 0
  fi
  echo "    attempt $i: not yet (Pages is still building), waiting 20s"
  sleep 20
done

echo "still not matching after 2 minutes." >&2
echo "Pages is usually slower than this only when its build failed —" >&2
echo "check https://github.com/QiSun317/auckland-house-heatmap/actions" >&2
exit 1

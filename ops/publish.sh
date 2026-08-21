#!/usr/bin/env bash
# Push the freshly built heatmap.html to the public GitHub Pages site.
#
#   ./ops/publish.sh
#
# The site lives in its own public repo holding only the built page: this repo
# stays private because it carries the scrapers, and data/raw holds council
# valuations we do not redistribute at address level. Only the aggregated page
# goes out.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_REPO="${AKL_SITE_REPO:-QiSun317/auckland-house-heatmap}"
WORK="${AKL_SITE_DIR:-$ROOT/.site}"
PAGE="$ROOT/heatmap.html"

[ -f "$PAGE" ] || { echo "heatmap.html not built yet" >&2; exit 1; }

if [ ! -d "$WORK/.git" ]; then
  rm -rf "$WORK"
  git clone -q "https://github.com/$SITE_REPO.git" "$WORK"
fi
git -C "$WORK" fetch -q origin main
git -C "$WORK" reset -q --hard origin/main

cp "$PAGE" "$WORK/index.html"

if git -C "$WORK" diff --quiet; then
  echo "page unchanged, nothing to publish"
  exit 0
fi

stamp="$(date +%Y-%m-%d)"
# Most publishes are a data refresh and say so by default, but the site repo's
# history is the only record of what the public page actually gained, and
# "Refresh data" is a lie when the page grew a feature.
#
#   ./ops/publish.sh "Add the mortgage and rates calculator"
msg="${1:-Refresh data} ($stamp)"
git -C "$WORK" add index.html
git -C "$WORK" commit -q -m "$msg"
git -C "$WORK" push -q origin main
echo "published $stamp -> https://${SITE_REPO%%/*}.github.io/${SITE_REPO##*/}/"

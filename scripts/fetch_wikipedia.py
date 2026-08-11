#!/usr/bin/env python3
"""Pull a short intro for each priced suburb from English Wikipedia.

Title resolution is ambiguous ("Albany" is a city in New York, "Flat Bush,
New Zealand" doesn't exist but "Flat Bush" does), so each candidate title is
verified before it is accepted: the article must either sit within 20 km of
the suburb centroid we already have, or read as an Auckland/NZ place.

Output: data/raw/wikipedia.json  {suburb: {title, extract, url}}
"""
import json
import os
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
OUT = Path(os.environ.get("AKL_OUT_DIR", RAW))

API = "https://en.wikipedia.org/w/api.php"
UA = "auckland-property-agent/0.1 (personal research project)"
BATCH = 20
MAX_KM = 20
NZ_HINT = re.compile(r"\b(Auckland|New Zealand)\b")
# Wikipedia leads often open with a pronunciation gloss or a stray parenthetical.
CLEAN = re.compile(r"\s+")


def api(params, tries=6):
    """Serial with a pause between calls — the API 429s well before it needs to."""
    params = {**params, "format": "json", "formatversion": "2"}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                time.sleep(1.0)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fetch_pages(titles):
    """titles -> {requested_title: page dict} (follows redirects/normalisation)."""
    out = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        data = api({
            "action": "query",
            "prop": "extracts|coordinates|info",
            "exintro": 1, "explaintext": 1, "redirects": 1,
            "inprop": "url",
            "titles": "|".join(chunk),
        }).get("query", {})
        # map every alias back to the title we asked for
        alias = {}
        for kind in ("normalized", "redirects"):
            for m in data.get(kind, []):
                alias[m["to"]] = alias.get(m["from"], m["from"])
        for p in data.get("pages", []):
            asked = alias.get(p["title"], p["title"])
            out[asked] = p
    return out


def accept(page, lat, lon):
    if page.get("missing") or not page.get("extract"):
        return False
    co = (page.get("coordinates") or [None])[0]
    if co and lat and lon:
        return haversine(lat, lon, co["lat"], co["lon"]) <= MAX_KM
    return bool(NZ_HINT.search(page["extract"][:400]))


def trim(text, max_chars=520):
    text = CLEAN.sub(" ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    stop = cut.rfind(". ")
    return (cut[:stop + 1] if stop > max_chars * 0.5 else cut.rstrip() + "…")


def main():
    suburbs = [s for s in json.loads((RAW / "opes_suburbs.json").read_text())
               if s.get("average_house_price")]
    print(f"{len(suburbs)} suburbs")

    resolved, pending = {}, {s["suburb_name"]: s for s in suburbs}
    patterns = ["{n}, Auckland", "{n}, New Zealand", "{n}"]

    for pat in patterns:
        if not pending:
            break
        wanted = {pat.format(n=n): n for n in pending}
        pages = fetch_pages(list(wanted))
        hit = 0
        for title, name in wanted.items():
            page = pages.get(title)
            s = pending[name]
            if page and accept(page, s.get("latitude"), s.get("longitude")):
                resolved[name] = {
                    "title": page["title"],
                    "extract": trim(page["extract"]),
                    "url": page.get("fullurl")
                           or "https://en.wikipedia.org/wiki/"
                              + urllib.parse.quote(page["title"].replace(" ", "_")),
                }
                hit += 1
        for name in list(resolved):
            pending.pop(name, None)
        print(f"  '{pat}' -> +{hit} (total {len(resolved)}, {len(pending)} left)")

    out = OUT / "wikipedia.json"
    out.write_text(json.dumps(resolved, ensure_ascii=False, indent=1))
    print(f"wrote {len(resolved)} intros -> {out}")
    if pending:
        print("no article found:", sorted(pending))


if __name__ == "__main__":
    main()

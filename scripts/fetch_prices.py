#!/usr/bin/env python3
"""Fetch per-suburb Auckland property stats from opespartners.co.nz.

Each suburb page is a Next.js app-router page; the suburb record is embedded in
the RSC flight payload under the key "suburbData". We reconstruct the payload
from the self.__next_f.push(...) chunks and JSON-decode that object.

Output: data/raw/opes_suburbs.json  (list of raw suburb records)
"""
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
OUT = Path(os.environ.get("AKL_OUT_DIR", RAW))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SITEMAPS = [
    f"https://www.opespartners.co.nz/sitemaps/sitemaps-1-section-propertyMarketSuburbs-1-sitemap-p{p}.xml"
    for p in (1, 2, 3)
]

PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)')
DECODER = json.JSONDecoder()


def get(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - retry on anything transient
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
            last = exc
    raise last


def suburb_urls():
    urls = set()
    for sm in SITEMAPS:
        for loc in re.findall(r"<loc>([^<]+)</loc>", get(sm)):
            if "/property-markets/auckland/" in loc:
                urls.add(loc.strip())
    return sorted(urls)


def parse_page(html):
    flight = "".join(json.loads('"' + p + '"') for p in PUSH_RE.findall(html))
    marker = '"suburbData":'
    i = flight.find(marker)
    if i < 0:
        return None
    obj, _ = DECODER.raw_decode(flight, i + len(marker))
    return obj


def scrape(url):
    try:
        rec = parse_page(get(url))
    except Exception as exc:  # noqa: BLE001
        print(f"  !! {url}: {exc}", file=sys.stderr)
        return None
    if rec is None:
        print(f"  !! {url}: no suburbData", file=sys.stderr)
        return None
    rec["source_url"] = url
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    urls = suburb_urls()
    print(f"{len(urls)} Auckland suburb pages")

    with ThreadPoolExecutor(max_workers=6) as pool:
        records = [r for r in pool.map(scrape, urls) if r]

    # Drop the long monthly history to keep the file manageable, but keep a
    # yearly sample so we can chart trends later.
    for r in records:
        graph = r.pop("median_house_prices_graph", None)
        if graph:
            r["price_history_yearly"] = [
                p for p in graph if p.get("date", "").endswith("-01-01")
            ]

    out = OUT / "opes_suburbs.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=1))
    print(f"wrote {len(records)} records -> {out}")


if __name__ == "__main__":
    main()

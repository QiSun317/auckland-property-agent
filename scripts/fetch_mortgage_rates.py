#!/usr/bin/env python3
"""Fetch carded home-loan rates for every NZ bank from interest.co.nz.

The alternative source quotes its rates as prose ("the lowest 1 year fixed
mortgage interest rate is 4.65%"), which is a sentence, not data — one rewrite
and the regex reads a different number without ever failing. interest.co.nz
publishes the same thing as an HTML table with a stable header, so this parses
the table.

robots.txt allows /borrowing (only /admin/, /search/, /user/* and similar are
disallowed).

Output: data/raw/mortgage_rates.json
  {fetched_at, source, terms, products: [...], lowest: {...}}

`products` is what the table said, one row per institution+product. `lowest` is
the single statistic the page actually uses, derived here so that exactly one
piece of code defines it: the cheapest carded rate a main bank offers at each
term. See LOWEST_BASIS.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
OUT = Path(os.environ.get("AKL_OUT_DIR", RAW))

URL = "https://www.interest.co.nz/borrowing"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# The registered banks most people actually shop between. Second-tier lenders
# and the Chinese and Indian bank subsidiaries are kept in `products` but do not
# set the headline rate: quoting a rate almost nobody in the reader's position
# will be offered is worse than quoting a slightly higher one they will.
MAIN_BANKS = ["ANZ", "ASB", "BNZ", "Kiwibank", "Westpac"]

# Column header -> the short key used in the output and on the page. Headers are
# matched with all whitespace removed: the cells are marked up rather than plain
# ("6 months" arrives as "6months" once the tags are stripped), and which of the
# two you get is a detail of their template, not of the data.
TERM_KEYS = {
    "variablefloating": "floating",
    "6months": "6m",
    "1year": "1y",
    "2years": "2y",
    "3years": "3y",
    "4years": "4y",
    "5years": "5y",
}
squash = lambda s: re.sub(r"\s+", "", s.lower())
TERM_ORDER = ["floating", "6m", "1y", "18m", "2y", "3y", "4y", "5y"]

# Rows like ["", "Standard", "18 months = 6.05"] are a continuation of the
# product above, carrying the one term that has no column of its own.
EIGHTEEN = re.compile(r"18\s*months?\s*=\s*([0-9.]+)", re.I)

# A green top-up or an offset account is quoted at one term only; a home loan is
# quoted across the row. Counting terms separates them structurally, which
# survives the renaming that a blocklist of product names would not — and it has
# to be separated, because "Good Energy - Up to $80K" at 1.00% would otherwise
# become the cheapest three-year mortgage in New Zealand.
MIN_TERMS = 3

LOWEST_BASIS = (
    "cheapest carded rate at each term across " + ", ".join(MAIN_BANKS) +
    "; a product must quote at least %d terms to count, which excludes "
    "single-term green top-ups and offset accounts" % MIN_TERMS)


class Rows(HTMLParser):
    """Cells of every <table> on the page, as lists of strings.

    Institution cells hold a logo rather than text on this page, so an <img>
    contributes its alt text — that is where the bank's name actually is.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._rows, self._cells, self._buf = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._cells = []
        elif tag in ("td", "th") and self._cells is not None:
            self._buf = []
        elif tag == "img" and self._buf is not None:
            self._buf.append(dict(attrs).get("alt", ""))

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._buf is not None:
            self._cells.append(re.sub(r"\s+", " ", "".join(self._buf)).strip())
            self._buf = None
        elif tag == "tr" and self._cells is not None:
            self._rows.append(self._cells)
            self._cells = None
        elif tag == "table" and self._rows is not None:
            self.tables.append(self._rows)
            self._rows = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def parse(html):
    """Every rate row on the page, across all of its tables."""
    p = Rows()
    p.feed(html)

    products = []
    for rows in p.tables:
        if not rows:
            continue
        header = [squash(c) for c in rows[0]]
        cols = {i: TERM_KEYS[h] for i, h in enumerate(header) if h in TERM_KEYS}
        if "1y" not in cols.values():          # not a rate table
            continue

        institution = ""
        for cells in rows[1:]:
            if not cells:
                continue
            # Continuation row: attach the 18-month rate to the row above it,
            # but only if it names the same product — otherwise a table whose
            # first row happened to be a continuation would hang its rate on
            # whatever the previous table ended with.
            if len(cells) < len(header):
                m = EIGHTEEN.search(" ".join(cells))
                if m and products and len(cells) > 1 \
                        and cells[1] == products[-1]["product"]:
                    products[-1]["rates"]["18m"] = num(m.group(1))
                continue
            institution = cells[0] or institution
            rates = {k: num(cells[i]) for i, k in cols.items()}
            rates = {k: v for k, v in rates.items() if v is not None}
            if not rates:
                continue
            products.append({"institution": institution,
                             "product": cells[1], "rates": rates})
    return products


def lowest(products):
    """The headline rate per term. See LOWEST_BASIS."""
    eligible = [p for p in products
                if p["institution"] in MAIN_BANKS and len(p["rates"]) >= MIN_TERMS]
    out = {}
    for term in TERM_ORDER:
        offers = [(p["rates"][term], p["institution"]) for p in eligible
                  if p["rates"].get(term)]
        if offers:
            best = min(offers)
            out[term] = {"rate": best[0],
                         "banks": sorted({b for r, b in offers if r == best[0]})}
    return out


def main():
    products = parse(get(URL))
    if not products:
        sys.exit("no rate rows parsed — the table markup has probably changed")

    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_at": date.today().isoformat(),
        "source": URL,
        "main_banks": MAIN_BANKS,
        "lowest_basis": LOWEST_BASIS,
        "terms": TERM_ORDER,
        "lowest": lowest(products),
        "products": products,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "mortgage_rates.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    lo = payload["lowest"]
    print(f"wrote {len(products)} product rows -> {out}")
    print("  lowest: " + "  ".join(
        f"{t} {lo[t]['rate']:.2f}%" for t in TERM_ORDER if t in lo))


if __name__ == "__main__":
    main()

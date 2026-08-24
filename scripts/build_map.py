#!/usr/bin/env python3
"""Join suburb prices to LINZ polygons and emit a self-contained heat map.

Outputs
  data/suburb_prices.csv   flat table, one row per suburb (for the agent to use)
  data/join_report.txt     what matched, what didn't
  heatmap.html             standalone page, no external requests
"""
import csv
import json
import os
import math
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

# One definition of "these two names are the same place", shared with the
# database build so the page and the db cannot disagree.
from build_db import ALIASES

try:
    import duckdb
except ModuleNotFoundError:  # noqa: TRY003 - the message is the point
    import sys
    sys.exit(
        f"duckdb is not installed for this interpreter.\n"
        f"  running: {sys.executable}\n"
        f"  fix:     {sys.executable} -m pip install duckdb\n"
        f"(a shell whose python3 resolves elsewhere will hit this even though\n"
        f" another interpreter on the machine has it)")

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
DATA = ROOT / "data"

VIEW_W = 3000.0          # SVG user units across the full region
PRECISION = 1            # ~3 m at this scale

# Default framing: the built-up isthmus + North Shore + Whangaparaoa + Waiheke
# down to Papakura, i.e. where nearly everyone actually shops for a house. The
# full region (Wellsford to Port Waikato, plus the outer gulf) is one click away.
URBAN_LONLAT = (174.50, -37.10, 175.15, -36.58)

# --- diverging blue<->red ramp -------------------------------------------------
# Blue arm = the reference sequential blue steps; red arm mirrors each step's
# OKLCH lightness and chroma at the red hue (24.9 deg), so the two arms are
# perceptually balanced. Midpoint is neutral gray, per the diverging rule.
RAMP_LIGHT = ["#104281", "#2a78d6", "#86b6ef", "#b7d3f6", "#f0efec",
              "#f4c2be", "#ea9a93", "#c74845", "#762221"]
# On the dark surface the midpoint has to sit *above* the background rather
# than blend into it, so the dark arms brighten outward from a mid gray that
# still clears 2:1 on #1a1a19. Same construction: each red step mirrors the
# blue step's OKLCH lightness and chroma.
RAMP_DARK = ["#519fff", "#388df5", "#427ac1", "#46658e", "#4a4a47",
             "#89524d", "#b75852", "#e45955", "#ff615d"]

# Regional context figure quoted by the same source (REINZ-style sale median,
# a different measure from the per-suburb automated valuations).
REGION_SALE_MEDIAN = 980000

# The source's own dates used to be constants here, and the page kept showing
# them long after they stopped being true — a scheduled job that refreshes the
# data weekly but not the date printed beside it is worse than no date at all.
# Both are carried in the records themselves, so both are read from there.
EXCEL_EPOCH = date(1899, 12, 30)     # the serial base these dates use


def source_dates(prices):
    """When the source says its figures are as at, and when it last published.

    max_date is an Excel serial: 46174 -> 2026-06-01, corroborated by
    one_year_ago_date and two_year_ago_date sitting exactly 365 and 730 days
    behind it. Different suburbs carry different max_dates, so the newest is
    the dataset's basis.
    """
    serials = [p["max_date"] for p in prices if p.get("max_date")]
    published = sorted({p["last_updated"] for p in prices if p.get("last_updated")})
    if not serials or not published:
        raise SystemExit("the price records carry no max_date or last_updated — "
                         "the source changed shape; fix this rather than "
                         "shipping a date the page will state as fact")
    as_at = EXCEL_EPOCH + timedelta(days=max(serials))
    # A serial that decodes to last century or next is a decoding error, and a
    # wrong date printed confidently is the failure worth preventing.
    if not date(2000, 1, 1) <= as_at <= date.today() + timedelta(days=400):
        raise SystemExit(f"max_date decodes to {as_at}, which cannot be right")
    return as_at.isoformat(), published[-1]


def fetch_times():
    """When each source was last pulled. Already recorded per run; it has just
    never been shown to the reader, who has no other way to tell whether the
    page in front of them is a week or a year old."""
    con = duckdb.connect(str(DATA / "auckland.duckdb"), read_only=True)
    try:
        rows = con.execute("""
            SELECT source, max(finished_at)::DATE::TEXT
            FROM pipeline_step WHERE status IN ('ok', 'unchanged')
            GROUP BY 1 ORDER BY 1""").fetchall()
    finally:
        con.close()
    return {s: d for s, d in rows}

# Opes records that duplicate an area already covered by its constituent
# suburbs, or that have no polygon in the LINZ layer.
DROP_SUBURBS = {"Waiheke Island", "Kawau Island"}

# How far the price join is allowed to fall before the build is a failure
# rather than a quieter map. An unattended weekly run has nobody reading the
# join report, so the drop has to stop the run instead of shipping.
MIN_PRICED = 190

# --- mortgage rates ------------------------------------------------------------
# Fetched, validated and promoted like every other source (fetch_mortgage_rates
# .py), then read here. Carried with the date it was read: a repayment computed
# off a rate that moved two months ago is wrong in the way that is hardest to
# catch, because it still looks exactly like a repayment. The page prints this
# date and says so once the rate is more than 60 days old.
FIXED_TERMS = ["6m", "1y", "18m", "2y", "3y", "4y", "5y"]


def mortgage_rates():
    path = RAW / "mortgage_rates.json"
    if not path.exists():
        raise SystemExit(
            f"{path} is missing.\n"
            f"  fix:  python3 scripts/fetch_mortgage_rates.py\n"
            f"  or:   python3 scripts/pipeline.py run --force mortgagerates")
    d = json.loads(path.read_text())
    low = d["lowest"]
    return {
        "asAt": d["as_at"],
        "src": d["source"],
        "basis": d["lowest_basis"],
        "banks": d["main_banks"],
        # [term, rate, who offers it] — the third element is only a tooltip, but
        # "4.95% (Kiwibank)" is a different claim from "4.95%", and the second
        # one invites the reader to assume it is their bank.
        "terms": [[t, low[t]["rate"], low[t]["banks"]]
                  for t in FIXED_TERMS if t in low],
        "floating": low["floating"]["rate"] if "floating" in low else None,
        "floatingBanks": low["floating"]["banks"] if "floating" in low else [],
        # Where most people fix, and so where the calculator starts. Named
        # rather than indexed: adding 18 months to the list once shifted what
        # position 1 meant.
        "default": low["1y"]["rate"],
    }


# --- what moved since last time -------------------------------------------
# Proposed as a job for Delta's change data feed, and it is not one. bank_rate
# is a type 2 dimension: valid_from is when a rate opened and valid_to is when
# it closed, so "what changed this week" is a WHERE clause on dates the table
# already carries. CDF would return the same facts as row-level inserts and
# deletes, less directly. market_snapshot is replaced wholesale each run, so a
# change feed over it is entirely noise.
CHANGE_WINDOW_DAYS = 8       # a weekly job, plus slack for a late run


def recent_changes():
    """A short, honest account of what moved. Empty is a valid answer and says
    so — the first run has nothing to compare against, and a quiet week really
    is quiet."""
    from datetime import date, timedelta
    since = date.today() - timedelta(days=CHANGE_WINDOW_DAYS)
    out = {"since": since.isoformat(), "rates": None, "release": None}

    table = Path(os.environ.get("AKL_RATE_TABLE", DATA / "state" / "bank_rate"))
    if table.exists():
        try:
            from deltalake import DeltaTable
            rows = DeltaTable(str(table)).to_pyarrow_table().to_pylist()
            main = {"ANZ", "ASB", "BNZ", "Kiwibank", "Westpac"}
            opened = [r for r in rows if r["valid_from"] >= since and r["bank"] in main]
            closed = [r for r in rows if r["valid_to"] and r["valid_to"] >= since
                      and r["bank"] in main]
            # Only report a move where both sides exist; a rate that merely
            # appeared for the first time is not a repricing.
            moves = []
            for term in ("6m", "1y", "18m", "2y", "3y", "5y"):
                was = [r["rate"] for r in closed if r["term"] == term]
                now = [r["rate"] for r in opened if r["term"] == term]
                if was and now:
                    moves.append([term, round(min(was), 2), round(min(now), 2)])
            if moves:
                out["rates"] = {"moves": moves,
                                "banks": sorted({r["bank"] for r in opened})}
        except Exception as exc:  # noqa: BLE001 - a page must not fail on this
            print(f"  (no rate changes read: {exc})")

    return out


# --- Auckland Council rates, 2026/2027 -----------------------------------------
# The council publishes the *average* bill and the year-on-year movement of each
# component, but not the schedule of rates in the dollar, so the split below is
# reconstructed from the pieces it does publish and pinned to the one figure it
# states outright: the average-value residential property (CV $1.28m) pays
# $4,378 this year. At that CV these components return $4,378.00, so the model
# is exact at the anchor and an estimate everywhere else — which is what the
# page calls it. The three environment targeted rates are value-based, so they
# scale with CV; the UAGC and waste charges are fixed per rating unit.
COUNCIL = {
    "year": "2026/2027",
    "general": 0.00250,     # residential urban, per $1 of capital value
    "generalRural": 0.00185,
    "env": 0.00014,         # water quality + natural environment + climate action
    "uagc": 610.0,          # uniform annual general charge, per SUIP
    "waste": 388.8,         # base service + recycling + refuse + food scraps
    "avgCv": 1280000,       # council's stated average residential CV
    "avgTotal": 4378,       # ...and the average bill on it, up 7.9%
    "risePct": 7.9,
    "src": "https://www.aucklandcouncil.govt.nz/en/property-rates-valuations/"
           "changes-rates-bills-this-year.html",
}


# --- colour helpers (OKLab interpolation, done once, baked into a LUT) --------
def _srgb_to_lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin_to_srgb(c):
    v = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return max(0, min(255, round(v * 255)))


def hex_to_oklab(h):
    h = h.lstrip("#")
    r, g, b = (_srgb_to_lin(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def oklab_to_hex(L, A, B):
    l_ = L + 0.3963377774 * A + 0.2158037573 * B
    m_ = L - 0.1055613458 * A - 0.0638541728 * B
    s_ = L - 0.0894841775 * A - 1.2914855480 * B
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return "#%02x%02x%02x" % (_lin_to_srgb(r), _lin_to_srgb(g), _lin_to_srgb(b))


def ramp_lut(stops, n=101):
    labs = [hex_to_oklab(s) for s in stops]
    out = []
    for i in range(n):
        t = i / (n - 1) * (len(stops) - 1)
        k = min(int(t), len(stops) - 2)
        f = t - k
        a, b = labs[k], labs[k + 1]
        out.append(oklab_to_hex(*(a[j] + (b[j] - a[j]) * f for j in range(3))))
    return out


# --- name matching -------------------------------------------------------------
def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bmount\b", "mt", s)
    return re.sub(r"[^a-z0-9]", "", s)


# --- geometry ------------------------------------------------------------------
def mercator(lon, lat):
    return lon, math.degrees(math.log(math.tan(math.pi / 4
                                               + math.radians(lat) / 2)))


def rings(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    return [r for poly in geom["coordinates"] for r in poly]


def build_paths(features):
    projected = []
    for f in features:
        projected.append([[mercator(x, y) for x, y in r] for r in rings(f["geometry"])])

    xs = [p[0] for rs in projected for r in rs for p in r]
    ys = [p[1] for rs in projected for r in rs for p in r]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    scale = VIEW_W / (maxx - minx)
    height = (maxy - miny) * scale

    def to_view(p):
        return (round((p[0] - minx) * scale, PRECISION),
                round((maxy - p[1]) * scale, PRECISION))

    paths, boxes = [], []
    for rs in projected:
        vs = [to_view(p) for r in rs for p in r]
        bxs = [v[0] for v in vs]
        bys = [v[1] for v in vs]
        boxes.append([round(min(bxs), 1), round(min(bys), 1),
                      round(max(bxs) - min(bxs), 1), round(max(bys) - min(bys), 1)])
        d = []
        for r in rs:
            pts, prev = [], None
            for p in r:
                v = to_view(p)
                if v != prev:
                    pts.append(v)
                    prev = v
            if len(pts) < 3:
                continue
            d.append("M" + " ".join(f"{x},{y}" for x, y in pts) + "Z")
        paths.append("".join(d))
    return paths, boxes, height, to_view, scale


def quantiles(vals, qs):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return {q: None for q in qs}
    return {q: v[min(len(v) - 1, int(q * len(v)))] for q in qs}


def reference_stats(rows):
    """Region-wide reference points. Without these the assistant can say a
    number but not whether it is good, and 'high yield' with no baseline is
    the sort of claim that reads as insight and isn't."""
    priced = [r for r in rows if r["price"]]
    out = {}
    for key, field in [("price", "price"), ("yield", "yield"), ("rent", "rent"),
                       ("growth", "growth"), ("days", "days"), ("sold", "sold")]:
        q = quantiles([r[field] for r in priced], (0.25, 0.5, 0.75))
        out[key] = {"p25": q[0.25], "p50": q[0.5], "p75": q[0.75]}
    dens = [round(r["pop"] / r["area_km2"]) for r in priced
            if r.get("pop") and r.get("area_km2")]
    q = quantiles(dens, (0.25, 0.5, 0.75))
    out["density"] = {"p25": q[0.25], "p50": q[0.5], "p75": q[0.75]}
    return out


def history(rec):
    """Yearly price series -> [firstYear, [values in $1000]] (compact + enough
    resolution for a sparkline)."""
    pts = rec.get("price_history_yearly") or []
    pts = [p for p in pts if p.get("value")]
    if len(pts) < 5:
        return None
    return [int(pts[0]["date"][:4]),
            [int(round(p["value"] / 1000)) for p in pts]]


def main():
    prices = json.loads((RAW / "opes_suburbs.json").read_text())
    geo = json.loads((RAW / "auckland_boundaries.geojson").read_text())
    wiki = json.loads((RAW / "wikipedia.json").read_text())
    detail = json.loads((DATA / "suburb_detail.json").read_text())
    dsub = detail["suburbs"]
    # Loaded here with the rest of the raw inputs rather than where it is used,
    # so a missing rates file stops the run before it has written a CSV and a
    # join report that no longer match the page.
    rates = mortgage_rates()
    changes = recent_changes()
    as_at, last_updated = source_dates(prices)
    fetched = fetch_times()

    # Geography and typical section size come from the database, where the
    # spatial joins already happened.
    con = duckdb.connect(str(DATA / "auckland.duckdb"), read_only=True)
    con.execute("LOAD spatial;")
    geo_by_name = {r[0]: {"lb": r[1], "z": r[2], "km": r[3], "area": r[4]}
                   for r in con.execute(
                       "SELECT name, local_board, zone, cbd_km, area_km2 "
                       "FROM suburb").fetchall()}
    # Median section size, plus the share of the suburb that is a standalone
    # section at all. Bedroom mix hints at this; land area states it. A 0 m2
    # land area is a unit-title flat, which is exactly what someone asking for
    # a house with a yard does not want.
    land_by_name = {r[0]: {"la": r[1], "hs": r[2]} for r in con.execute("""
        SELECT s.name,
               median(r.land_area_m2) FILTER (
                   WHERE r.land_area_m2 BETWEEN 100 AND 5000)::INT AS land_median,
               round(count(*) FILTER (WHERE coalesce(r.land_area_m2, 0) >= 300)
                     / count(*)::DOUBLE, 3) AS house_share
        FROM rating_unit r JOIN suburb s USING (suburb_id)
        GROUP BY 1""").fetchall()}
    releases = [r[0] for r in con.execute(
        "SELECT DISTINCT source_as_at FROM market_snapshot ORDER BY 1 DESC LIMIT 2"
    ).fetchall()]
    con.close()

    by_name = {norm(p["suburb_name"]): p
               for p in prices if p["suburb_name"] not in DROP_SUBURBS}

    features = geo["features"]
    paths, boxes, height, to_view, scale_x = build_paths(features)

    w, s, e, n = URBAN_LONLAT
    ux0, uy0 = to_view(mercator(w, n))
    ux1, uy1 = to_view(mercator(e, s))
    urban_view = {"x": ux0, "y": uy0, "w": ux1 - ux0, "h": uy1 - uy0}

    used, rows = set(), []
    for feat, path, box in zip(features, paths, boxes):
        a = feat["properties"]
        key = norm(a.get("name_ascii") or a["name"])
        p = by_name.get(key) or by_name.get(ALIASES.get(key, ""))
        if p:
            key = norm(p["suburb_name"])
        if p:
            used.add(key)
        rows.append({
            "name": a["name"],
            "type": a["type"],
            "major": a.get("major_name") or "",
            "pop_linz": a.get("population_estimate"),
            "area_km2": None,   # filled from geo below
            "path": path,
            "box": box,
            "price": (p or {}).get("average_house_price"),
            "yoy": (p or {}).get("one_year_ago_price_change"),
            "growth": (p or {}).get("long_term_capital_growth"),
            "rent": (p or {}).get("median_rent"),
            "yield": (p or {}).get("estimated_yield"),
            "pop": (p or {}).get("population"),
            "days": (p or {}).get("median_days_to_sell"),
            "sold": (p or {}).get("sold_last_12_months"),
            "lat": (p or {}).get("latitude"),
            "lon": (p or {}).get("longitude"),
            "url": ("https://www.opespartners.co.nz/" + p["url"]) if p else None,
            "renters": (p or {}).get("renter_population_percentage"),
            "listed": (p or {}).get("listed_for_sale_last_month"),
            "days_rent": (p or {}).get("median_days_to_rent"),
            "beds": [(p or {}).get(f"{k}_bed_percentage")
                     for k in ("one", "two", "three", "four", "five")],
            "bedrent": [(p or {}).get(f"{k}_bedroom_rent")
                        for k in ("one", "two", "three", "four")],
            "hist": history(p) if p else None,
            "geo": geo_by_name.get(a["name"], {}),
            "land": land_by_name.get(a["name"]) or {},
            "wiki": wiki.get(a["name"]) or (wiki.get(p["suburb_name"]) if p else None),
            "detail": dsub.get(a["name"]),
        })

    for r in rows:
        r["area_km2"] = r["geo"].get("area")

    unmatched = [p["suburb_name"] for k, p in by_name.items() if k not in used]
    no_price = [r["name"] for r in rows if not r["price"]]
    priced = [r for r in rows if r["price"]]
    mid = median(r["price"] for r in priced)

    if len(releases) >= 2:
        changes["release"] = [str(releases[1]), str(releases[0])]
    elif releases:
        changes["release"] = [None, str(releases[0])]

    # ---- CSV -----------------------------------------------------------------
    DATA.mkdir(parents=True, exist_ok=True)
    cols = ["name", "type", "major", "price", "yoy", "growth", "rent", "yield",
            "pop", "days", "sold", "lat", "lon", "url"]
    with (DATA / "suburb_prices.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (-(r["price"] or 0), r["name"])):
            w.writerow(r)

    report = [
        f"LINZ polygons:            {len(rows)}",
        f"with a price:             {len(priced)}",
        f"without a price:          {len(no_price)}",
        f"price records dropped:    {sorted(DROP_SUBURBS)}",
        f"price records unmatched:  {unmatched}",
        f"median of suburb values:  ${mid:,.0f}",
        "",
        "Suburbs with no price data (rendered grey):",
        *(f"  {n}" for n in sorted(no_price)),
    ]
    (DATA / "join_report.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report[:6]))
    if len(priced) < MIN_PRICED:
        raise SystemExit(
            f"only {len(priced)} suburbs matched a price, expected >={MIN_PRICED}.\n"
            f"  unmatched price records: {unmatched}\n"
            f"  usually a LINZ rename — add it to ALIASES in this script.")

    # ---- payload for the page -------------------------------------------------
    def num(v, nd=None):
        if v is None:
            return None
        return round(v, nd) if nd is not None else v

    def opt(v):
        """The source uses 0 as a 'not available' sentinel on these fields
        (Saint Heliers reports 0 sales and 0 days to sell), so don't print it
        as if it were a measurement."""
        return v or None

    payload = {
        "viewW": VIEW_W,
        "viewH": round(height, 1),
        "urbanView": urban_view,
        # one view unit in metres, for the "each cell is ~N m" caption
        "metresPerUnit": round(111320 * math.cos(math.radians(-36.9)) / scale_x, 3),
        "midPrice": mid,
        "regionSaleMedian": REGION_SALE_MEDIAN,
        "asAt": as_at,
        "lastUpdated": last_updated,
        # UTC with an offset, not a naive local clock. A build on this laptop
        # stamped 13:29 and the next one in CI stamped 01:35, six minutes
        # later — the same instant twelve hours apart on the page, and no way
        # for a reader to tell which. The page renders it in their own zone.
        "built": {"at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                  "sources": fetched},
        "rampLight": ramp_lut(RAMP_LIGHT),
        "rampDark": ramp_lut(RAMP_DARK),
        "ref": reference_stats(rows),
        # Set AKL_AGENT_PROXY to a deployed ops/worker URL to offer the model
        # without visitors needing their own key. Empty = the option is absent.
        "proxy": os.environ.get("AKL_AGENT_PROXY", ""),
        "fin": {"m": rates, "c": COUNCIL},
        "changed": changes,
        "valuationDate": detail["valuationDate"],
        "prevValuationDate": detail["prevValuationDate"],
        "unitsMatched": detail["unitsMatched"],
        "suburbs": [{
            "n": r["name"],
            "d": r["path"],
            "bx": r["box"],
            "p": r["price"],
            "y": num(r["yoy"] * 100 if r["yoy"] is not None else None, 2),
            "g": num(opt(r["growth"]), 2),
            "r": opt(r["rent"]),
            "i": num(opt(r["yield"]), 2),
            "o": opt(r["pop"]),
            "s": opt(r["days"]),
            "c": opt(r["sold"]),
            "t": r["type"],
            "rp": num(opt(r["renters"]), 1),
            "lf": opt(r["listed"]),
            "dr": opt(r["days_rent"]),
            "bm": [num(opt(v), 1) for v in r["beds"]] if any(r["beds"]) else None,
            "br": r["bedrent"] if any(r["bedrent"]) else None,
            "h": r["hist"],
            "w": r["wiki"],
            "dt": r["detail"],
            "lb": r["geo"].get("lb"),
            "z": r["geo"].get("z"),
            "km": r["geo"].get("km"),
            "la": r["land"].get("la"),
            "hs": r["land"].get("hs"),
            "ar": r["geo"].get("area"),
        } for r in sorted(rows, key=lambda r: r["name"])],
    }

    # .tpl, not .html: on its own the template renders a blank page (the data
    # slot is still a placeholder), so keep it out of double-click range.
    tpl = (ROOT / "scripts" / "heatmap_template.html.tpl").read_text()
    body = tpl.replace("/*__DATA__*/null",
                       json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    # Two outputs from one template: a standalone file to open locally, and a
    # body-only copy for the Artifact publisher (which supplies its own <head>).
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "heatmap_body.html").write_text(body)

    # Write then rename, so a scheduled rebuild never leaves a half-written
    # page for whoever has it open in a browser tab.
    # Slice-based edits to the template have twice deleted functions that
    # happened to sit between the anchors. Syntax stays valid, so it only
    # surfaces at runtime — check the names are all still there.
    required = ["figuresCheckOut", "claimsCheckOut", "HARD_BLOCK", "SOFT_SOURCE",
                "smoothField", "fieldImage", "drawDetailMap", "enterDetail",
                "scoreSuburb", "prosCons", "askModel", "detectLang", "applyLang",
                "repayment", "councilRates", "calcCard", "renderCalcOut",
                "seedCalc", "calcPanel", "readIntent", "renderAssess", "changesLine",
                "provenance", "monthLabel", "freshness",
                "renderCompare", "explainAnswer", "assessBlock"]
    missing = [n for n in required
               if f"function {n}" not in body and f"const {n}" not in body]
    if missing:
        raise SystemExit(f"template is missing: {', '.join(missing)}")

    out = ROOT / "heatmap.html"
    tmp = out.with_suffix(".html.building")
    tmp.write_text('<!doctype html>\n<html lang="zh-CN">\n<head>\n'
                   '<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
                   + body + "\n</html>\n")
    os.replace(tmp, out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()

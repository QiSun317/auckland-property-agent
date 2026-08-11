#!/usr/bin/env python3
"""Aggregate rating-unit valuations into the per-suburb detail grids.

Reads from data/auckland.duckdb, so the point-in-polygon assignment happens
once (in build_db.py) rather than again here. Run build_db.py first.

Within a suburb the units are binned onto a ~35 m square grid and each cell
keeps the median capital value. That also collapses cross-lease flats, which
all share one parcel centroid.


Output: data/suburb_detail.json
"""
import base64
import json
import math
import os
import struct
from collections import defaultdict
from pathlib import Path
from statistics import median

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
DB = Path(os.environ.get("AKL_DB", DATA / "auckland.duckdb"))

VIEW_W = 3000.0            # must match build_map.py
CELL_M = 35.0              # target cell size in metres (~one house frontage)
GRID_MAX = 200             # but never more cells than this on a suburb's long side
FILL_PASSES = 2            # gap-filling passes (roads, driveways, small reserves)
FILL_MIN_NEIGHBOURS = 3
IDX = 0.01                 # spatial index cell size, degrees (~1 km)
MIN_CV = 50_000            # below this it's a car park / utility lot, not a home
HIST_BINS = 24

VALUATION_DATE = "2024-05-01"
PREV_VALUATION_DATE = "2021-06-01"


# --- projection (same Web Mercator framing as build_map.py) -------------------
def mercator(lon, lat):
    return lon, math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def rings_of(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    return [r for poly in geom["coordinates"] for r in poly]


def point_in_rings(x, y, rings):
    """Even-odd ray cast over every ring, so holes fall out for free."""
    inside = False
    for ring in rings:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y):
                if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
            j = i
    return inside


def main():
    geo = json.loads((RAW / "auckland_boundaries.geojson").read_text())
    feats = geo["features"]

    # --- view-unit transform (identical to build_map.py) ----------------------
    pxs, pys = [], []
    for f in feats:
        for r in rings_of(f["geometry"]):
            for lon, lat in r:
                mx, my = mercator(lon, lat)
                pxs.append(mx)
                pys.append(my)
    minx, maxx, miny, maxy = min(pxs), max(pxs), min(pys), max(pys)
    scale = VIEW_W / (maxx - minx)
    metres_per_unit = 111320 * math.cos(math.radians(-36.9)) / scale
    print(f"1 view unit = {metres_per_unit:.2f} m")

    def to_view(lon, lat):
        mx, my = mercator(lon, lat)
        return (mx - minx) * scale, (maxy - my) * scale

    # --- points come pre-assigned to a suburb by build_db.py ------------------
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("LOAD spatial;")
    dates = con.execute("""
        SELECT max(valuation_date) AS cur,
               max(valuation_date) FILTER (
                   WHERE valuation_date < (SELECT max(valuation_date) FROM valuation)
               ) AS prev
        FROM valuation""").fetchone()
    cur_date, prev_date = dates
    print(f"valuations: current {cur_date}, previous {prev_date}")

    rows = con.execute(f"""
        SELECT s.name, r.lon, r.lat, c.cv AS cv_now,
               coalesce(p.cv, 0) AS cv_prev
        FROM rating_unit r
        JOIN suburb s USING (suburb_id)
        JOIN valuation c ON c.ru_id = r.ru_id AND c.valuation_date = DATE '{cur_date}'
        LEFT JOIN valuation p ON p.ru_id = r.ru_id
                             AND p.valuation_date = DATE '{prev_date}'
        WHERE c.cv >= {MIN_CV}
    """).fetchall()
    con.close()

    buckets = defaultdict(list)
    for name, lon, lat, cv_now, cv_prev in rows:
        vx, vy = to_view(lon, lat)
        buckets[name].append((vx, vy, cv_now, cv_prev))
    matched = len(rows)
    print(f"{matched:,} rating units over {len(buckets)} suburbs")

    # --- per suburb: grid + summary ------------------------------------------
    out = {}
    total_cells = 0
    for name, pts in buckets.items():
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)

        cell = CELL_M / metres_per_unit
        if max(w, h) / cell > GRID_MAX:
            cell = max(w, h) / GRID_MAX
        nx = max(1, min(GRID_MAX, math.ceil(w / cell)))
        ny = max(1, min(GRID_MAX, math.ceil(h / cell)))

        grid = defaultdict(list)
        for vx, vy, lcv, _cv in pts:
            gx = min(nx - 1, int((vx - x0) / cell))
            gy = min(ny - 1, int((vy - y0) / cell))
            grid[(gx, gy)].append(lcv)
        cells = {k: median(v) for k, v in grid.items()}
        measured = len(cells)

        # Roads, driveways and small reserves hold no rating unit, which leaves
        # a fine grid looking like scattered dots rather than a surface. Fill a
        # gap only where enough neighbours agree on what belongs there.
        for _ in range(FILL_PASSES):
            add = {}
            for gx in range(nx):
                for gy in range(ny):
                    if (gx, gy) in cells:
                        continue
                    near = [cells[(gx + dx, gy + dy)]
                            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                            if (dx or dy) and (gx + dx, gy + dy) in cells]
                    if len(near) >= FILL_MIN_NEIGHBOURS:
                        add[(gx, gy)] = median(near)
            if not add:
                break
            cells.update(add)

        blob = bytearray()
        for (gx, gy), v in sorted(cells.items()):
            blob += struct.pack("<BBH", gx, gy, min(65535, int(round(v / 1000))))
        total_cells += len(cells)

        lcvs = sorted(p[2] for p in pts)
        n = len(lcvs)

        def q(f):
            return lcvs[min(n - 1, int(f * n))]

        changes = sorted((p[2] - p[3]) / p[3] for p in pts if p[3] > 0)
        # Log-spaced bins: property values are strongly right-skewed, and linear
        # bins put nearly everything in the first bar with a long empty tail.
        lo, hi = max(q(0.02), 1), max(q(0.98), 2)
        span = math.log(hi / lo)
        hist = [0] * HIST_BINS
        for v in lcvs:
            k = int(math.log(max(v, 1) / lo) / span * HIST_BINS) if span > 0 else 0
            hist[max(0, min(HIST_BINS - 1, k))] += 1

        out[name] = {
            "bb": [round(x0, 1), round(y0, 1), round(w, 1), round(h, 1)],
            "nx": nx, "ny": ny, "cs": round(cell, 4),
            "measured": measured,
            "cells": base64.b64encode(bytes(blob)).decode("ascii"),
            "n": n,
            "med": q(0.5),
            "q": [q(0.1), q(0.25), q(0.5), q(0.75), q(0.9)],
            "chg": round(changes[len(changes) // 2], 4) if changes else None,
            "hist": hist, "histLo": lo, "histHi": hi,
        }

    payload = {
        "valuationDate": str(cur_date),
        "prevValuationDate": str(prev_date),
        "unitsMatched": matched,
        "suburbs": out,
    }
    path = DATA / "suburb_detail.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(out)} suburbs | {total_cells:,} grid cells | "
          f"{path.stat().st_size / 1e6:.2f} MB -> {path}")


if __name__ == "__main__":
    main()

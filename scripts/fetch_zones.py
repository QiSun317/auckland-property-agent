#!/usr/bin/env python3
"""Download Auckland Unitary Plan base zone polygons (Auckland Council, CC BY 4.0).

The zone is the join that makes the plan text answerable. A question like "can
I subdivide this section" needs two different lookups: which zone the parcel is
in, which is geometry, and what that zone permits, which is prose in the plan.
This fetches the first half. Without it the plan chapters are a pile of rules
with nothing to attach them to.

Two things about this layer will produce confidently wrong answers if ignored:

  * `NAME` is not the zone. It holds a place label — school names, bays,
    suburbs, and 300-odd nulls. The zone lives in `ZONE`, a coded integer, and
    its coarser parent in `GROUPZONE`. Reading `NAME` as the zone is the
    obvious mistake and it fails quietly, because the values look plausible.
  * `VERSIONSTATUS` separates what is operative from what is merely proposed
    or still under appeal. Only 16 of 139,432 polygons are not operative,
    which is exactly the ratio that makes skipping the filter tempting and
    makes the resulting error invisible until it lands on someone's section.

The code -> name dictionaries are read from the service at run time rather than
pinned here. The council adds zones — codes 70-72 arrived with the medium
density rules — and a hardcoded table would not fail on a new code, it would
map it to nothing and drop the polygon.

Output: data/raw/unitary_plan_zones.geojson.gz  (WGS84, zone names decoded)
        data/raw/unitary_plan_zones_report.txt  (what was excluded, and why)
"""
import gzip
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
OUT = Path(os.environ.get("AKL_OUT_DIR", RAW))

SERVICE = ("https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services/"
           "Unitary_Plan_Base_Zone/FeatureServer/0")
LAYER = SERVICE + "/query"

# 4 = Operative. Anything else is proposed, notified, or under appeal: real
# enough to appear on the council's own map, not real enough to plan against.
OPERATIVE = 4
# The domain keeps retired codes addressable so old records still decode.
DELETED_ZONE = 58

PAGE = 1000
WORKERS = 6
# ~0.1 m. Unlike the suburb choropleth, this geometry decides which side of a
# zone boundary a parcel falls on, so it is not simplified.
PRECISION = 6

_lock = threading.Lock()


def get(url, params, tries=4):
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(full, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def domains():
    """code -> name for every coded field, straight from the service."""
    meta = get(SERVICE, {"f": "json"})
    out = {}
    for f in meta.get("fields", []):
        dom = f.get("domain") or {}
        if dom.get("type") == "codedValue":
            out[f["name"]] = {cv["code"]: cv["name"] for cv in dom["codedValues"]}
    missing = {"ZONE", "GROUPZONE", "VERSIONSTATUS"} - set(out)
    if missing:
        sys.exit(f"service no longer publishes domains for {sorted(missing)} — "
                 "the decode below would silently produce nulls")
    return out


def count(where):
    return get(LAYER, {"where": where, "returnCountOnly": "true", "f": "json"})["count"]


def page(offset, where):
    return get(LAYER, {
        "where": where,
        "outFields": "OBJECTID,NAME,ZONE,GROUPZONE",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": PRECISION,
        "orderByFields": "OBJECTID",
        "resultOffset": offset,
        "resultRecordCount": PAGE,
        "f": "geojson",
    }).get("features", [])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dom = domains()
    zone_name = dom["ZONE"]
    group_name = dom["GROUPZONE"]
    status_name = dom["VERSIONSTATUS"]

    where = f"VERSIONSTATUS={OPERATIVE} AND ZONE<>{DELETED_ZONE}"
    total_all = count("1=1")
    n = count(where)
    print(f"{n:,} operative zone polygons ({total_all - n:,} excluded of {total_all:,})")

    offsets = list(range(0, n + PAGE, PAGE))
    done = [0]

    def work(off):
        rows = page(off, where)
        with _lock:
            done[0] += 1
            if done[0] % 10 == 0 or done[0] == len(offsets):
                print(f"  {done[0]}/{len(offsets)} pages", flush=True)
        return rows

    # A code the domain does not describe is a new zone, not a bad row. Keep the
    # polygon, label it by its code, and say so at the end rather than dropping
    # a chunk of the region on the floor because the dictionary aged out.
    unknown = {}
    out = OUT / "unitary_plan_zones.geojson.gz"
    written = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool, \
            gzip.open(out, "wt", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","features":[\n')
        for rows in pool.map(lambda o: work(o), offsets):
            for f in rows:
                p = f.get("properties") or {}
                if not f.get("geometry"):
                    continue
                z, g = p.get("ZONE"), p.get("GROUPZONE")
                if z not in zone_name:
                    unknown[z] = unknown.get(z, 0) + 1
                f["properties"] = {
                    "zone_code": z,
                    "zone": zone_name.get(z, f"UNKNOWN ({z})"),
                    "group_code": g,
                    "group_zone": group_name.get(g, f"UNKNOWN ({g})"),
                    # kept because the council publishes it, not because it
                    # means anything about the zone
                    "place_name": (p.get("NAME") or "").strip() or None,
                }
                fh.write(("," if written else "")
                         + json.dumps(f, separators=(",", ":")) + "\n")
                written += 1
        fh.write("]}\n")

    # What was left out, in a file, because a filter nobody can see is a filter
    # nobody will remember when the numbers look odd six months from now.
    excluded = []
    for code, label in sorted(status_name.items()):
        if code == OPERATIVE:
            continue
        c = count(f"VERSIONSTATUS={code}")
        if c:
            excluded.append(f"  VERSIONSTATUS={code:<3} {label:<40} {c:>6,}")
    deleted = count(f"ZONE={DELETED_ZONE}")

    report = OUT / "unitary_plan_zones_report.txt"
    report.write_text(
        "Auckland Unitary Plan base zone — fetch report\n"
        f"source: {SERVICE}\n"
        f"licence: CC BY 4.0, Auckland Council\n\n"
        f"kept    {written:,} operative polygons\n"
        f"of      {total_all:,} published\n\n"
        "excluded — not operative:\n"
        + ("\n".join(excluded) if excluded else "  (none)")
        + f"\n\nexcluded — retired zone code {DELETED_ZONE} (DELETED): {deleted:,}\n\n"
        "zone codes seen but not in the service's own domain:\n"
        + ("\n".join(f"  {k}: {v:,} polygons" for k, v in sorted(unknown.items()))
           if unknown else "  (none)")
        + "\n", encoding="utf-8")

    print(f"wrote {written:,} polygons -> {out} "
          f"({out.stat().st_size / 1e6:.1f} MB gzipped)")
    print(f"       exclusions -> {report}")
    if unknown:
        print(f"WARNING: {sum(unknown.values()):,} polygons carry zone codes the "
              f"service does not define: {sorted(unknown)}", file=sys.stderr)
    if written < n * 0.98:
        print(f"WARNING: expected ~{n:,}, got {written:,}", file=sys.stderr)


if __name__ == "__main__":
    main()

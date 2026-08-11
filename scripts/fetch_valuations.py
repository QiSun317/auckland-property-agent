#!/usr/bin/env python3
"""Download Auckland Council rating valuations (one row per rating unit).

The council's AGOL_RateAccountInfo1_gdb service exposes, per rating unit:
  CV  / LV   -> the 2021-06-01 valuation (the one rates are currently struck on)
  LCV / LLV  -> the 2024-05-01 revaluation (the most recent)
We take centroids rather than parcel polygons: 620k polygons would be hundreds
of megabytes, and a point per rating unit is all either the detail map or a
"what is this place worth" lookup needs.

Output: data/raw/valuations.jsonl.gz, one JSON object per rating unit
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

LAYER = ("https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services/"
         "AGOL_RateAccountInfo1_gdb/FeatureServer/0/query")
PAGE = 2000
WORKERS = 8

_lock = threading.Lock()


def query(params, tries=4):
    url = LAYER + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        except Exception as exc:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def total():
    return query({"where": "LCV>0", "returnCountOnly": "true", "f": "json"})["count"]


def page(offset):
    data = query({
        "where": "LCV>0",
        "outFields": "VALUATIONREF,FORMATTEDADDRESS,AREALABEL,CV,LV,LCV,LLV",
        "returnGeometry": "false",
        "returnCentroid": "true",
        "outSR": "4326",
        "orderByFields": "OBJECTID",
        "resultOffset": offset,
        "resultRecordCount": PAGE,
        "f": "json",
    })
    out = []
    for f in data.get("features", []):
        c = f.get("centroid")
        if not c or c.get("x") is None:
            continue
        a = f["attributes"]
        out.append({
            "ref": a.get("VALUATIONREF"),
            # the address arrives as "street\rsuburb\rcity postcode"
            "addr": (a.get("FORMATTEDADDRESS") or "").replace("\r", ", "),
            "area": a.get("AREALABEL"),
            "x": round(c["x"], 6), "y": round(c["y"], 6),
            "cv": a.get("CV"), "lv": a.get("LV"),
            "lcv": a.get("LCV"), "llv": a.get("LLV"),
        })
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = total()
    offsets = list(range(0, n + PAGE, PAGE))
    print(f"{n:,} rating units -> {len(offsets)} pages")

    done = [0]

    def work(off):
        rows = page(off)
        with _lock:
            done[0] += 1
            if done[0] % 25 == 0 or done[0] == len(offsets):
                print(f"  {done[0]}/{len(offsets)} pages", flush=True)
        return rows

    out = OUT / "valuations.jsonl.gz"
    written = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool, \
            gzip.open(out, "wt", encoding="utf-8") as fh:
        for rows in pool.map(work, offsets):
            for r in rows:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
                written += 1

    print(f"wrote {written:,} rows -> {out} "
          f"({out.stat().st_size / 1e6:.1f} MB gzipped)")
    if written < n * 0.98:
        print(f"WARNING: expected ~{n:,}, got {written:,}", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Download Auckland Council local board boundaries (21 areas).

Suburb names alone can't answer "somewhere on the North Shore" or "east
Auckland". Local boards are the division Aucklanders actually use, and they
are small enough (21) to assign every suburb to one by centroid.

Output: data/raw/local_boards.geojson (WGS84, generalised)
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
OUT = Path(os.environ.get("AKL_OUT_DIR", RAW))

LAYER = ("https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services/"
         "Local_Board_boundaries_view/FeatureServer/0/query")
OFFSET_DEG = 0.0005      # ~55 m; only used to name areas, never drawn


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    params = {
        "where": "1=1",
        "outFields": "BOARD,WARD",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": OFFSET_DEG,
        "geometryPrecision": 5,
        "f": "geojson",
    }
    url = LAYER + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                fc = json.loads(resp.read().decode("utf-8"))
            break
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

    out = OUT / "local_boards.geojson"
    out.write_text(json.dumps(fc))
    print(f"wrote {len(fc['features'])} local boards -> {out} "
          f"({out.stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()

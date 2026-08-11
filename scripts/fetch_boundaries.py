#!/usr/bin/env python3
"""Download Auckland suburb/locality polygons from the LINZ 'NZ Suburbs and
Localities' feature service (published by LINZ on ArcGIS Online, CC BY 4.0).

Output: data/raw/auckland_boundaries.geojson (WGS84, generalised)
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

LAYER = ("https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/"
         "LINZ_NZ_Suburbs_and_Localities/FeatureServer/0/query")

# territorial_authority is a comma-joined list for areas that straddle a TA
# boundary (e.g. Pukekohe is "Auckland, Waikato District"), so match on LIKE.
WHERE = ("territorial_authority LIKE '%Auckland%' "
         "AND type IN ('Suburb','Locality')")
FIELDS = "id,name,name_ascii,type,major_name,territorial_authority,population_estimate"
# ~22 m of simplification: plenty of detail for a regional choropleth, but
# keeps the payload small enough to inline into a single HTML file.
OFFSET_DEG = 0.0002
PAGE = 40


def fetch(params, tries=3):
    url = LAYER + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    features, offset = [], 0
    while True:
        data = fetch({
            "where": WHERE,
            "outFields": FIELDS,
            "returnGeometry": "true",
            "outSR": "4326",
            "maxAllowableOffset": OFFSET_DEG,
            "geometryPrecision": 5,
            "resultOffset": offset,
            "resultRecordCount": PAGE,
            "f": "geojson",
        })
        batch = data.get("features", [])
        features.extend(batch)
        print(f"  +{len(batch)} (total {len(features)})")
        if len(batch) < PAGE:
            break
        offset += PAGE

    fc = {"type": "FeatureCollection", "features": features}
    out = OUT / "auckland_boundaries.geojson"
    out.write_text(json.dumps(fc))
    print(f"wrote {len(features)} polygons -> {out} "
          f"({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

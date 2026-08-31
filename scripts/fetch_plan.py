#!/usr/bin/env python3
"""Download the Auckland Unitary Plan chapters that answer "what can I do here".

fetch_zones.py established which zone a parcel is in. This fetches the other
half: what that zone permits. The two only meet because the plan's chapter
numbering and the zone layer's coded domain describe the same objects — H5 *is*
Residential - Mixed Housing Urban Zone, which is zone code 60 — so the mapping
below is not a guess to be recovered by search at query time. It is data, and
build_plan.py checks it against the database rather than trusting it.

That matters more than it sounds. Retrieval that has to *find* the right
chapter can return H4 for an H5 question and read plausibly; retrieval that is
told the chapter cannot. The zone lookup is exact, so the chapter should be too,
and the vectors only decide which clause within it.

Scope is every zone chapter that a rating unit in this database can land in,
plus the region-wide chapters on subdivision and natural hazards. Adding a
chapter is one line in CHAPTERS; the one gap left is the Hauraki Gulf Islands
(zone code 43, 8,327 parcels), which is governed by its own district plan
rather than by a chapter of this one, and so is a refusal the agent has to be
able to give rather than a file that can be fetched.

Output: data/raw/plan/*.pdf, plus plan_index.json recording what was fetched
        (url, bytes, sha256, zone codes) so build_plan.py never has to guess.
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
# The pipeline stages fetches in data/incoming and promotes them only after the
# gate passes, so honour AKL_OUT_DIR the way the other fetchers do. This source
# is a directory rather than one file; pipeline.py promotes it as a unit.
OUT = Path(os.environ.get("AKL_PLAN_DIR",
                          Path(os.environ.get("AKL_OUT_DIR", RAW)) / "plan"))

BASE = ("https://unitaryplan.aucklandcouncil.govt.nz/images/"
        "Auckland%20Unitary%20Plan%20Operative")

# (clause prefix, folder, file stem, zone codes this chapter governs)
#
# The zone codes are from the council's own dUPZone domain — the same numbers
# planning_zone.zone_code holds — so a parcel resolves to a chapter with a join
# and no string matching. An empty tuple means the chapter applies region-wide
# rather than to one zone.
ZONES_DIR = "Chapter H Zones"
WIDE = "Chapter E Auckland-wide"

# The zones E39.1 lists by name as its own. Everything else subdivides under
# E38. Quarry (51) is here because the plan puts it here, even though no zone
# chapter for it is fetched.
RURAL_SUBDIVISION = (16, 11, 46, 15, 3, 68, 69, 4, 51)

# (clause prefix, folder, file stem, zone codes, [zone codes excluded])
CHAPTERS = [
    # Residential
    ("H1",  ZONES_DIR, "H1 Residential - Large Lot Zone", (23,)),
    ("H2",  ZONES_DIR, "H2 Residential - Rural and Coastal Settlement Zone", (20,)),
    ("H3",  ZONES_DIR, "H3 Residential - Single House Zone", (19,)),
    ("H4",  ZONES_DIR, "H4 Residential - Mixed Housing Suburban Zone", (18,)),
    ("H5",  ZONES_DIR, "H5 Residential - Mixed Housing Urban Zone", (60,)),
    ("H6",  ZONES_DIR,
     "H6 Residential - Terrace Housing and Apartment Buildings Zone", (8,)),
    # Open space
    ("H7",  ZONES_DIR, "H7 Open Space zones", (62, 34, 31, 32, 33)),
    # Business
    ("H8",  ZONES_DIR, "H8 Business - City Centre Zone", (35,)),
    ("H9",  ZONES_DIR, "H9 Business - Metropolitan Centre Zone", (10,)),
    ("H10", ZONES_DIR, "H10 Business - Town Centre Zone", (22,)),
    ("H11", ZONES_DIR, "H11 Business - Local Centre Zone", (7,)),
    ("H12", ZONES_DIR, "H12 Business - Neighbourhood Centre Zone", (44,)),
    ("H13", ZONES_DIR, "H13 Business - Mixed Use Zone", (12,)),
    ("H14", ZONES_DIR, "H14 Business - General Business Zone", (49,)),
    ("H15", ZONES_DIR, "H15 Business - Business Park Zone", (1,)),
    ("H16", ZONES_DIR, "H16 Business - Heavy Industry Zone", (5,)),
    ("H17", ZONES_DIR, "H17 Business - Light Industry Zone", (17,)),
    # Future urban and rural. H19 covers five rural zones in one chapter, which
    # is why zone_codes is a list rather than one code per file.
    ("H18", ZONES_DIR, "H18 Future Urban Zone", (4,)),
    ("H19", ZONES_DIR, "H19 Rural zones", (3, 11, 15, 16, 46)),
    # The plan text spells these Waitākere; the file names drop the macron.
    ("H20", ZONES_DIR, "H20 Rural - Waitakere Foothills Zone", (68,)),
    ("H21", ZONES_DIR, "H21 Rural - Waitakere Ranges Zone", (69,)),
    # Region-wide chapters. Natural hazards is the one people ask about
    # without knowing its name — flooding, coastal inundation and land
    # instability all live in E36 — and it genuinely applies everywhere.
    ("E36", f"{WIDE}/5. Environmental risk", "E36 Natural hazards and flooding", ()),
    # Subdivision is not region-wide, and treating it as though it were is the
    # mistake that cost this corpus three eval cases outright: asked the
    # minimum site size for an urban section, retrieval kept answering out of
    # the rural chapter, which is in scope for nothing of the sort and is
    # worded almost identically.
    #
    # The chapters say where they apply, so the split is theirs, not a guess.
    # E39.1: "apply to subdivision in the following zones" — the nine below.
    # E38.1: "apply to subdivision in all zones except" — the same nine. So
    # E38 is a complement, and is stored as one rather than enumerated, which
    # keeps it right when the council adds a zone.
    ("E38", f"{WIDE}/6. Subdivision", "E38 Subdivision - Urban", (), RURAL_SUBDIVISION),
    ("E39", f"{WIDE}/6. Subdivision", "E39 Subdivision - Rural", RURAL_SUBDIVISION),
]


def get(url, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as resp:
                return resp.read()
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index, failed = [], []

    for clause, folder, stem, zones, *rest in CHAPTERS:
        excluded = rest[0] if rest else ()
        url = f"{BASE}/{urllib.parse.quote(folder)}/{urllib.parse.quote(stem)}.pdf"
        dest = OUT / f"{clause}.pdf"
        try:
            body = get(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  {clause:<4} FAILED  {exc}", file=sys.stderr)
            failed.append(clause)
            continue
        # A 404 from this host comes back as a small HTML error page with a 200
        # on some paths, so check the magic bytes rather than the status code.
        if not body.startswith(b"%PDF"):
            print(f"  {clause:<4} FAILED  not a PDF ({len(body)} bytes)", file=sys.stderr)
            failed.append(clause)
            continue
        dest.write_bytes(body)
        index.append({
            "clause": clause,
            "title": stem,
            "zone_codes": list(zones),
            "excluded_zone_codes": list(excluded),
            "url": url,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "file": dest.name,
        })
        print(f"  {clause:<4} {len(body) / 1e6:>5.2f} MB  {stem}")

    (OUT / "plan_index.json").write_text(
        json.dumps({
            "source": "Auckland Unitary Plan (Operative in Part), Auckland Council",
            "base": BASE,
            "chapters": index,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(c["bytes"] for c in index)
    print(f"wrote {len(index)} chapters ({total / 1e6:.1f} MB) -> {OUT}")
    if failed:
        sys.exit(f"{len(failed)} chapter(s) could not be fetched: {failed}")


if __name__ == "__main__":
    main()

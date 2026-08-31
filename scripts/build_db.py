#!/usr/bin/env python3
"""Load the validated raw snapshot in data/raw into data/auckland.duckdb.

This is written to be run repeatedly, once a month. The rules that follow from
that:

  * market_snapshot and valuation are APPEND-ONLY, keyed on the source's own
    release date. Re-running on unchanged input inserts nothing; a new release
    adds one row per suburb and leaves the old ones alone. The accumulating
    history is the point of a monthly job.
  * suburb and rating_unit are slowly-changing reference data and get rebuilt,
    but first_seen carries across so we keep knowing when a parcel appeared.
  * Each run builds a NEW file and atomically replaces the old one. DuckDB
    rewrites a table wholesale on CREATE OR REPLACE and never reclaims the old
    blocks, so building in place grew the file ~20 MB per no-op run. Rebuilding
    also means a reader holding the old file keeps a consistent view until the
    swap, which matters because DuckDB's write lock excludes readers.
  * Valuations are stored long (one row per unit per valuation round) rather
    than as cv_2021/cv_2024 columns, so the next revaluation is an INSERT
    instead of a schema migration.

The database is a derived artefact: data/raw is the source of truth and this
file can be deleted and rebuilt at any time.
"""
import gzip
import json
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import date, datetime
from pathlib import Path

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
# What a clean checkout carries instead of the database itself.
STATE = Path(os.environ.get("AKL_STATE_DB",
                            DATA / "state" / "history.duckdb.gz"))

VALUATION_ROUNDS = {"cv_2021": "2021-06-01", "cv_2024": "2024-05-01"}

# Britomart, for "how far out is this" distances.
CBD = (174.7645, -36.8443)

# Distances and areas go through NZTM (EPSG:2193, metres) rather than the
# ST_*_Spheroid family. Those functions follow EPSG:4326's declared axis order,
# which is (lat, lon) — feed them the (lon, lat) points everything else uses and
# ST_Area_Spheroid returns NaN while ST_Distance_Sphere silently returns a
# plausible-looking wrong number. always_xy pins the input order explicitly.
TO_NZTM = "ST_Transform({}, 'EPSG:4326', 'EPSG:2193', always_xy := true)"

# Unitary Plan base zones held back to a second pass when a parcel falls in
# more than one. Two independent reasons pick out the same four, which is why
# one pass can serve both.
#
# Semantically they are subordinate. The General Coastal Marine Zone governs
# the water below mean high water springs and is drawn over the coastal land
# zones rather than beside them, so a parcel matching it *and* a land zone is
# in the land zone. That single overlap explains every one of the 8,833 double
# matches in this data — 8,327 of them Hauraki Gulf Islands — and deferring it
# leaves zero parcels ambiguous. Road, Water and the transport corridor are the
# same shape of thing: real answers when they are the only answer, never the
# answer when a land zone is also on offer.
#
# Geometrically they are the expensive ones. A coastal polygon's bounding box
# spans the gulf, so the R-tree prunes nothing and the exact test runs against
# thousands of vertices. Held back, the other 55,004 polygons resolve 621,650
# parcels in 1.4 s.
#
# Not to be confused with ZONES below, which is a geographic grouping of local
# boards and has nothing to do with the plan.
DEFERRED_ZONES = (27, 25, 30, 26)   # Road, Water, General Coastal Marine,
                                    # Strategic Transport Corridor

# The 21 local boards grouped the way Aucklanders actually talk about the city.
ZONES = {
    "北岸": ["Hibiscus and Bays", "Upper Harbour", "Kaipatiki", "Devonport - Takapuna"],
    "西区": ["Henderson - Massey", "Waitakere Ranges", "Whau"],
    "中区": ["Waitemata", "Albert - Eden", "Puketapapa", "Orakei",
             "Maungakiekie - Tamaki"],
    "东区": ["Howick"],
    "南区": ["Mangere - Otahuhu", "Otara - Papatoetoe", "Manurewa", "Papakura",
             "Franklin"],
    "北部乡村": ["Rodney"],
    "海岛": ["Waiheke", "Great Barrier"],
}
BOARD_ZONE = {b: z for z, bs in ZONES.items() for b in bs}


# The same polygon under a new LINZ label, keyed by norm(). norm() folds
# accents, case and St/Mt, which covers the fifteen macrons LINZ added in
# August 2026 (Orakei -> Ōrākei); it cannot cover a suffix appearing, and those
# quietly drop a suburb out of the price join. build_map imports this so the
# database and the page can never disagree about which suburbs are priced —
# they did, by two, until this moved out of build_map.
ALIASES = {
    "muriwaibeach": "muriwai",              # LINZ renamed, Opes still Muriwai
    "manukaucitycentre": "manukau",
    "mahurangi": "mahurangieast",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bmount\b", "mt", s)
    return re.sub(r"[^a-z0-9]", "", s)


def area_m2(label):
    """AREALABEL arrives as '711 M2' / '1.2 HA' / '0 M2' (cross-lease flats)."""
    if not label:
        return None
    m = re.match(r"\s*([\d.]+)\s*(M2|HA)\s*$", label, re.I)
    if not m:
        return None
    v = float(m.group(1))
    return round(v * 10_000 if m.group(2).upper() == "HA" else v, 1) or None


def source_as_at(prices):
    """The source's own release date keys the snapshot, so re-running against
    unchanged data is a no-op rather than a duplicate row."""
    for p in prices:
        if p.get("last_updated"):
            return p["last_updated"]
    return date.today().isoformat()


def stage_valuations(tmp):
    n = 0
    with gzip.open(RAW / "valuations.jsonl.gz", "rt", encoding="utf-8") as fin, \
            gzip.open(tmp, "wt", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            fout.write(json.dumps({
                "valuation_ref": r.get("ref"),
                "address": r.get("addr") or None,
                "land_area_m2": area_m2(r.get("area")),
                "lon": r["x"], "lat": r["y"],
                "cv_2021": r.get("cv") or None, "lv_2021": r.get("lv") or None,
                "cv_2024": r.get("lcv") or None, "lv_2024": r.get("llv") or None,
            }, separators=(",", ":")) + "\n")
            n += 1
    return n


def ensure_schema(con):
    con.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_run (
        run_id BIGINT PRIMARY KEY, started_at TIMESTAMP, finished_at TIMESTAMP,
        trigger TEXT, status TEXT, note TEXT);

    CREATE TABLE IF NOT EXISTS pipeline_step (
        run_id BIGINT, source TEXT, started_at TIMESTAMP, finished_at TIMESTAMP,
        status TEXT, source_hash TEXT, rows BIGINT, message TEXT);

    CREATE TABLE IF NOT EXISTS market_snapshot (
        suburb_id INTEGER, source_as_at DATE, captured_at TIMESTAMP, run_id BIGINT,
        avg_house_value BIGINT, value_1y_ago BIGINT, change_1y DOUBLE,
        value_2y_ago BIGINT, change_2y DOUBLE,
        long_term_growth_pct DOUBLE, est_gross_yield_pct DOUBLE,
        median_weekly_rent INTEGER, population INTEGER, renter_pct DOUBLE,
        median_days_to_sell INTEGER, median_days_to_rent INTEGER,
        sold_last_12m INTEGER, listed_last_month INTEGER,
        bed1_pct DOUBLE, bed2_pct DOUBLE, bed3_pct DOUBLE,
        bed4_pct DOUBLE, bed5_pct DOUBLE,
        rent_1bed INTEGER, rent_2bed INTEGER, rent_3bed INTEGER, rent_4bed INTEGER,
        source_url TEXT,
        PRIMARY KEY (suburb_id, source_as_at));

    -- No primary key: the ART index over 1.2M rows cost more than the whole
    -- rest of the database. Dedupe is an anti-join at insert time instead.
    CREATE TABLE IF NOT EXISTS valuation (
        ru_id INTEGER, valuation_date DATE, cv BIGINT, lv BIGINT, run_id BIGINT);

    CREATE TABLE IF NOT EXISTS suburb_price_history (
        suburb_id INTEGER, as_at DATE, avg_house_value BIGINT,
        PRIMARY KEY (suburb_id, as_at));

    CREATE TABLE IF NOT EXISTS suburb_description (
        suburb_id INTEGER PRIMARY KEY, title TEXT, extract TEXT, url TEXT,
        source TEXT, license TEXT, captured_at TIMESTAMP);
    """)


def carry_run_log(con):
    """The two tables that key on nothing but themselves."""
    for t in ("pipeline_run", "pipeline_step"):
        con.execute(f"INSERT INTO {t} SELECT * FROM prev.{t}")


def carry_suburb_history(con):
    """Carry the suburb-keyed history, re-pointing it by name.

    suburb_id is row_number() over the boundary file ordered by name, so it is
    positional: it means "the 143rd suburb alphabetically", not "Remuera". LINZ
    published macronised names in August 2026 — Orakei -> Ōrākei, Ranui ->
    Rānui, fifteen of them — and re-sorting moved 122 of 286 ids. Copying the
    history across on the old id silently re-pointed a third of the dataset at
    the wrong suburbs, and it did not error, because an integer is an integer.

    So the join goes through the name, which is the key the source actually
    thinks in — accents stripped and lowercased, because the change that
    triggered this was purely orthographic and Orakei and Ōrākei are the same
    place. A suburb that was genuinely renamed (Mahurangi East -> Mahurangi)
    still drops its history, which is the honest outcome: nothing here can tell
    a rename from a deletion plus an unrelated arrival.
    """
    con.execute("CREATE OR REPLACE TEMP MACRO same_place(a, b) AS "
                "lower(strip_accents(a)) = lower(strip_accents(b))")
    con.execute("""
        INSERT INTO market_snapshot
        SELECT s.suburb_id, m.* EXCLUDE (suburb_id)
        FROM prev.market_snapshot m
        JOIN prev.suburb p ON p.suburb_id = m.suburb_id
        JOIN suburb s ON same_place(s.name, p.name);

        INSERT INTO suburb_price_history
        SELECT s.suburb_id, h.* EXCLUDE (suburb_id)
        FROM prev.suburb_price_history h
        JOIN prev.suburb p ON p.suburb_id = h.suburb_id
        JOIN suburb s ON same_place(s.name, p.name);

        INSERT INTO suburb_description
        SELECT s.suburb_id, d.* EXCLUDE (suburb_id)
        FROM prev.suburb_description d
        JOIN prev.suburb p ON p.suburb_id = d.suburb_id
        JOIN suburb s ON same_place(s.name, p.name);
    """)


def carry_valuations(con):
    """Same hazard, same fix: ru_id is row_number() over valuation_ref, so one
    parcel appearing or leaving shifts every id after it. valuation_ref is the
    council's own identifier and does not move."""
    con.execute("""
        INSERT INTO valuation
        SELECT r.ru_id, v.* EXCLUDE (ru_id)
        FROM prev.valuation v
        JOIN prev.rating_unit q ON q.ru_id = v.ru_id
        JOIN rating_unit r ON r.valuation_ref = q.valuation_ref;
    """)


def main():
    started = datetime.now()
    building = DB.with_name(DB.name + ".building")
    if building.exists():
        building.unlink()

    # A scheduled run in CI has no previous database — it starts from a clean
    # checkout — but it does have the small export that scripts/export_state.py
    # left behind, which carries the tables data/raw cannot rebuild. It has the
    # same schema on purpose, so it attaches as `prev` and the existing
    # carry-forward path does the rest.
    prev_src, prev_tmp = (DB, None) if DB.exists() else (None, None)
    if prev_src is None and STATE.exists():
        prev_tmp = Path(tempfile.mkdtemp()) / "history.duckdb"
        with gzip.open(STATE, "rb") as fin, prev_tmp.open("wb") as fout:
            shutil.copyfileobj(fin, fout)
        prev_src = prev_tmp
        print(f"  no database yet — carrying history from {STATE.name}")

    fresh = prev_src is None
    con = duckdb.connect(str(building))
    con.execute("INSTALL spatial; LOAD spatial;")
    ensure_schema(con)
    if not fresh:
        con.execute(f"ATTACH '{prev_src}' AS prev (READ_ONLY)")
        carry_run_log(con)

    run_id = int(os.environ.get("AKL_RUN_ID") or
                 con.execute("SELECT coalesce(max(run_id), 0) + 1 FROM pipeline_run")
                    .fetchone()[0])
    con.execute("""INSERT INTO pipeline_run VALUES (?,?,?,?,?,?)
                   ON CONFLICT (run_id) DO NOTHING""",
                [run_id, started, None, os.environ.get("AKL_TRIGGER", "manual"),
                 "running", "build_db"])

    # ---- suburb: reference data, rebuilt but keeping first_seen --------------
    con.execute(f"""
        CREATE OR REPLACE TABLE suburb_new AS
        SELECT row_number() OVER (ORDER BY name) AS suburb_id,
               name, name_ascii, type, major_name, territorial_authority,
               population_estimate AS population_linz,
               geom, ST_Centroid(geom) AS centroid,
               round(ST_Area(ST_Transform(geom, 'EPSG:4326', 'EPSG:2193', always_xy := true)) / 1e6, 3) AS area_km2
        FROM ST_Read('{RAW / "auckland_boundaries.geojson"}');
    """)
    if fresh:
        con.execute("""CREATE TABLE suburb AS
                       SELECT *, current_date AS first_seen FROM suburb_new""")
    else:
        con.execute("""
            CREATE OR REPLACE TABLE suburb AS
            SELECT n.*, coalesce(o.first_seen, current_date) AS first_seen
            FROM suburb_new n LEFT JOIN prev.suburb o USING (name);""")
    con.execute("DROP TABLE suburb_new")
    if not fresh:
        carry_suburb_history(con)   # by name: suburb_id is positional

    # Which local board each suburb sits in, plus how far out it is. Centroid
    # rather than overlap: a suburb belongs to exactly one board, and the
    # centroid is the cheap unambiguous answer.
    con.execute(f"""
        ALTER TABLE suburb ADD COLUMN local_board TEXT;
        ALTER TABLE suburb ADD COLUMN zone TEXT;
        ALTER TABLE suburb ADD COLUMN cbd_km DOUBLE;
    """)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE lb AS
        SELECT BOARD AS board, geom FROM ST_Read('{RAW / "local_boards.geojson"}');
    """)
    con.execute("""
        CREATE OR REPLACE TABLE suburb AS
        SELECT s.* EXCLUDE (local_board, zone, cbd_km),
               b.board AS local_board,
               NULL::TEXT AS zone,
               round(ST_Distance(
                   ST_Transform(s.centroid, 'EPSG:4326', 'EPSG:2193', always_xy := true),
                   ST_Transform(ST_Point(?, ?), 'EPSG:4326', 'EPSG:2193', always_xy := true)
               ) / 1000, 1) AS cbd_km
        FROM suburb s
        LEFT JOIN lb b ON ST_Intersects(b.geom, s.centroid);
    """, [CBD[0], CBD[1]])

    # A handful of coastal/island centroids fall outside every board polygon;
    # fall back to the nearest board rather than leaving them unplaced.
    con.execute("""
        UPDATE suburb SET local_board = (
            SELECT b.board FROM lb b
            ORDER BY ST_Distance(b.geom, suburb.centroid) LIMIT 1)
        WHERE local_board IS NULL;
    """)
    zone_cases = " ".join(
        f"WHEN local_board = '{b}' THEN '{z}'" for z, bs in ZONES.items() for b in bs)
    con.execute(f"UPDATE suburb SET zone = CASE {zone_cases} ELSE NULL END")

    key = {norm(name): i for i, name in
           con.execute("SELECT suburb_id, coalesce(name_ascii, name) FROM suburb")
              .fetchall()}
    # ALIASES maps the LINZ spelling to the one the price source still uses, so
    # register the price-source spelling as a second way in to the same suburb.
    for linz, opes in ALIASES.items():
        if linz in key:
            key.setdefault(opes, key[linz])

    # ---- market snapshot: append-only, keyed on the source's release --------
    prices = json.loads((RAW / "opes_suburbs.json").read_text())
    as_at = source_as_at(prices)
    rows, hist = [], []
    for p in prices:
        i = key.get(norm(p["suburb_name"]))
        if i is None or not p.get("average_house_price"):
            continue
        rows.append((
            i, as_at, started, run_id,
            p["average_house_price"],
            p.get("one_year_ago_price"), p.get("one_year_ago_price_change"),
            p.get("two_year_ago_price"), p.get("two_year_ago_price_change"),
            p.get("long_term_capital_growth") or None,
            p.get("estimated_yield") or None, p.get("median_rent") or None,
            p.get("population") or None, p.get("renter_population_percentage"),
            p.get("median_days_to_sell") or None, p.get("median_days_to_rent") or None,
            p.get("sold_last_12_months") or None,
            p.get("listed_for_sale_last_month") or None,
            p.get("one_bed_percentage"), p.get("two_bed_percentage"),
            p.get("three_bed_percentage"), p.get("four_bed_percentage"),
            p.get("five_bed_percentage"),
            p.get("one_bedroom_rent") or None, p.get("two_bedroom_rent") or None,
            p.get("three_bedroom_rent") or None, p.get("four_bedroom_rent") or None,
            "https://www.opespartners.co.nz/" + p["url"],
        ))
        for pt in p.get("price_history_yearly") or []:
            if pt.get("value"):
                hist.append((i, pt["date"], pt["value"]))

    con.execute("CREATE OR REPLACE TEMP TABLE ms_in AS SELECT * FROM market_snapshot LIMIT 0")
    con.executemany("INSERT INTO ms_in VALUES (" + ",".join(["?"] * 28) + ")", rows)
    added_market = len(con.execute("""
        INSERT INTO market_snapshot
        SELECT * FROM ms_in
        WHERE (suburb_id, source_as_at) NOT IN
              (SELECT suburb_id, source_as_at FROM market_snapshot)
        RETURNING 1;""").fetchall())

    con.execute("CREATE OR REPLACE TEMP TABLE h_in (suburb_id INTEGER, as_at DATE, v BIGINT)")
    con.executemany("INSERT INTO h_in VALUES (?,?,?)", hist)
    con.execute("""INSERT INTO suburb_price_history
                   SELECT suburb_id, as_at, v FROM h_in
                   WHERE (suburb_id, as_at) NOT IN
                         (SELECT suburb_id, as_at FROM suburb_price_history);""")

    # ---- descriptions --------------------------------------------------------
    wiki = json.loads((RAW / "wikipedia.json").read_text())
    desc = [(key[norm(n)], w["title"], w["extract"], w["url"],
             "English Wikipedia", "CC BY-SA 4.0", started)
            for n, w in wiki.items() if norm(n) in key]
    con.execute("DELETE FROM suburb_description")  # carried forward, now refreshed
    con.executemany("INSERT INTO suburb_description VALUES (?,?,?,?,?,?,?)", desc)

    # ---- unitary plan base zones --------------------------------------------
    # The zone is the join that makes the plan text answerable. "Can I subdivide
    # this section" is two lookups wearing one question: which zone the parcel
    # is in, which is geometry, and what that zone permits, which is prose in
    # the plan. Neither half answers it alone.
    #
    # Kept whole rather than reduced to a per-parcel label, because a dropped
    # pin has no parcel to look up. The bounding-box columns are materialised
    # here because the second resolution pass below needs them as plain numbers.
    con.execute(f"""
        CREATE OR REPLACE TABLE planning_zone AS
        SELECT row_number() OVER (ORDER BY zone_code, place_name) AS zone_poly_id,
               zone_code::INTEGER AS zone_code, zone,
               group_code::INTEGER AS group_code, group_zone,
               place_name, geom,
               ST_XMin(geom) AS x0, ST_XMax(geom) AS x1,
               ST_YMin(geom) AS y0, ST_YMax(geom) AS y1
        FROM ST_Read('/vsigzip/{RAW / "unitary_plan_zones.geojson.gz"}');
    """)

    # ---- rating units + valuations ------------------------------------------
    tmp = DATA / "_valuations_staged.jsonl.gz"
    n_raw = stage_valuations(tmp)
    # Point-in-polygon in the CREATE, not a later UPDATE: DuckDB rewrites the
    # whole table on UPDATE and never reclaims the old blocks.
    con.execute(f"""
        CREATE OR REPLACE TABLE ru_new AS
        WITH ru AS (
            SELECT valuation_ref, address, land_area_m2, lon, lat,
                   ST_Point(lon, lat) AS geom,
                   cv_2021, lv_2021, cv_2024, lv_2024
            FROM read_json_auto('{tmp}', format='newline_delimited')
        ), hit AS (
            SELECT ru.valuation_ref, min(s.suburb_id) AS suburb_id
            FROM ru JOIN suburb s ON ST_Intersects(s.geom, ru.geom)
            GROUP BY 1
        )
        SELECT row_number() OVER (ORDER BY ru.valuation_ref) AS ru_id,
               ru.*, hit.suburb_id
        FROM ru LEFT JOIN hit USING (valuation_ref);
    """)
    tmp.unlink()

    # Which zone each parcel is in. Two passes, and the order of operations in
    # the second one is not stylistic: writing the leftovers as a correlated
    # NOT EXISTS inside the join takes 508 s, because DuckDB runs ST_Intersects
    # before it filters. Materialising the ~2,100 leftovers first and putting a
    # plain numeric bounding-box test ahead of ST_Intersects gives the same
    # answer in 2.4 s. Whole join: 431 s -> about 4 s.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ru_zone AS
        SELECT r.valuation_ref, min(z.zone_code) AS zone_code
        FROM ru_new r JOIN planning_zone z ON ST_Intersects(z.geom, r.geom)
        WHERE z.zone_code NOT IN {DEFERRED_ZONES}
        GROUP BY 1;
    """)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE ru_left AS
        SELECT r.valuation_ref, r.lon, r.lat, r.geom
        FROM ru_new r
        WHERE NOT EXISTS (SELECT 1 FROM ru_zone z
                          WHERE z.valuation_ref = r.valuation_ref);
    """)
    con.execute(f"""
        INSERT INTO ru_zone
        SELECT r.valuation_ref, min(z.zone_code)
        FROM ru_left r JOIN planning_zone z
          ON r.lon BETWEEN z.x0 AND z.x1 AND r.lat BETWEEN z.y0 AND z.y1
         AND ST_Intersects(z.geom, r.geom)
        WHERE z.zone_code IN {DEFERRED_ZONES}
        GROUP BY 1;
    """)

    if fresh:
        con.execute("""CREATE TABLE rating_unit AS
            SELECT n.ru_id, n.valuation_ref, n.address, n.land_area_m2,
                   n.lon, n.lat, n.geom, n.suburb_id,
                   z.zone_code AS planning_zone_code,
                   current_date AS first_seen, current_date AS last_seen
            FROM ru_new n LEFT JOIN ru_zone z USING (valuation_ref)""")
    else:
        con.execute("""
            CREATE OR REPLACE TABLE rating_unit AS
            SELECT n.ru_id, n.valuation_ref, n.address, n.land_area_m2,
                   n.lon, n.lat, n.geom, n.suburb_id,
                   z.zone_code AS planning_zone_code,
                   coalesce(o.first_seen, current_date) AS first_seen,
                   current_date AS last_seen
            FROM ru_new n
            LEFT JOIN ru_zone z USING (valuation_ref)
            LEFT JOIN prev.rating_unit o USING (valuation_ref);""")
    # No R-tree: measured on this data a vectorised scan with ST_Distance_Sphere
    # answers a 1.5 km radius query in ~20 ms, beating the indexed ST_Within
    # path, and the index cost ~40 MB. Add one if this grows 10x.
    con.execute("CREATE INDEX IF NOT EXISTS ru_suburb_idx ON rating_unit (suburb_id)")
    if not fresh:
        carry_valuations(con)       # by valuation_ref: ru_id is positional

    added_val = 0
    for col, vdate in VALUATION_ROUNDS.items():
        lv = col.replace("cv_", "lv_")
        added_val += len(con.execute(f"""
            INSERT INTO valuation
            SELECT r.ru_id, DATE '{vdate}', n.{col}, n.{lv}, {run_id}
            FROM ru_new n JOIN rating_unit r USING (valuation_ref)
            WHERE n.{col} IS NOT NULL
              AND (r.ru_id, DATE '{vdate}') NOT IN
                  (SELECT ru_id, valuation_date FROM valuation)
            RETURNING 1;""").fetchall())
    con.execute("DROP TABLE ru_new")

    # ---- views ---------------------------------------------------------------
    con.execute("""
    CREATE OR REPLACE VIEW suburb_market AS
    SELECT * EXCLUDE (rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY suburb_id
                                     ORDER BY source_as_at DESC) AS rn
        FROM market_snapshot) WHERE rn = 1;

    -- Revaluations are region-wide, so "current" is one global date. That keeps
    -- this a cheap equality filter instead of a per-row window function.
    -- 57 rows lifted out of the 139k polygons so anything that needs to turn a
    -- zone code into words does not have to touch the geometry table. Names
    -- rather than codes are what reaches the views below: a question like
    -- "how many Mixed Housing Urban parcels" has to be answerable by whoever
    -- writes the SQL, and nobody knows that Mixed Housing Urban is 60.
    CREATE OR REPLACE TABLE planning_zone_ref AS
    SELECT DISTINCT zone_code, zone, group_code, group_zone FROM planning_zone;

    CREATE OR REPLACE VIEW rating_unit_current AS
    SELECT r.*, pz.zone AS planning_zone, pz.group_zone AS planning_group_zone,
           v.valuation_date, v.cv, v.lv
    FROM rating_unit r
    JOIN valuation v USING (ru_id)
    LEFT JOIN planning_zone_ref pz ON pz.zone_code = r.planning_zone_code
    WHERE v.valuation_date = (SELECT max(valuation_date) FROM valuation);

    CREATE OR REPLACE VIEW suburb_overview AS
    SELECT s.suburb_id, s.name, s.type, s.area_km2,
           s.local_board, s.zone, s.cbd_km,
           m.source_as_at AS market_as_at,
           m.avg_house_value, m.change_1y, m.long_term_growth_pct,
           m.median_weekly_rent, m.est_gross_yield_pct, m.population,
           m.median_days_to_sell, m.sold_last_12m,
           v.units, v.cv_median, v.cv_p25, v.cv_p75,
           v.cv_median / nullif(m.avg_house_value, 0) AS cv_vs_avm,
           d.extract AS description
    FROM suburb s
    LEFT JOIN suburb_market m USING (suburb_id)
    LEFT JOIN suburb_description d USING (suburb_id)
    LEFT JOIN (
        SELECT suburb_id, count(*) AS units,
               median(cv)::BIGINT AS cv_median,
               quantile_cont(cv, 0.25)::BIGINT AS cv_p25,
               quantile_cont(cv, 0.75)::BIGINT AS cv_p75
        FROM rating_unit_current WHERE cv IS NOT NULL GROUP BY 1
    ) v USING (suburb_id);

    -- 'skipped' means "not due", which is the normal state most months and
    -- would otherwise mask the last real outcome. Report the last attempt.
    CREATE OR REPLACE VIEW pipeline_status AS
    SELECT source,
           max(finished_at) FILTER (WHERE status IN ('ok','unchanged')) AS last_ok,
           date_diff('day', max(finished_at) FILTER (WHERE status IN ('ok','unchanged')),
                     now()) AS days_ago,
           arg_max(status, finished_at) FILTER (WHERE status <> 'skipped') AS last_status,
           arg_max(rows, finished_at) FILTER (WHERE status <> 'skipped') AS rows,
           arg_max(message, finished_at) FILTER (WHERE status = 'failed') AS last_error
    FROM pipeline_step GROUP BY 1 ORDER BY 1;
    """)

    con.execute("UPDATE pipeline_run SET finished_at = ?, status = 'ok' WHERE run_id = ?",
                [datetime.now(), run_id])
    con.execute("CHECKPOINT")

    s = con.execute("""
        SELECT (SELECT count(*) FROM suburb),
               (SELECT count(*) FROM market_snapshot),
               (SELECT count(DISTINCT source_as_at) FROM market_snapshot),
               (SELECT count(*) FROM rating_unit),
               (SELECT count(*) FROM rating_unit WHERE suburb_id IS NULL),
               (SELECT count(*) FROM valuation),
               (SELECT count(*) FROM suburb_description),
               (SELECT count(*) FROM planning_zone),
               (SELECT count(*) FROM rating_unit WHERE planning_zone_code IS NULL)
        """).fetchone()
    if not fresh:
        con.execute("DETACH prev")
    con.close()
    if prev_tmp is not None:
        shutil.rmtree(prev_tmp.parent, ignore_errors=True)
    os.replace(building, DB)     # atomic: readers keep the old file until now

    print(f"run {run_id} | raw rating units {n_raw:,}")
    print(f"  suburb              {s[0]:>9,}")
    print(f"  market_snapshot     {s[1]:>9,}  (+{added_market} this run, "
          f"{s[2]} release(s), latest {as_at})")
    print(f"  suburb_description  {s[6]:>9,}")
    print(f"  rating_unit         {s[3]:>9,}  ({s[4]:,} outside every suburb, "
          f"{s[8]:,} with no plan zone)")
    print(f"  planning_zone       {s[7]:>9,}")
    print(f"  valuation           {s[5]:>9,}  (+{added_val:,} this run)")
    print(f"{DB} — {DB.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

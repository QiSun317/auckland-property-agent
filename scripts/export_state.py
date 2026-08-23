#!/usr/bin/env python3
"""Export the part of the database that cannot be rebuilt from data/raw.

A scheduled run in CI starts from a clean checkout, so everything the pipeline
knows has to come from somewhere. Almost all of it can be re-derived: the
valuation rounds, the yearly price series and the suburb intros all come back
from the raw files, which is why data/raw is the source of truth. Three things
cannot:

  * market_snapshot  - one row per suburb per source release. The whole point
                       of a scheduled job is that this pile grows; a rebuild
                       from raw only ever knows about the release in hand.
  * pipeline_run/step - when each source was last fetched, which is what the
                       per-source cadences are read from. Lose it and every run
                       thinks every source is due, and a weekly job re-scrapes
                       217 pages for data that changes quarterly.
  * suburb.first_seen - 286 rows, so free to keep and impossible to recover
                       once a rebuild has stamped everything today.

rating_unit.first_seen is deliberately NOT carried. Keeping it means shipping
623,765 rows, which took this file from 60 KB to 6.3 MB — a week's worth of
that, pushed every Monday, is most of a gigabyte a year for a column nothing
reads: grep finds no query, view or page that touches it outside build_db
setting it. A scheduled rebuild therefore stamps every parcel with its own
date. If per-parcel first_seen ever earns its keep, carry it in object storage
rather than in the repo.

The output is a DuckDB file with the same schema as the real one and only those
tables filled, so build_db.py can ATTACH it as `prev` and use the code path it
already has for carrying history forward. Nothing new to keep in step.

Written gzipped: a DuckDB file is nearly all pre-allocated block space, so
this one is 1.8 MB on disk and 24 KB compressed. At a commit a week that is the
difference between a gigabyte a year and a megabyte.

Output: data/state/history.duckdb.gz
"""
import gzip
import os
import shutil
import sys
import tempfile
from pathlib import Path

import build_db     # schema comes from there, so the two cannot drift

ROOT = Path(os.environ.get("AKL_ROOT", Path(__file__).resolve().parent.parent))
DB = Path(os.environ.get("AKL_DB", ROOT / "data" / "auckland.duckdb"))
OUT = Path(os.environ.get("AKL_STATE_DB",
                          ROOT / "data" / "state" / "history.duckdb.gz"))

# Copied wholesale. Everything else in the schema is left empty on purpose:
# build_db refills it from data/raw, and a copy here would be dead weight that
# can disagree with the raw files.
CARRY = ("pipeline_run", "pipeline_step", "market_snapshot")


def main():
    import duckdb

    if not DB.exists():
        sys.exit(f"{DB} does not exist — nothing to export")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp()) / "history.duckdb"

    con = duckdb.connect(str(tmp))
    build_db.ensure_schema(con)
    # suburb and rating_unit are CREATE TABLE AS in build_db rather than part of
    # the schema, so make the two columns its LEFT JOINs actually read.
    # suburb_id comes along because the carry-forward join needs to map the old
    # id to the name before mapping the name to the new id.
    con.execute("CREATE TABLE IF NOT EXISTS suburb "
                "(suburb_id INTEGER, name TEXT, first_seen DATE)")
    # Left empty (see above) but it still needs the columns carry_valuations
    # joins on, or the rebuild fails to bind rather than copying nothing.
    con.execute("CREATE TABLE IF NOT EXISTS rating_unit "
                "(ru_id INTEGER, valuation_ref TEXT, first_seen DATE)")

    con.execute(f"ATTACH '{DB}' AS live (READ_ONLY)")
    counts = {}
    for t in CARRY:
        con.execute(f"INSERT INTO {t} SELECT * FROM live.{t}")
        counts[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    con.execute("INSERT INTO suburb SELECT suburb_id, name, first_seen FROM live.suburb")
    counts["suburb"] = con.execute("SELECT count(*) FROM suburb").fetchone()[0]
    counts["rating_unit"] = 0      # see the module docstring
    con.execute("DETACH live")
    con.close()

    with tmp.open("rb") as fin, gzip.open(OUT, "wb", compresslevel=9) as fout:
        shutil.copyfileobj(fin, fout)
    raw = tmp.stat().st_size
    shutil.rmtree(tmp.parent)

    print(f"wrote {OUT} ({OUT.stat().st_size / 1e3:.1f} KB, "
          f"from {raw / 1e6:.2f} MB uncompressed)")
    for t, n in counts.items():
        print(f"  {t:<16} {n:>9,}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the rate SCD2 merge inside Databricks instead of locally.

Until now the history was merged locally with delta-rs and the whole table was
shipped over by CTAS. That worked, but it meant Databricks was a filing cabinet:
the compute that mattered still happened on a laptop. This sends the *snapshot*
and does the merge there, which is the difference between storing data in a
lakehouse and using one.

It also fixes a hazard the CTAS version had. `CREATE OR REPLACE TABLE bank_rate`
is fine for a table rebuilt from source every run — and fatal for one that
accumulates. The moment the merge lives here, bank_rate has to come out of that
list, or the next sync silently flattens every version it has ever recorded.

Databricks SQL folds two of the three local passes into one statement: it takes
WHEN MATCHED and WHEN NOT MATCHED BY SOURCE in a single MERGE, so closing a
repriced version and closing a delisted one happen together. Opening the new
version still needs its own pass — no MERGE can update a matched row and insert
a replacement for the same source row.

    python3 scripts/databricks_rates.py
    python3 scripts/databricks_rates.py --history   # what the table has seen
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from databricks_sync import CATALOG, SCHEMA, VOLUME, sql, warehouse  # noqa: E402
from rate_history import snapshot_rows                              # noqa: E402

ROOT = Path(os.environ.get("AKL_ROOT", Path(__file__).resolve().parent.parent))
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
TABLE = f"{CATALOG}.{SCHEMA}.bank_rate"
STAGE = "bank_rate_snapshot"


def upload_snapshot(w, rows, as_at, vol):
    import pyarrow as pa
    import pyarrow.parquet as pq
    t = pa.table({
        "bank": pa.array([r["bank"] for r in rows], pa.string()),
        "product": pa.array([r["product"] for r in rows], pa.string()),
        "term": pa.array([r["term"] for r in rows], pa.string()),
        "rate": pa.array([r["rate"] for r in rows], pa.float64()),
    })
    tmp = Path(tempfile.mkdtemp()) / f"{STAGE}.parquet"
    pq.write_table(t, tmp, compression="zstd")
    with tmp.open("rb") as fh:
        w.files.upload(f"{vol}/{STAGE}.parquet", fh, overwrite=True)
    import shutil
    shutil.rmtree(tmp.parent, ignore_errors=True)
    return len(rows)


def counts(w, wh_id):
    r = sql(w, wh_id, f"""
        SELECT count(*), count_if(is_current), count_if(NOT is_current)
        FROM {TABLE}""")
    return tuple(int(x) for x in r.result.data_array[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true",
                    help="the observed series, straight out of the lakehouse")
    a = ap.parse_args()

    if not os.environ.get("DATABRICKS_HOST"):
        sys.exit("DATABRICKS_HOST is not set")

    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    wh = warehouse(w)
    vol = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"

    if a.history:
        r = sql(w, wh.id, f"""
            SELECT valid_from, min(rate) AS cheapest, count(*) AS products
            FROM {TABLE}
            WHERE term = '1y'
              AND bank IN ('ANZ','ASB','BNZ','Kiwibank','Westpac')
            GROUP BY valid_from ORDER BY valid_from""")
        print("cheapest carded 1y rate across the main banks, by observed date\n")
        for d, cheapest, n in (r.result.data_array or []):
            print(f"  {d}   {float(cheapest):.2f}%   ({n} products)")
        return

    snap = RAW / "mortgage_rates.json"
    if not snap.exists():
        sys.exit(f"{snap} is missing — run scripts/fetch_mortgage_rates.py")
    as_at, rows = snapshot_rows(snap)

    n = upload_snapshot(w, rows, as_at, vol)
    print(f"{as_at}: {n} carded rates staged to {vol}/{STAGE}.parquet")

    src = f"(SELECT * FROM parquet.`{vol}/{STAGE}.parquet`)"
    key = ("t.bank = s.bank AND t.product = s.product "
           "AND t.term = s.term AND t.is_current")

    exists = sql(w, wh.id, f"""
        SELECT count(*) FROM {CATALOG}.information_schema.tables
        WHERE table_schema = '{SCHEMA}' AND table_name = 'bank_rate'
    """).result.data_array[0][0]

    if int(exists) == 0:
        sql(w, wh.id, f"""
            CREATE TABLE {TABLE} AS
            SELECT bank, product, term, rate,
                   DATE '{as_at}' AS valid_from,
                   CAST(NULL AS DATE) AS valid_to,
                   true AS is_current
            FROM parquet.`{vol}/{STAGE}.parquet`""")
        print(f"  created {TABLE} with {n} open versions")
        return

    before = counts(w, wh.id)

    # Close what moved and what vanished, in one statement. The guard on
    # t.is_current in the NOT MATCHED BY SOURCE arm is what stops it reclosing
    # every historical row on every run.
    sql(w, wh.id, f"""
        MERGE INTO {TABLE} t
        USING {src} s
        ON {key}
        WHEN MATCHED AND t.rate <> s.rate
            THEN UPDATE SET valid_to = DATE '{as_at}', is_current = false
        WHEN NOT MATCHED BY SOURCE AND t.is_current
            THEN UPDATE SET valid_to = DATE '{as_at}', is_current = false""")

    # Open a version for anything without a current row: new products, and the
    # ones the statement above just closed.
    sql(w, wh.id, f"""
        MERGE INTO {TABLE} t
        USING {src} s
        ON {key}
        WHEN NOT MATCHED THEN INSERT
            (bank, product, term, rate, valid_from, valid_to, is_current)
            VALUES (s.bank, s.product, s.term, s.rate,
                    DATE '{as_at}', NULL, true)""")

    after = counts(w, wh.id)
    opened = after[0] - before[0]
    closed = after[2] - before[2]
    print(f"  {TABLE}: {before[0]} -> {after[0]} rows, "
          f"{after[1]} current")
    print(f"  opened {opened}, closed {closed}")
    if not opened and not closed:
        print("  nothing moved — no versions written")


if __name__ == "__main__":
    main()

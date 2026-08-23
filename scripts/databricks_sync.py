#!/usr/bin/env python3
"""Push the built dataset into Unity Catalog.

Free Edition compute cannot reach the open internet — outbound access is
restricted to a trusted-domain list, and every source this project has is a
site it would need to scrape. So the fetching stays where it already works, in
GitHub Actions, and this pushes the validated result in. Inbound API calls to
the workspace are not restricted, which is what makes the split work at all.

    data/raw  --(fetch + validate in CI)-->  parquet  -->  UC volume
                                                             |
                                                        CTAS into
                                                             v
                                             workspace.auckland.<table>

Parquet through a volume rather than INSERT statements: 1.25M valuation rows
would be a very long afternoon of SQL, and the warehouse is a 2X-Small.

    python3 scripts/databricks_sync.py            # export, upload, load
    python3 scripts/databricks_sync.py --dry-run  # say what it would send
"""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(os.environ.get("AKL_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
DB = Path(os.environ.get("AKL_DB", DATA / "auckland.duckdb"))

CATALOG = os.environ.get("AKL_DBX_CATALOG", "workspace")
SCHEMA = os.environ.get("AKL_DBX_SCHEMA", "auckland")
VOLUME = "raw"

# What goes over, and how it is shaped on the way out. geom is left behind on
# purpose: it is a blob that Databricks SQL has no better use for than the
# lon/lat already beside it, and it is a third of the file.
EXPORTS = {
    "suburb": """
        SELECT suburb_id, name, name_ascii, type, major_name,
               territorial_authority, population_linz, local_board, zone,
               cbd_km, area_km2, first_seen
        FROM suburb""",
    "rating_unit": """
        SELECT ru_id, valuation_ref, address, land_area_m2, lon, lat,
               suburb_id, first_seen, last_seen
        FROM rating_unit""",
    "valuation": "SELECT * FROM valuation",
    "market_snapshot": "SELECT * FROM market_snapshot",
    "suburb_price_history": "SELECT * FROM suburb_price_history",
    "suburb_description": "SELECT * FROM suburb_description",
    "pipeline_step": "SELECT * FROM pipeline_step",
}


def export_parquet(out_dir):
    """DuckDB -> parquet. Zstd because this crosses a network."""
    import duckdb
    if not DB.exists():
        sys.exit(f"{DB} is missing — run scripts/pipeline.py run --rebuild first")
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("LOAD spatial;")
    made = []
    for name, sql in EXPORTS.items():
        path = out_dir / f"{name}.parquet"
        con.execute(f"COPY ({sql}) TO '{path}' (FORMAT PARQUET, COMPRESSION zstd)")
        n = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        made.append((name, path, n))
    con.close()

    # bank_rate is deliberately NOT here. Everything above is derived data,
    # rebuilt from data/raw every run, so CREATE OR REPLACE is the honest
    # verb. bank_rate accumulates — it is the one table whose contents cannot
    # be recomputed from the current snapshot — and replacing it would flatten
    # every version it has recorded. databricks_rates.py merges into it
    # instead.
    return made


def sql(w, warehouse_id, statement):
    from databricks.sdk.service.sql import StatementState
    r = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=statement, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        sys.exit(f"SQL failed: {r.status.error.message if r.status.error else r.status.state}\n"
                 f"  statement: {statement[:200]}")
    return r


def warehouse(w):
    whs = list(w.warehouses.list())
    if not whs:
        sys.exit("no SQL warehouse in the workspace — create one in SQL > Warehouses")
    wh = whs[0]
    if str(wh.state) not in ("State.RUNNING", "RUNNING"):
        print(f"  starting {wh.name} ({wh.state})…", flush=True)
        w.warehouses.start(wh.id).result(timeout=__import__("datetime").timedelta(minutes=10))
    return wh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # Checked after the export, not before: --dry-run only touches local files,
    # and needing a credential to find out what you would have sent is the kind
    # of friction that stops people from checking.
    if not a.dry_run and not os.environ.get("DATABRICKS_HOST"):
        sys.exit("DATABRICKS_HOST is not set.\n"
                 "  local:  databricks configure --host https://<workspace>\n"
                 "  CI:     the DATABRICKS_HOST / DATABRICKS_TOKEN secrets")

    tmp = Path(tempfile.mkdtemp())
    try:
        made = export_parquet(tmp)
        total = sum(p.stat().st_size for _, p, _ in made)
        print(f"exported {len(made)} tables, {total / 1e6:.1f} MB")
        for name, path, n in made:
            print(f"  {name:<22} {n:>9,} rows   {path.stat().st_size / 1e6:>6.2f} MB")
        if a.dry_run:
            print(f"\ndry run — would load into {CATALOG}.{SCHEMA}")
            return

        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        wh = warehouse(w)
        print(f"\nwarehouse: {wh.name} ({wh.cluster_size})")

        sql(w, wh.id, f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
        sql(w, wh.id, f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")
        vol = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
        print(f"namespace: {CATALOG}.{SCHEMA}, volume {vol}")

        for name, path, n in made:
            with path.open("rb") as fh:
                w.files.upload(f"{vol}/{name}.parquet", fh, overwrite=True)
            # CTAS rather than COPY INTO: these are full refreshes of derived
            # data, and a table that is rebuilt is easier to reason about than
            # one that accumulates whatever previous runs happened to leave.
            sql(w, wh.id,
                f"CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.{name} AS "
                f"SELECT * FROM parquet.`{vol}/{name}.parquet`")
            print(f"  loaded {CATALOG}.{SCHEMA}.{name:<22} {n:>9,} rows")

        r = sql(w, wh.id, f"""
            SELECT table_name, 0 AS n FROM {CATALOG}.information_schema.tables
            WHERE table_schema = '{SCHEMA}' ORDER BY 1""")
        names = [row[0] for row in (r.result.data_array or [])]
        print(f"\n{CATALOG}.{SCHEMA} now holds {len(names)} tables: {', '.join(names)}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

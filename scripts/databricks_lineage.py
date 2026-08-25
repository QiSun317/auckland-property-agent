#!/usr/bin/env python3
"""Put the measurement caveats on the columns, and read back the lineage.

This project's longest-running theme is which number means what. The README
carries a whole section of it — that `price` is an automated valuation and not
a sale price, that council capital values cover every rating unit including
industrial land, that the carded rate is not the rate anyone is offered. All of
it lives in a markdown file nobody reads while writing a query.

Unity Catalog holds column comments, and comments travel: they show in the
schema browser, in autocomplete, in anything that introspects the table. So the
caveats go on the columns they are about. A person who writes
`SELECT avg_house_value` and sees "not a sale price, not comparable to the
REINZ median" has been told at the only moment it matters.

Lineage is the other half and needs no building — Unity Catalog records it as
queries run. What is missing is somewhere to read it, so this prints it.

    python3 scripts/databricks_lineage.py            # apply comments
    python3 scripts/databricks_lineage.py --lineage  # where a column came from
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from databricks_sync import CATALOG, SCHEMA, sql, warehouse  # noqa: E402
from field_notes import en as note  # noqa: E402

NS = f"{CATALOG}.{SCHEMA}"

TABLE_COMMENTS = {
    "suburb": "LINZ suburb and locality polygons for Auckland, CC BY 4.0. "
              "suburb_id is a row number over the file ordered by name — it is "
              "positional and moves when LINZ renames anything. Join on name.",
    "rating_unit": "One row per rating unit from Auckland Council's public "
                   "valuation layer. Includes every rating unit, not only "
                   "residential. ru_id is positional; valuation_ref is the "
                   "council's own identifier and is the key to join on.",
    "valuation": "Long format, one row per unit per valuation round, so the "
                 "next revaluation is an INSERT rather than a schema change.",
    "market_snapshot": "Append-only, keyed on the source's own release date. "
                       "Re-running against unchanged input inserts nothing.",
    "bank_rate": "Type 2 slowly changing dimension of carded home loan rates. "
                 "valid_to IS NULL means currently carded. A rate is in force "
                 "from when it was first observed, not from when it was last "
                 "checked.",
    "suburb_confidence": "Residual of a model predicting the commercial AVM "
                         "from council valuations plus geography. A low "
                         "confidence means the two price sources disagree "
                         "about that suburb, not that the suburb is bad.",
    "data_quality": "One row per metric per run. Exists to make a slow slide "
                    "visible; a pass/fail gate cannot see one.",
}

# Base-table columns only — the view columns are declared with the view in
# databricks_views.py, because a view will not take ALTER COLUMN COMMENT. Both
# read the same definitions out of field_notes.py, which is also what the page
# shows a reader on hover. One sentence, three places it can be seen.
COLUMN_COMMENTS = {
    ("valuation", "cv"): note("median_cv"),
    ("rating_unit", "land_area_m2"): note("median_section_m2"),
    ("bank_rate", "rate"):
        "The carded rate, which is what a bank advertises. NOT the rate a "
        "given borrower is offered: that depends on the bank, the deposit and "
        "income, and a deposit under 20% usually does not qualify for the "
        "carded special at all.",
    ("suburb_confidence", "residual_pct"):
        "Positive means the commercial AVM sits above what council valuations "
        "and geography predict. Large either way means the two sources "
        "disagree about this suburb.",
}


def apply_comments(w, wh_id):
    n_t = n_c = 0
    for table, text in TABLE_COMMENTS.items():
        try:
            sql(w, wh_id, f"COMMENT ON TABLE {NS}.{table} IS {lit(text)}")
            n_t += 1
        except SystemExit as exc:
            print(f"  skipped table {table}: {str(exc)[:80]}")
    for (table, col), text in COLUMN_COMMENTS.items():
        try:
            sql(w, wh_id, f"ALTER TABLE {NS}.{table} ALTER COLUMN {col} "
                          f"COMMENT {lit(text)}")
            n_c += 1
        except SystemExit:
            # Views take comments differently; report rather than fail.
            try:
                sql(w, wh_id, f"ALTER VIEW {NS}.{table} ALTER COLUMN {col} "
                              f"COMMENT {lit(text)}")
                n_c += 1
            except SystemExit as exc:
                print(f"  skipped {table}.{col}: {str(exc)[:90]}")
    return n_t, n_c


def lit(s):
    return "'" + s.replace("'", "''") + "'"


def show_lineage(w, wh_id):
    """Unity Catalog records this as queries run; nothing here builds it."""
    try:
        r = sql(w, wh_id, f"""
            SELECT source_table_full_name, target_table_full_name,
                   count(*) AS edges
            FROM system.access.table_lineage
            WHERE target_table_schema = '{SCHEMA}'
               OR source_table_schema = '{SCHEMA}'
            GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 40""")
        rows = r.result.data_array or []
        if not rows:
            print("no lineage recorded yet — it accrues as queries run, and "
                  "system table population lags by up to a few hours")
            return
        print("recorded lineage into and out of this schema:\n")
        for src, tgt, n in rows:
            print(f"  {src or '(file)':<44} -> {tgt}")
    except SystemExit as exc:
        print(f"system.access.table_lineage not readable: {str(exc)[:140]}")
        print("Free Edition may not expose the system catalog; the comments "
              "above are the part that does not depend on it.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lineage", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("DATABRICKS_HOST"):
        sys.exit("DATABRICKS_HOST is not set")

    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    wh = warehouse(w)

    if a.lineage:
        return show_lineage(w, wh.id)

    n_t, n_c = apply_comments(w, wh.id)
    print(f"\n  {n_t} table comments, {n_c} column comments on {NS}")
    r = sql(w, wh.id, f"""
        SELECT table_name, column_name, left(comment, 64)
        FROM {CATALOG}.information_schema.columns
        WHERE table_schema = '{SCHEMA}' AND comment IS NOT NULL
        ORDER BY 1, 2 LIMIT 6""")
    print("\n  a sample, as anyone browsing the schema will see it:")
    for tbl, col, c in (r.result.data_array or []):
        print(f"    {tbl}.{col}\n      {c}…")


if __name__ == "__main__":
    main()

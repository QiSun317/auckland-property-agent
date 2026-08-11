#!/usr/bin/env python3
"""Run a SQL query against data/auckland.duckdb and print it as a table.

    python3 scripts/q.py "SELECT name, avg_house_value FROM suburb_overview LIMIT 5"
    python3 scripts/q.py -f queries/cheap_near_train.sql
    python3 scripts/q.py --schema

Opens read-only by default, so it is safe to run while something else has the
database open (DuckDB allows only one writer).
"""
import argparse
import sys
from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parent.parent / "data" / "auckland.duckdb"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="SQL to run")
    ap.add_argument("-f", "--file", help="read SQL from a file")
    ap.add_argument("--schema", action="store_true", help="print tables and columns")
    ap.add_argument("--write", action="store_true", help="open read-write")
    ap.add_argument("--csv", action="store_true", help="emit CSV instead of a table")
    args = ap.parse_args()

    if not DB.exists():
        sys.exit(f"{DB} not found — run scripts/build_db.py first")

    con = duckdb.connect(str(DB), read_only=not args.write)
    con.execute("LOAD spatial;")

    if args.schema:
        rows = con.execute("""
            SELECT table_name, string_agg(column_name || ' ' || data_type, ', '
                                          ORDER BY ordinal_position) AS columns
            FROM information_schema.columns
            WHERE table_schema = 'main'
            GROUP BY table_name ORDER BY table_name
        """).fetchall()
        for name, cols in rows:
            n = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
            print(f"\n{name}  ({n:,} rows)")
            for c in cols.split(", "):
                print(f"    {c}")
        return

    sql = Path(args.file).read_text() if args.file else args.sql
    if not sql:
        ap.error("give SQL, -f FILE, or --schema")

    rel = con.sql(sql)
    if rel is None:
        return
    if args.csv:
        import csv
        w = csv.writer(sys.stdout)
        w.writerow(rel.columns)
        w.writerows(rel.fetchall())
    else:
        rel.show(max_rows=40)


if __name__ == "__main__":
    main()

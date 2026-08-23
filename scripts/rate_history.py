#!/usr/bin/env python3
"""Accumulate carded home loan rates as a slowly-changing history.

fetch_mortgage_rates.py writes today's snapshot to data/raw/mortgage_rates.json
and the next run overwrites it. Run weekly, that throws away 52 snapshots a
year — and the page can only ever say what the rate is today, never what it
did. The roadmap item "add a curve we observed ourselves" has been waiting on
exactly this.

The shape of the problem is a type 2 slowly changing dimension: a snapshot
tells you what is carded *now*, and the history has to be inferred from the
difference between snapshots. Three things can happen to a
(bank, product, term), and only the second one should create a row:

    unchanged   -> touch nothing. Banks hold rates for weeks; a year of no-op
                   runs must not grow the table.
    repriced    -> close the old version, open a new one.
    delisted    -> close the open version, open nothing.

Delta Lake is used for the format, not the platform: delta-rs is pure Python
with no Spark, and MERGE-on-natural-key plus time travel are the two things
worth having. The natural key matters here for a reason this project learned
the hard way — market_snapshot keyed on a positional suburb_id, and when LINZ
renamed fifteen suburbs the ids shifted and a third of the history silently
re-pointed at the wrong places. (bank, product, term) cannot shift.

    python3 scripts/rate_history.py            # merge today's snapshot
    python3 scripts/rate_history.py --show     # current carded rates
    python3 scripts/rate_history.py --series 1y   # one term's history
    python3 scripts/rate_history.py --log      # the Delta commit log
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

try:
    import pyarrow
    if tuple(int(x) for x in pyarrow.__version__.split(".")[:1]) < (21,):
        raise ImportError(f"pyarrow {pyarrow.__version__} is too old")
except ImportError as exc:  # noqa: TRY003 - the message is the point
    sys.exit(f"{exc}\n"
             f"  running: {sys.executable}\n"
             f"  fix:     {sys.executable} -m pip install 'deltalake' 'pyarrow>=21'\n"
             f"(pyarrow below 21 reads delta-rs 1.x parquet as 'Repetition level\n"
             f" histogram size mismatch' — it writes fine and fails on read back)")

ROOT = Path(os.environ.get("AKL_ROOT", Path(__file__).resolve().parent.parent))
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))
TABLE = Path(os.environ.get("AKL_RATE_TABLE",
                            ROOT / "data" / "state" / "bank_rate"))

# Snapshot -> rows. One row per (bank, product, term) that is actually carded;
# a product quoting no rate for a term simply has no row, which is what makes
# "delisted" expressible at all.
def snapshot_rows(path):
    d = json.loads(Path(path).read_text())
    as_at = date.fromisoformat(d["as_at"])
    rows = []
    for p in d["products"]:
        for term, rate in (p.get("rates") or {}).items():
            if rate:
                rows.append({"bank": p["institution"], "product": p["product"],
                             "term": term, "rate": float(rate)})
    return as_at, rows


def arrow_source(rows, as_at):
    import pyarrow as pa
    return pa.table({
        "bank": pa.array([r["bank"] for r in rows], pa.string()),
        "product": pa.array([r["product"] for r in rows], pa.string()),
        "term": pa.array([r["term"] for r in rows], pa.string()),
        "rate": pa.array([r["rate"] for r in rows], pa.float64()),
        "valid_from": pa.array([as_at] * len(rows), pa.date32()),
        "valid_to": pa.array([None] * len(rows), pa.date32()),
        "is_current": pa.array([True] * len(rows), pa.bool_()),
    })


KEY = ("t.bank = s.bank AND t.product = s.product AND t.term = s.term "
       "AND t.is_current")


def merge_snapshot(rows, as_at, table_uri=None):
    """Fold one snapshot into the history. Returns what actually changed."""
    from deltalake import DeltaTable, write_deltalake

    uri = str(table_uri or TABLE)
    src = arrow_source(rows, as_at)

    if not DeltaTable.is_deltatable(uri):
        write_deltalake(uri, src, mode="error")
        return {"opened": len(rows), "repriced": 0, "delisted": 0, "unchanged": 0,
                "version": DeltaTable(uri).version()}

    dt = DeltaTable(uri)
    before = dt.to_pyarrow_table().num_rows
    closed_before = _closed(dt)

    # 1. Close the versions whose rate moved. Doing this first is what lets
    #    step 2 use a plain "not matched" clause: a repriced key no longer has
    #    a current row, so it looks exactly like a brand new one.
    dt.merge(src, predicate=KEY, source_alias="s", target_alias="t") \
      .when_matched_update(predicate="t.rate <> s.rate",
                           updates={"valid_to": f"DATE '{as_at}'",
                                    "is_current": "false"}) \
      .execute()
    repriced = _closed(dt) - closed_before

    # 2. Open a version for anything with no current row: new products and the
    #    ones step 1 just closed. Unchanged keys still match, and a merge with
    #    no matched clause leaves them alone — that is the no-op property.
    dt.merge(src, predicate=KEY, source_alias="s", target_alias="t") \
      .when_not_matched_insert(updates={
          "bank": "s.bank", "product": "s.product", "term": "s.term",
          "rate": "s.rate", "valid_from": f"DATE '{as_at}'",
          "valid_to": "NULL", "is_current": "true"}) \
      .execute()
    opened = dt.to_pyarrow_table().num_rows - before

    # 3. A key that is current here but absent from the snapshot stopped being
    #    carded. Close it and open nothing. Guarded on is_current so it does
    #    not reopen and re-close every historical row on every run.
    closed_before = _closed(dt)
    dt.merge(src, predicate=KEY, source_alias="s", target_alias="t") \
      .when_not_matched_by_source_update(
          predicate="t.is_current",
          updates={"valid_to": f"DATE '{as_at}'", "is_current": "false"}) \
      .execute()
    delisted = _closed(dt) - closed_before

    return {"opened": opened, "repriced": repriced, "delisted": delisted,
            "unchanged": len(rows) - repriced - (opened - repriced),
            "version": dt.version()}


def _closed(dt):
    import pyarrow.compute as pc
    t = dt.to_pyarrow_table(columns=["is_current"])
    return pc.sum(pc.cast(pc.invert(t["is_current"].combine_chunks()),
                          "int64")).as_py() or 0


# --------------------------------------------------------------------------
def show_current(uri):
    from deltalake import DeltaTable
    dt = DeltaTable(str(uri))
    t = dt.to_pyarrow_table().to_pylist()
    cur = sorted((r for r in t if r["is_current"]),
                 key=lambda r: (r["term"], r["rate"]))
    print(f"{len(cur)} carded rates, table version {dt.version()}\n")
    print(f"{'term':<8}{'rate':>7}  {'bank':<26}{'product':<28}{'since'}")
    for r in cur:
        print(f"{r['term']:<8}{r['rate']:>6.2f}%  {r['bank']:<26}"
              f"{r['product'][:26]:<28}{r['valid_from']}")


def show_series(uri, term, everyone=False):
    """What this term's cheapest carded rate did over time — the thing the page
    cannot say today.

    Defaults to the main banks, because that is the basis the page quotes and
    two different statistics must not wear the same name. Across every
    institution the cheapest 1y is a percentage point lower, carded by lenders
    almost nobody in the reader's position will be offered.
    """
    from deltalake import DeltaTable
    from fetch_mortgage_rates import MAIN_BANKS      # one definition of "main"

    rows = [r for r in DeltaTable(str(uri)).to_pyarrow_table().to_pylist()
            if r["term"] == term and (everyone or r["bank"] in MAIN_BANKS)]
    if not rows:
        sys.exit(f"no rows for term {term!r}"
                 + ("" if everyone else " among the main banks — try --all"))
    basis = "every institution" if everyone else ", ".join(MAIN_BANKS)
    edges = sorted({r["valid_from"] for r in rows} |
                   {r["valid_to"] for r in rows if r["valid_to"]})
    print(f"cheapest carded {term} rate across {basis},")
    print(f"on the dates we actually observed\n")
    for d in edges:
        live = [r["rate"] for r in rows
                if r["valid_from"] <= d and (r["valid_to"] is None or r["valid_to"] > d)]
        if live:
            print(f"  {d}   {min(live):.2f}%   ({len(live)} products carded)")
    if len(edges) == 1:
        print("\n  one observation so far — this is a history that starts now,")
        print("  not one we can backfill. It gains a point every time a rate moves.")


def show_log(uri):
    from deltalake import DeltaTable
    dt = DeltaTable(str(uri))
    print(f"{dt.version() + 1} versions — every one of them readable\n")
    for h in reversed(dt.history()):
        op = h.get("operationParameters", {})
        pred = (op.get("predicate") or "")[:44]
        print(f"  v{h['version']:<3} {h['operation']:<18} {pred}")
    print(f"\n  time travel:  DeltaTable('{uri}', version=0)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--show", action="store_true", help="current carded rates")
    ap.add_argument("--series", metavar="TERM", help="one term's history, e.g. 1y")
    ap.add_argument("--all", action="store_true",
                    help="with --series: every institution, not just the main banks")
    ap.add_argument("--log", action="store_true", help="the Delta commit log")
    a = ap.parse_args()

    from deltalake import DeltaTable
    if (a.show or a.series or a.log) and not DeltaTable.is_deltatable(str(TABLE)):
        sys.exit(f"{TABLE} has no history yet — run this with no arguments first")
    if a.show:
        return show_current(TABLE)
    if a.series:
        return show_series(TABLE, a.series, a.all)
    if a.log:
        return show_log(TABLE)

    snap = RAW / "mortgage_rates.json"
    if not snap.exists():
        sys.exit(f"{snap} is missing.\n"
                 f"  fix:  python3 scripts/fetch_mortgage_rates.py")
    as_at, rows = snapshot_rows(snap)
    r = merge_snapshot(rows, as_at)
    print(f"{as_at}: {len(rows)} carded rates in the snapshot -> "
          f"version {r['version']}")
    print(f"  opened   {r['opened']:>4}   (new products, plus the repriced ones reopened)")
    print(f"  repriced {r['repriced']:>4}")
    print(f"  delisted {r['delisted']:>4}")
    if not (r["opened"] or r["repriced"] or r["delisted"]):
        print("  nothing moved — no new versions written")


if __name__ == "__main__":
    main()
    # delta-rs occasionally fails to join a native worker at interpreter
    # shutdown: every line of output is already written and flushed, main() has
    # returned, no Python thread is left alive, and the process still sits
    # there. Measured one hang in three on --show, indefinite. This runs inside
    # the weekly pipeline, where that means hanging until the job timeout
    # rather than failing, so leave through the door that does not wait for the
    # native runtime to tidy up.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)

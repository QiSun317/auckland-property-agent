#!/usr/bin/env python3
"""Prove the three transitions in rate_history.py against a throwaway table.

There is only one real snapshot so far, so the interesting paths — repriced and
delisted — cannot be exercised against live data for months. They are the whole
point of the design, and a three-pass MERGE is subtle enough that "it ran
without erroring" is not evidence it did the right thing.

    python3 scripts/rate_history_test.py
"""
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rate_history as rh

FAILED = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'}  {label:<52} {got!r}"
          + ("" if ok else f"  (expected {want!r})"))
    if not ok:
        FAILED.append(label)


def state(uri):
    from deltalake import DeltaTable
    rows = DeltaTable(str(uri)).to_pyarrow_table().to_pylist()
    return rows, [r for r in rows if r["is_current"]]


def rate_of(rows, bank, term):
    hit = [r for r in rows if r["bank"] == bank and r["term"] == term]
    return hit[0]["rate"] if hit else None


def main():
    tmp = Path(tempfile.mkdtemp()) / "bank_rate"
    try:
        snap = lambda *rs: [{"bank": b, "product": "Special", "term": t, "rate": v}
                            for b, t, v in rs]

        # --- day 1: first ever snapshot ---------------------------------
        r = rh.merge_snapshot(snap(("ANZ", "1y", 4.99), ("ASB", "1y", 4.99),
                                   ("BNZ", "2y", 5.45)),
                              date(2026, 8, 1), tmp)
        rows, cur = state(tmp)
        print("day 1 — first snapshot")
        check("rows written", len(rows), 3)
        check("all current", len(cur), 3)

        # --- day 2: nothing moved ---------------------------------------
        # The property that makes a weekly job cheap: banks hold rates for
        # weeks, and a no-op run must not grow the table.
        r = rh.merge_snapshot(snap(("ANZ", "1y", 4.99), ("ASB", "1y", 4.99),
                                   ("BNZ", "2y", 5.45)),
                              date(2026, 8, 8), tmp)
        rows, cur = state(tmp)
        print("day 2 — identical snapshot")
        check("no rows added", len(rows), 3)
        check("still 3 current", len(cur), 3)
        check("reported nothing moved", (r["opened"], r["repriced"], r["delisted"]),
              (0, 0, 0))

        # --- day 3: ANZ reprices ----------------------------------------
        r = rh.merge_snapshot(snap(("ANZ", "1y", 5.25), ("ASB", "1y", 4.99),
                                   ("BNZ", "2y", 5.45)),
                              date(2026, 8, 15), tmp)
        rows, cur = state(tmp)
        old = [x for x in rows if x["bank"] == "ANZ" and not x["is_current"]]
        print("day 3 — ANZ 1y moves 4.99 -> 5.25")
        check("one version added", len(rows), 4)
        check("still 3 current", len(cur), 3)
        check("current ANZ rate", rate_of(cur, "ANZ", "1y"), 5.25)
        check("old version closed on the day it moved",
              (old[0]["rate"], str(old[0]["valid_to"])), (4.99, "2026-08-15"))
        check("reported one reprice", r["repriced"], 1)
        check("untouched banks kept their valid_from",
              str([x for x in cur if x["bank"] == "ASB"][0]["valid_from"]), "2026-08-01")

        # --- day 4: BNZ stops carding 2y --------------------------------
        r = rh.merge_snapshot(snap(("ANZ", "1y", 5.25), ("ASB", "1y", 4.99)),
                              date(2026, 8, 22), tmp)
        rows, cur = state(tmp)
        print("day 4 — BNZ 2y delisted")
        check("no version opened for it", len(rows), 4)
        check("two current", len(cur), 2)
        check("BNZ closed, not deleted",
              [x["is_current"] for x in rows if x["bank"] == "BNZ"], [False])
        check("reported one delisting", r["delisted"], 1)

        # --- day 5: a run after a delisting is still a no-op ------------
        # Guards the mistake that would reopen and re-close every historical
        # row on every subsequent run.
        r = rh.merge_snapshot(snap(("ANZ", "1y", 5.25), ("ASB", "1y", 4.99)),
                              date(2026, 8, 29), tmp)
        rows, _ = state(tmp)
        print("day 5 — same snapshot again, after a delisting")
        check("still no churn", len(rows), 4)
        check("nothing reported", (r["opened"], r["repriced"], r["delisted"]),
              (0, 0, 0))

        # --- time travel -------------------------------------------------
        from deltalake import DeltaTable
        v0 = DeltaTable(str(tmp), version=0).to_pyarrow_table().to_pylist()
        print("time travel — read the table as it was at version 0")
        check("version 0 has the day-1 rate", rate_of(v0, "ANZ", "1y"), 4.99)
        check("and does not know about the reprice", len(v0), 3)

    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)

    print()
    if FAILED:
        sys.exit(f"{len(FAILED)} check(s) failed: {', '.join(FAILED)}")
    print("all checks passed")


if __name__ == "__main__":
    main()

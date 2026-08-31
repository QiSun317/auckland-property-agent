#!/usr/bin/env python3
"""Measure whether plan retrieval actually finds the clause that answers.

Two numbers matter here and they are not the same thing.

Recall is the obvious one: is the right clause in the top k. It says how often
the model is given what it needs, and it is the number that moves when the
embedding model or the chunking changes.

Off-zone is the one worth watching. It counts hits returned from a chapter that
does not govern the queried zone — H4's height standard offered for an H5
parcel. Those are the dangerous results, because every zone chapter says
roughly the same things in roughly the same words with different numbers, so a
wrong-chapter clause reads exactly like a right one. The filtered path should
hold this at zero by construction, and the point of running the unfiltered arm
is to show what it would otherwise be rather than to assert it.

Cases live in evals/plan_cases.jsonl. `want` is a clause id, or a chapter when
section-level is the honest expectation — a prefix match either way, so
wanting H5.6.4 accepts H5.6.4#2 and wanting E36 accepts any clause in it.

    python3 scripts/eval_plan.py                    # default model, both arms
    python3 scripts/eval_plan.py --model e5-small   # compare encoders
    python3 scripts/eval_plan.py --k 10 --verbose
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AKL_DATA_DIR", ROOT / "data"))
DB = Path(os.environ.get("AKL_DB", DATA / "auckland.duckdb"))
CASES = ROOT / "evals" / "plan_cases.jsonl"
EXPERIMENT = "auckland-plan-retrieval"


def matches(clause_id, want):
    """H5.6.4 satisfies a want of H5.6.4 or H5.6; H5.6.41 satisfies neither."""
    return clause_id == want or clause_id.startswith(want + ".")


def chapters_for_zone(con, zone):
    """Chapters that actually govern this zone, region-wide ones included."""
    rows = con.execute("""
        SELECT DISTINCT chapter FROM plan_clause
        WHERE (len(zone_codes) = 0 AND NOT list_contains(excluded_zone_codes, ?))
           OR list_contains(zone_codes, ?)
    """, [zone, zone]).fetchall()
    return {r[0] for r in rows}


def run(con, cases, k, model, filtered):
    hits, ranks, off_zone, rows = 0, [], 0, []
    for c in cases:
        allowed = chapters_for_zone(con, c["zone"])
        found = plan_search.search(con, c["q"],
                                   zone_code=c["zone"] if filtered else None,
                                   k=k, model=model)
        rank = next((i + 1 for i, h in enumerate(found)
                     if matches(h["clause_id"], c["want"])), None)
        stray = [h["clause_key"] for h in found if h["chapter"] not in allowed]
        if rank:
            hits += 1
            ranks.append(1 / rank)
        else:
            ranks.append(0.0)
        off_zone += len(stray)
        rows.append({"id": c["id"], "rank": rank, "top": found[0]["clause_key"],
                     "off_zone": len(stray), "why": c["why"]})
    n = len(cases)
    return {"recall": hits / n, "mrr": sum(ranks) / n,
            "off_zone": off_zone, "cases": n, "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-log", action="store_true", help="skip MLflow")
    args = ap.parse_args()

    if not CASES.exists():
        sys.exit(f"{CASES} not found")
    cases = [json.loads(l) for l in CASES.read_text().splitlines() if l.strip()]
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET enable_progress_bar=false;")
    cfg = plan_search.embedding_config(con, args.model)

    print(f"{len(cases)} cases · k={args.k} · {cfg['model']} ({cfg['dims']}d)\n")
    results = {}
    for filtered in (True, False):
        t0 = time.time()
        r = run(con, cases, args.k, args.model, filtered)
        r["seconds"] = time.time() - t0
        results["filtered" if filtered else "unfiltered"] = r

    print(f"{'':12} {'recall@' + str(args.k):>10} {'MRR':>8} {'off-zone hits':>15}")
    for name, r in results.items():
        print(f"{name:12} {r['recall']:>9.0%} {r['mrr']:>8.2f} {r['off_zone']:>15}")

    f, u = results["filtered"], results["unfiltered"]
    print(f"\nfiltering: recall {u['recall']:.0%} -> {f['recall']:.0%}, "
          f"off-zone hits {u['off_zone']} -> {f['off_zone']}")

    misses = [r for r in f["rows"] if r["rank"] is None]
    if misses:
        print(f"\n{len(misses)} case(s) the filtered path does not reach in {args.k}:")
        for m in misses:
            print(f"  {m['id']:<28} got {m['top']:<14} — {m['why']}")
    if args.verbose:
        print("\nall cases (filtered):")
        for r in f["rows"]:
            print(f"  {r['id']:<28} rank={str(r['rank'] or '-'):<4} {r['top']}")

    if not args.no_log:
        try:
            import mlflow
            mlflow.set_experiment(EXPERIMENT)
            with mlflow.start_run():
                mlflow.log_params({"model": cfg["model"], "dims": cfg["dims"],
                                   "k": args.k, "cases": len(cases)})
                for name, r in results.items():
                    mlflow.log_metrics({f"{name}_recall": r["recall"],
                                        f"{name}_mrr": r["mrr"],
                                        f"{name}_off_zone": r["off_zone"]})
        except ImportError:
            print("\n(mlflow not installed — metrics not logged)")

    # A retrieval arm that cannot beat no-filtering on its own cases means the
    # design claim is wrong, and that should stop a build rather than print.
    if f["recall"] < u["recall"] or f["off_zone"] > u["off_zone"]:
        sys.exit("filtered retrieval is not better than unfiltered — the zone "
                 "filter is not doing what this design says it does")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the agent's gates as a regression suite and record the result.

The three gates — names, figures, claims — were verified once, by hand, against
nine cases. That was true when they were written and stopped being true the
moment anything around them changed: this run's suite immediately found that
the figure checker's tolerance was wide enough to reach the field next door,
so an invented "租金回报 5.8%" passed by landing near a real growth figure of
6.3%.

Every case in evals/cases.jsonl is a failure that actually happened. That is
the point of the file — not coverage for its own sake, but a record of the ways
this thing has been wrong, in a form that makes being wrong that way again into
a red build.

The cases run against the built page through jsdom, so they exercise the code
that shipped rather than a copy of it. Results land in MLflow as a pass rate
per category, tagged with the commit, which is what turns "I tested it once"
into a line that can be watched.

    python3 scripts/eval_agent.py            # run, print, log to MLflow
    python3 scripts/eval_agent.py --no-log   # run and print only
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AKL_ROOT", Path(__file__).resolve().parent.parent))
PAGE = ROOT / "heatmap.html"
CASES = ROOT / "evals" / "cases.jsonl"
HARNESS = ROOT / "evals" / "run.mjs"
EXPERIMENT = "auckland-agent-gates"


def run_harness():
    if not PAGE.exists():
        sys.exit(f"{PAGE} is not built — run scripts/build_map.py first")
    if not (ROOT / "evals" / "node_modules").exists():
        sys.exit("evals/node_modules is missing.\n"
                 "  fix:  npm --prefix evals install")
    proc = subprocess.run(["node", str(HARNESS), str(PAGE), str(CASES)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"harness failed:\n{proc.stderr.strip()[:1200]}")
    return json.loads(proc.stdout)


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001 - a missing git is not a reason to fail
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()

    out = run_harness()
    results = out["results"]
    kinds = sorted({r["kind"] for r in results})
    failed = [r for r in results if not r["ok"]]

    print(f"{out['n']} cases against {Path(out['page']).name}\n")
    for k in kinds:
        rs = [r for r in results if r["kind"] == k]
        n_ok = sum(1 for r in rs if r["ok"])
        print(f"  {k:<10} {n_ok}/{len(rs)}")
    print()
    for r in failed:
        print(f"  FAIL {r['id']}")
        print(f"       got {r['got']!r}, expected {r['expect']!r}")
        print(f"       case exists because: {r['why']}")

    if not a.no_log and os.environ.get("DATABRICKS_HOST"):
        import mlflow
        from databricks.sdk import WorkspaceClient
        mlflow.set_tracking_uri("databricks")
        me = WorkspaceClient().current_user.me().user_name
        mlflow.set_experiment(f"/Users/{me}/{EXPERIMENT}")
        with mlflow.start_run(run_name=git_sha()):
            mlflow.log_params({"commit": git_sha(), "cases": out["n"],
                               "page_bytes": PAGE.stat().st_size})
            mlflow.log_metric("pass_rate", (out["n"] - len(failed)) / out["n"])
            mlflow.log_metric("failures", len(failed))
            for k in kinds:
                rs = [r for r in results if r["kind"] == k]
                mlflow.log_metric(f"pass_rate_{k}",
                                  sum(1 for r in rs if r["ok"]) / len(rs))
            # The full result, so a red run can be read without rerunning it.
            mlflow.log_dict(out, "results.json")
        print(f"\nlogged to MLflow: /Users/{me}/{EXPERIMENT} (run {git_sha()})")
    elif not a.no_log:
        print("\nDATABRICKS_HOST not set — ran locally, nothing logged")

    if failed:
        sys.exit(f"\n{len(failed)} of {out['n']} gate cases failed")
    print(f"\nall {out['n']} passed")


if __name__ == "__main__":
    main()

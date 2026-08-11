#!/usr/bin/env python3
"""Orchestrator for the monthly refresh.

    python3 scripts/pipeline.py run              # fetch what is due, rebuild if changed
    python3 scripts/pipeline.py run --force prices
    python3 scripts/pipeline.py run --dry-run    # say what it would do
    python3 scripts/pipeline.py status           # per-source state, recent runs

Design notes
------------
Fetch -> validate -> promote. Every fetcher writes into data/incoming; a file
only replaces the one in data/raw once it has passed that source's checks. A
source site changing its markup therefore degrades to "last month's data plus a
failed step in the log", never to a wiped dataset.

Sources are polled on their own cadence, because they do not move at the same
speed: council capital values are set on a three-year revaluation cycle, LINZ
edits boundaries a few times a year, and Wikipedia intros almost never change.
Running everything monthly would be mostly wasted requests.

Nothing here is macOS-specific — the scheduler is a thin wrapper in ops/, so
moving to CI means swapping that wrapper, not this file.
"""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(os.environ.get("AKL_ROOT", Path(__file__).resolve().parent.parent))
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
RAW = DATA / "raw"
INCOMING = DATA / "incoming"
LOGS = ROOT / "logs"
DB = DATA / "auckland.duckdb"
PY = sys.executable


# --------------------------------------------------------------------------
# validation gates
# --------------------------------------------------------------------------
class Reject(Exception):
    """Raised when a freshly fetched file is not fit to replace the live one."""


def _within(new, old, tol, label):
    if old:
        drift = abs(new - old) / old
        if drift > tol:
            raise Reject(f"{label} moved {drift:.0%} (from {old:,.0f} to {new:,.0f}), "
                         f"tolerance {tol:.0%}")


def check_boundaries(path, prev):
    fc = json.loads(path.read_text())
    n = len(fc.get("features", []))
    if not 250 <= n <= 400:
        raise Reject(f"{n} polygons, expected 250-400")
    if any(not f.get("properties", {}).get("name") or not f.get("geometry")
           for f in fc["features"]):
        raise Reject("some features have no name or no geometry")
    return n


def check_prices(path, prev):
    recs = json.loads(path.read_text())
    priced = [r for r in recs if r.get("average_house_price")]
    if len(priced) < 190:
        raise Reject(f"only {len(priced)} suburbs have a price, expected >=190")
    vals = sorted(r["average_house_price"] for r in priced)
    _within(vals[len(vals) // 2], prev.get("median_price"), 0.30, "median suburb value")
    return len(recs)


def check_valuations(path, prev):
    n = with_cv = 0
    total = 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            n += 1
            if r.get("lcv"):
                with_cv += 1
                total += r["lcv"]
    if n < 590_000:
        raise Reject(f"{n:,} rating units, expected >=590,000")
    if with_cv / n < 0.95:
        raise Reject(f"only {with_cv / n:.1%} of units carry a capital value")
    _within(total / with_cv, prev.get("mean_cv"), 0.25, "mean capital value")
    return n


def check_localboards(path, prev):
    fc = json.loads(path.read_text())
    n = len(fc.get("features", []))
    if n != 21:
        raise Reject(f"{n} local boards, expected exactly 21")
    return n


def check_wikipedia(path, prev):
    d = json.loads(path.read_text())
    good = [v for v in d.values() if (v.get("extract") or "").strip()]
    if len(good) < 180:
        raise Reject(f"only {len(good)} intros, expected >=180")
    return len(good)


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------
@dataclass
class Source:
    name: str
    script: str
    artifact: str
    every_days: int
    check: Callable
    why: str


SOURCES = [
    Source("prices", "fetch_prices.py", "opes_suburbs.json", 30, check_prices,
           "per-suburb valuations; the source refreshes roughly quarterly"),
    Source("valuations", "fetch_valuations.py", "valuations.jsonl.gz", 90,
           check_valuations,
           "council CVs; set on a 3-year revaluation cycle, corrections in between"),
    Source("boundaries", "fetch_boundaries.py", "auckland_boundaries.geojson", 90,
           check_boundaries, "LINZ edits suburb boundaries a few times a year"),
    Source("localboards", "fetch_localboards.py", "local_boards.geojson", 365,
           check_localboards, "council local boards; redrawn only at reorganisation"),
    Source("wikipedia", "fetch_wikipedia.py", "wikipedia.json", 180,
           check_wikipedia, "suburb intros; near-static"),
]

BUILD_STEPS = ["build_db.py", "build_detail.py", "build_map.py"]

# Optional last step: push the rebuilt page to the public site. Off unless
# AKL_PUBLISH=1, so a local run never publishes by accident.
PUBLISH = ROOT / "ops" / "publish.sh"


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------
def db_state():
    """Last-success times, last hashes, and the baselines the gates compare to."""
    state = {"last_ok": {}, "last_hash": {}, "run_id": 1,
             "median_price": None, "mean_cv": None}
    if not DB.exists():
        return state
    try:
        import duckdb
        con = duckdb.connect(str(DB), read_only=True)
        for src, ts, h in con.execute("""
            SELECT source, max(finished_at),
                   arg_max(source_hash, finished_at)
            FROM pipeline_step WHERE status IN ('ok','unchanged')
            GROUP BY 1""").fetchall():
            state["last_ok"][src] = ts
            state["last_hash"][src] = h
        state["run_id"] = con.execute(
            "SELECT coalesce(max(run_id),0)+1 FROM pipeline_run").fetchone()[0]
        state["median_price"] = con.execute(
            "SELECT median(avg_house_value) FROM suburb_market").fetchone()[0]
        state["mean_cv"] = con.execute(
            "SELECT avg(cv) FROM rating_unit_current").fetchone()[0]
        con.close()
    except Exception as exc:  # noqa: BLE001 - a missing/old db must not block a run
        print(f"  (could not read previous state: {exc})", file=sys.stderr)
    return state


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log_jsonl(record):
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "pipeline.jsonl").open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def run_script(name, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    proc = subprocess.run([PY, str(SCRIPTS / name)], env=env,
                          capture_output=True, text=True)
    return proc


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------
def do_run(args):
    started = datetime.now()
    state = db_state()
    run_id = state["run_id"]
    force = set(args.force or [])
    steps, changed = [], []

    INCOMING.mkdir(parents=True, exist_ok=True)
    print(f"run {run_id} @ {started:%Y-%m-%d %H:%M}  trigger={args.trigger}")

    for src in SOURCES:
        last = state["last_ok"].get(src.name)
        age = (started - last).days if last else None
        due = "all" in force or src.name in force or age is None or age >= src.every_days
        if not due:
            print(f"  {src.name:<11} skip   (fetched {age}d ago, cadence {src.every_days}d)")
            steps.append(dict(run_id=run_id, source=src.name, status="skipped",
                              started_at=started, finished_at=datetime.now(),
                              source_hash=state["last_hash"].get(src.name), rows=None,
                              message=f"not due for {src.every_days - age}d"))
            continue
        if args.dry_run:
            print(f"  {src.name:<11} WOULD FETCH ({src.why})")
            continue

        t0 = datetime.now()
        print(f"  {src.name:<11} fetching...", flush=True)
        proc = run_script(src.script, {"AKL_OUT_DIR": str(INCOMING)})
        staged = INCOMING / src.artifact

        if proc.returncode != 0 or not staged.exists():
            msg = (proc.stderr.strip().splitlines() or ["no output"])[-1][:200]
            print(f"  {src.name:<11} FAILED fetch: {msg}")
            steps.append(dict(run_id=run_id, source=src.name, status="failed",
                              started_at=t0, finished_at=datetime.now(),
                              source_hash=None, rows=None, message=f"fetch: {msg}"))
            continue

        try:
            rows = src.check(staged, state)
        except Reject as exc:
            print(f"  {src.name:<11} REJECTED: {exc}  (keeping previous data)")
            steps.append(dict(run_id=run_id, source=src.name, status="failed",
                              started_at=t0, finished_at=datetime.now(),
                              source_hash=None, rows=None, message=f"rejected: {exc}"))
            staged.unlink()
            continue

        digest = sha256(staged)
        if digest == state["last_hash"].get(src.name):
            print(f"  {src.name:<11} unchanged ({rows:,} rows)")
            staged.unlink()
            steps.append(dict(run_id=run_id, source=src.name, status="unchanged",
                              started_at=t0, finished_at=datetime.now(),
                              source_hash=digest, rows=rows, message=None))
            continue

        RAW.mkdir(parents=True, exist_ok=True)
        os.replace(staged, RAW / src.artifact)          # promote, atomically
        changed.append(src.name)
        print(f"  {src.name:<11} updated ({rows:,} rows)")
        steps.append(dict(run_id=run_id, source=src.name, status="ok",
                          started_at=t0, finished_at=datetime.now(),
                          source_hash=digest, rows=rows, message=None))

    if args.dry_run:
        print("dry run: nothing fetched, nothing rebuilt")
        return 0

    rebuilt, build_error = False, None
    if changed or args.rebuild:
        why = ", ".join(changed) if changed else "--rebuild"
        print(f"  rebuilding ({why})")
        for name in BUILD_STEPS:
            t0 = time.time()
            proc = run_script(name, {"AKL_RUN_ID": str(run_id),
                                     "AKL_TRIGGER": args.trigger})
            ok = proc.returncode == 0
            tail = (proc.stdout.strip().splitlines() or [""])[-1][:120]
            print(f"    {name:<18} {'ok' if ok else 'FAILED'}  {time.time()-t0:.1f}s  {tail}")
            if not ok:
                build_error = f"{name}: {(proc.stderr.strip().splitlines() or [''])[-1][:200]}"
                break
        rebuilt = build_error is None
    else:
        print("  nothing changed, no rebuild")

    if rebuilt and os.environ.get("AKL_PUBLISH") == "1" and PUBLISH.exists():
        pr = subprocess.run(["bash", str(PUBLISH)], capture_output=True, text=True)
        line = (pr.stdout.strip().splitlines() or [""])[-1][:160]
        print(f"    publish            {'ok' if pr.returncode == 0 else 'FAILED'}  {line}")
        if pr.returncode != 0:
            build_error = build_error or f"publish: {pr.stderr.strip()[:200]}"

    status = "failed" if build_error else ("ok" if not any(
        s["status"] == "failed" for s in steps) else "partial")
    finished = datetime.now()

    record = dict(run_id=run_id, started_at=started, finished_at=finished,
                  trigger=args.trigger, status=status, changed=changed,
                  rebuilt=rebuilt, error=build_error,
                  steps=[{k: v for k, v in s.items()} for s in steps])
    log_jsonl(record)
    write_steps_to_db(run_id, steps, started, finished, args.trigger, status,
                      build_error)

    print(f"run {run_id} {status} in {(finished-started).total_seconds():.0f}s"
          + (f" — {build_error}" if build_error else ""))
    return 0 if status == "ok" else 1


def write_steps_to_db(run_id, steps, started, finished, trigger, status, note):
    """Best-effort: the JSONL log above is the record that always survives."""
    if not DB.exists() or not steps:
        return
    try:
        import duckdb
        con = duckdb.connect(str(DB))
        con.execute("""INSERT INTO pipeline_run VALUES (?,?,?,?,?,?)
                       ON CONFLICT (run_id) DO UPDATE SET
                         started_at = excluded.started_at,
                         finished_at = excluded.finished_at,
                         status = excluded.status, note = excluded.note""",
                    [run_id, started, finished, trigger, status, note])
        con.executemany(
            "INSERT INTO pipeline_step VALUES (?,?,?,?,?,?,?,?)",
            [(s["run_id"], s["source"], s["started_at"], s["finished_at"],
              s["status"], s["source_hash"], s["rows"], s["message"])
             for s in steps])
        con.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not write run log to db: {exc})", file=sys.stderr)


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
def do_status(args):
    if not DB.exists():
        print(f"{DB} not found — run the pipeline first")
        return 1
    import duckdb
    con = duckdb.connect(str(DB), read_only=True)
    cadence = {s.name: s.every_days for s in SOURCES}

    print(f"{'source':<13}{'status':<10}{'last ok':<18}{'age':<10}{'cadence':<11}"
          f"{'rows':>9}")
    rows = con.execute("SELECT * FROM pipeline_status").fetchall()
    seen = {r[0] for r in rows}
    for name, last_ok, days_ago, last_status, nrows, err in rows:
        every = cadence.get(name, 0)
        due = "DUE" if days_ago is None or days_ago >= every else f"in {every - days_ago}d"
        print(f"  {name:<11} {str(last_status):<9} {str(last_ok)[:16]:<17} "
              f"{f'{days_ago}d ago' if days_ago is not None else 'never':<9} "
              f"every {every:>3}d  {nrows or 0:>9,}  next {due}")
        if err:
            print(f"              last error: {err}")
    for s in SOURCES:
        if s.name not in seen:
            print(f"  {s.name:<11} never run")

    print("\nruns")
    for r in con.execute("""SELECT run_id, started_at, finished_at, trigger, status, note
                            FROM pipeline_run ORDER BY run_id DESC LIMIT ?""",
                         [args.n]).fetchall():
        secs = (r[2] - r[1]).total_seconds() if r[2] else None
        print(f"  #{r[0]:<4} {str(r[1])[:16]}  {r[4]:<8} {r[3]:<9} "
              f"{f'{secs:.0f}s' if secs else '-':>6}  {r[5] or ''}")

    print("\ndata")
    for k, v in [
        ("market releases", con.execute(
            "SELECT count(DISTINCT source_as_at) || ' (' || min(source_as_at) || ' .. ' "
            "|| max(source_as_at) || ')' FROM market_snapshot").fetchone()[0]),
        ("valuation rounds", con.execute(
            "SELECT string_agg(DISTINCT valuation_date::TEXT, ', ') FROM valuation").fetchone()[0]),
        ("rating units", f"{con.execute('SELECT count(*) FROM rating_unit').fetchone()[0]:,}"),
        ("suburbs", con.execute("SELECT count(*) FROM suburb").fetchone()[0]),
    ]:
        print(f"  {k:<18} {v}")
    con.close()
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--force", nargs="*", metavar="SOURCE",
                   help="fetch these regardless of cadence ('all' for everything)")
    r.add_argument("--rebuild", action="store_true",
                   help="rebuild the db and page even if no source changed")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--trigger", default="manual")
    r.set_defaults(fn=do_run)

    s = sub.add_parser("status")
    s.add_argument("-n", type=int, default=8, help="how many runs to show")
    s.set_defaults(fn=do_status)

    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()

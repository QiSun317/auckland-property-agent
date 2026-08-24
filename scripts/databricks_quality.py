#!/usr/bin/env python3
"""Data quality as something measured over time, not a pass/fail at the door.

The pipeline's gates are binary: a fetched file passes and replaces the live
one, or it fails and last month's data stays. That is the right behaviour and
it has caught real breakage — a source returning 20 suburbs instead of 205, a
currency unit change that divided every price by three. What it cannot see is
slow decay. Addresses gradually losing their suffixes, the share of parcels
carrying a coordinate sliding from 99% to 94% over a year: no single run trips
a threshold, and nothing ever says so.

Two things here, in order of how much they are worth:

1. A quality profile appended per run. Domain checks — the share of rating
   units with a capital value, of suburbs with a price, of parcels that landed
   inside a boundary — recorded as a time series so a slide is visible as a
   slide. This is the part that answers the actual gap.

2. Delta CHECK constraints on the invariants that should never be violated at
   all. Declarative, enforced by the engine on write, and they state the rule
   rather than implementing a test of the rule.

A Lakehouse Monitor is attempted first, since it is the purpose-built version
of (1). It needs a pipeline slot Free Edition may not have, so a refusal is
reported and the profile table carries on regardless.

    python3 scripts/databricks_quality.py
    python3 scripts/databricks_quality.py --history
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from databricks_sync import CATALOG, SCHEMA, sql, warehouse  # noqa: E402

NS = f"{CATALOG}.{SCHEMA}"

# Each is a share, so each is comparable to itself last week. Expressed as SQL
# against the tables that arrived, not against the raw files — this measures
# what the lakehouse actually holds.
PROFILE = {
    "rating_units": f"SELECT count(*) FROM {NS}.rating_unit",
    "ru_with_suburb": f"""SELECT count_if(suburb_id IS NOT NULL) / count(*)
                          FROM {NS}.rating_unit""",
    "ru_with_address": f"""SELECT count_if(address IS NOT NULL AND length(address) > 5)
                           / count(*) FROM {NS}.rating_unit""",
    "ru_with_land_area": f"""SELECT count_if(land_area_m2 > 0) / count(*)
                             FROM {NS}.rating_unit""",
    "valuations_with_cv": f"SELECT count_if(cv > 0) / count(*) FROM {NS}.valuation",
    "suburbs_priced": f"""SELECT count_if(avg_house_value IS NOT NULL) / count(*)
                          FROM {NS}.suburb_overview""",
    "suburbs_with_cv": f"""SELECT count_if(cv_median IS NOT NULL) / count(*)
                           FROM {NS}.suburb_overview""",
    "median_suburb_value": f"""SELECT median(avg_house_value)
                               FROM {NS}.suburb_overview""",
    "source_agreement_median": f"SELECT median(value_to_cv) FROM {NS}.source_agreement",
    "carded_rates_current": f"SELECT count_if(is_current) FROM {NS}.bank_rate",
}

# Invariants, not thresholds. A threshold is a judgement that can be argued
# with; these are things that being false means something is broken.
CONSTRAINTS = {
    "rating_unit": [("ru_lat_in_nz", "lat BETWEEN -47 AND -34"),
                    ("ru_lon_in_nz", "lon BETWEEN 166 AND 179")],
    "valuation": [("cv_not_negative", "cv IS NULL OR cv >= 0"),
                  ("lv_not_negative", "lv IS NULL OR lv >= 0")],
    "bank_rate": [("rate_is_a_mortgage_rate", "rate BETWEEN 0.5 AND 20"),
                  ("closed_after_opened", "valid_to IS NULL OR valid_to >= valid_from")],
}


def try_monitor(w, wh_id, table):
    """The purpose-built version of the profile below. Free Edition may not
    have a slot for it; that is reported, not fatal."""
    from databricks.sdk.service.catalog import MonitorSnapshot
    full = f"{NS}.{table}"
    try:
        w.quality_monitors.get(table_name=full)
        return f"already monitored: {full}"
    except Exception:  # noqa: BLE001 - not found is the normal path here
        pass
    try:
        w.quality_monitors.create(
            table_name=full,
            output_schema_name=NS,
            assets_dir=f"/Shared/quality/{table}",
            snapshot=MonitorSnapshot())
        return f"monitor created: {full}"
    except Exception as exc:  # noqa: BLE001
        return f"monitor unavailable ({str(exc)[:110]})"


def add_constraints(w, wh_id):
    added, present = [], []
    for table, rules in CONSTRAINTS.items():
        for name, expr in rules:
            try:
                sql(w, wh_id, f"ALTER TABLE {NS}.{table} "
                              f"ADD CONSTRAINT {name} CHECK ({expr})")
                added.append(f"{table}.{name}")
            except SystemExit:
                # Already there, or the data violates it. Both are worth
                # knowing and neither should stop the profile being written.
                present.append(f"{table}.{name}")
    return added, present


def write_profile(w, wh_id):
    vals = {}
    for name, q in PROFILE.items():
        try:
            v = sql(w, wh_id, q).result.data_array[0][0]
            vals[name] = None if v is None else float(v)
        except SystemExit:
            vals[name] = None
    sql(w, wh_id, f"""
        CREATE TABLE IF NOT EXISTS {NS}.data_quality (
            measured_at TIMESTAMP, metric STRING, value DOUBLE)""")
    rows = ",".join(f"(current_timestamp(), '{k}', "
                    f"{'NULL' if v is None else f'{v!r}'})" for k, v in vals.items())
    sql(w, wh_id, f"INSERT INTO {NS}.data_quality VALUES {rows}")
    return vals


def show_history(w, wh_id):
    r = sql(w, wh_id, f"""
        SELECT metric, count(*) AS runs,
               min(value) AS lo, max(value) AS hi,
               max_by(value, measured_at) AS latest
        FROM {NS}.data_quality GROUP BY 1 ORDER BY 1""")
    print(f"{'metric':<26}{'runs':>5}{'latest':>16}{'range':>28}")
    for m, n, lo, hi, latest in (r.result.data_array or []):
        rng = "—" if lo == hi else f"{float(lo):,.4g} … {float(hi):,.4g}"
        print(f"  {m:<24}{n:>5}{float(latest):>16,.4g}{rng:>28}")
    print("\n  one row per run. A share that slides over months is the thing "
          "a pass/fail gate cannot see.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("DATABRICKS_HOST"):
        sys.exit("DATABRICKS_HOST is not set")

    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    wh = warehouse(w)

    if a.history:
        return show_history(w, wh.id)

    print(f"warehouse: {wh.name}\n")
    print("  " + try_monitor(w, wh.id, "rating_unit"))

    added, present = add_constraints(w, wh.id)
    print(f"  constraints added: {', '.join(added) or 'none new'}")
    if present:
        print(f"  already present or rejected: {', '.join(present)}")

    vals = write_profile(w, wh.id)
    print(f"\n  {len(vals)} metrics -> {NS}.data_quality")
    for k, v in vals.items():
        print(f"    {k:<26}{'—' if v is None else f'{v:,.4g}':>16}")


if __name__ == "__main__":
    main()

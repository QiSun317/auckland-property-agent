#!/usr/bin/env python3
"""Create the views and saved queries the dashboard sits on.

The tables that arrive from the sync are the shapes the pipeline happens to
build in, not the shapes a question is asked in. These views are the questions:
one row per suburb with everything on it, the observed rate series, what the
revaluation did, and where the entry prices are.

Views rather than a pile of dashboard SQL on purpose. A dashboard tile that
carries its own 30-line query is a copy that drifts; a view is one definition
that every tile, notebook and ad-hoc query shares.

    python3 scripts/databricks_views.py
    python3 scripts/databricks_views.py --no-dashboard
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from databricks_sync import CATALOG, SCHEMA, sql, warehouse  # noqa: E402

NS = f"{CATALOG}.{SCHEMA}"

VIEWS = {
    # The workhorse. Everything the page knows about a suburb, on one row.
    "suburb_overview": f"""
        SELECT s.suburb_id, s.name, s.zone, s.local_board, s.cbd_km, s.area_km2,
               m.avg_house_value, m.change_1y, m.long_term_growth_pct,
               m.est_gross_yield_pct, m.median_weekly_rent, m.population,
               m.median_days_to_sell, m.sold_last_12m,
               c.units, c.cv_median, c.entry_price, c.cv_p75,
               round(m.avg_house_value / nullif(c.cv_median, 0), 3) AS value_to_cv
        FROM {NS}.suburb s
        LEFT JOIN (
            SELECT suburb_id, avg_house_value, change_1y, long_term_growth_pct,
                   est_gross_yield_pct, median_weekly_rent, population,
                   median_days_to_sell, sold_last_12m
            FROM (SELECT *, row_number() OVER (PARTITION BY suburb_id
                                               ORDER BY source_as_at DESC) rn
                  FROM {NS}.market_snapshot) WHERE rn = 1) m
          ON m.suburb_id = s.suburb_id
        LEFT JOIN (
            SELECT r.suburb_id, count(*) AS units,
                   median(v.cv) AS cv_median,
                   percentile(v.cv, 0.25) AS entry_price,
                   percentile(v.cv, 0.75) AS cv_p75
            FROM {NS}.valuation v JOIN {NS}.rating_unit r USING (ru_id)
            WHERE v.valuation_date = (SELECT max(valuation_date) FROM {NS}.valuation)
              AND v.cv > 0
            GROUP BY 1) c
          ON c.suburb_id = s.suburb_id""",

    # What the two independent sources say about the same place. The council
    # valuation and a commercial AVM agree closely in aggregate — their ratio
    # is the only cross-check this dataset has.
    "source_agreement": f"""
        SELECT name, zone, avg_house_value, cv_median, value_to_cv, units
        FROM {NS}.suburb_overview
        WHERE avg_house_value IS NOT NULL AND cv_median IS NOT NULL
          AND units >= 200""",

    # The 2021 -> 2024 revaluation, per suburb. A self-join on the long
    # valuation table, which is why it was stored long in the first place.
    "revaluation": f"""
        SELECT s.name, s.zone, count(*) AS units,
               median(a.cv) AS cv_2021, median(b.cv) AS cv_2024,
               round(median((b.cv - a.cv) / a.cv) * 100, 1) AS pct_change
        FROM {NS}.valuation a
        JOIN {NS}.valuation b
          ON a.ru_id = b.ru_id AND a.valuation_date < b.valuation_date
        JOIN {NS}.rating_unit r ON r.ru_id = a.ru_id
        JOIN {NS}.suburb s ON s.suburb_id = r.suburb_id
        WHERE a.cv > 0 AND b.cv > 0
        GROUP BY 1, 2 HAVING count(*) >= 300""",

    # The observed rate series — the thing the page cannot say today, and the
    # reason bank_rate accumulates instead of being replaced.
    "rate_series": f"""
        SELECT term, valid_from AS observed_on,
               min(rate) AS cheapest_main_bank,
               count(*) AS products
        FROM {NS}.bank_rate
        WHERE bank IN ('ANZ','ASB','BNZ','Kiwibank','Westpac')
        GROUP BY 1, 2""",
}

# The caveats that change the answer if you get them wrong. On the view rather
# than in a markdown file, because this is where someone writing
# SELECT avg_house_value will actually be looking.
VIEW_COLUMN_COMMENTS = {
    "suburb_overview": {
        "avg_house_value":
            "Average of automated valuations across all housing stock. NOT a "
            "sale price and not comparable to a sale median: the regional "
            "REINZ sale median was $980,000 over the same period while the "
            "median of these is $1,165,950. One weights by what sold, the "
            "other weights every suburb equally over all stock.",
        "cv_median":
            "Median council capital value across ALL rating units, including "
            "apartments, retail and industrial land. Apartment-dense and "
            "industrial suburbs read far below a residential interpretation.",
        "entry_price":
            "25th percentile of council capital values, i.e. what it costs to "
            "get in. Not the average, and the gap is the point: East Tamaki "
            "averages $1.07m and starts at $790,000.",
        "value_to_cv":
            "Commercial AVM divided by median council CV. The only "
            "cross-check between two independent price sources. Region-wide "
            "the median is about 1.0, which says they agree overall and "
            "nothing about where they do not.",
        "population":
            "From the market data source, not a census. Missing where the "
            "source does not cover the suburb.",
    },
}

# Saved queries so the dashboard tiles, and anyone poking around in the SQL
# editor, start from the same place.
QUERIES = {
    "Auckland · dearest and cheapest suburbs": f"""
        SELECT name, zone, avg_house_value, entry_price, cv_median, units
        FROM {NS}.suburb_overview
        WHERE avg_house_value IS NOT NULL
        ORDER BY avg_house_value DESC""",
    "Auckland · entry price by zone": f"""
        SELECT zone, count(*) AS suburbs,
               round(median(entry_price)) AS median_entry_price,
               round(median(avg_house_value)) AS median_avg_value
        FROM {NS}.suburb_overview
        WHERE entry_price IS NOT NULL AND zone IS NOT NULL
        GROUP BY 1 ORDER BY 3""",
    "Auckland · do the two price sources agree": f"""
        SELECT name, zone, avg_house_value, cv_median, value_to_cv
        FROM {NS}.source_agreement
        ORDER BY value_to_cv DESC""",
    "Auckland · revaluation impact 2021 to 2024": f"""
        SELECT name, zone, units, cv_2021, cv_2024, pct_change
        FROM {NS}.revaluation ORDER BY pct_change""",
    "Auckland · carded rate history": f"""
        SELECT term, observed_on, cheapest_main_bank, products
        FROM {NS}.rate_series ORDER BY observed_on, term""",
}


def dashboard_spec(warehouse_id):
    """A minimal Lakeview spec. Best effort — the serialized format is not a
    documented contract, so a failure here is reported rather than fatal; the
    views and saved queries above are the part that has to work."""
    ds = [
        {"name": "by_zone", "displayName": "Entry price by zone",
         "queryLines": [QUERIES["Auckland · entry price by zone"]]},
        {"name": "agreement", "displayName": "Source agreement",
         "queryLines": [QUERIES["Auckland · do the two price sources agree"]]},
    ]
    widget = lambda n, dsn, wtype, x, y, enc: {
        "widget": {"name": n,
                   "queries": [{"name": "main",
                                "query": {"datasetName": dsn,
                                          "fields": enc["fields"],
                                          "disaggregated": False}}],
                   "spec": {"version": 3, "widgetType": wtype,
                            "encodings": enc["encodings"]}},
        "position": {"x": x, "y": y, "width": 3, "height": 6}}
    return json.dumps({
        "datasets": ds,
        "pages": [{
            "name": "overview", "displayName": "Auckland",
            "layout": [
                widget("zones", "by_zone", "bar", 0, 0, {
                    "fields": [{"name": "zone", "expression": "`zone`"},
                               {"name": "median_entry_price",
                                "expression": "`median_entry_price`"}],
                    "encodings": {
                        "x": {"fieldName": "zone", "scale": {"type": "categorical"},
                              "displayName": "Zone"},
                        "y": {"fieldName": "median_entry_price",
                              "scale": {"type": "quantitative"},
                              "displayName": "Median entry price"}}}),
                widget("agree", "agreement", "table", 3, 0, {
                    "fields": [{"name": "name", "expression": "`name`"},
                               {"name": "value_to_cv", "expression": "`value_to_cv`"}],
                    "encodings": {"columns": [
                        {"fieldName": "name", "displayName": "Suburb"},
                        {"fieldName": "value_to_cv", "displayName": "AVM / CV"}]}}),
            ]}]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-dashboard", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("DATABRICKS_HOST"):
        sys.exit("DATABRICKS_HOST is not set")

    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    wh = warehouse(w)
    print(f"warehouse: {wh.name}\n")

    for name, body in VIEWS.items():
        # A view takes its column comments in its own definition — ALTER VIEW
        # ALTER COLUMN COMMENT is rejected — so the contract is declared with
        # the view rather than bolted on afterwards.
        cols = VIEW_COLUMN_COMMENTS.get(name)
        spec = ""
        if cols:
            got = sql(w, wh.id, f"SELECT * FROM ({body}) LIMIT 0")
            names = [c.name for c in got.manifest.schema.columns]
            spec = " (" + ", ".join(
                f"{c} COMMENT '{cols[c]}'" if c in cols else c
                for c in names) + ")"
        sql(w, wh.id, f"CREATE OR REPLACE VIEW {NS}.{name}{spec} AS {body}")
        n = sql(w, wh.id, f"SELECT count(*) FROM {NS}.{name}").result.data_array[0][0]
        print(f"  view  {NS}.{name:<20} {int(n):>6,} rows")

    from databricks.sdk.service.sql import CreateQueryRequestQuery
    existing = {q.display_name for q in w.queries.list()}
    for title, text in QUERIES.items():
        if title in existing:
            print(f"  query {title}  (already there)")
            continue
        w.queries.create(query=CreateQueryRequestQuery(
            display_name=title, query_text=text.strip(),
            warehouse_id=wh.id, catalog=CATALOG, schema=SCHEMA,
            description="Generated by scripts/databricks_views.py"))
        print(f"  query {title}")

    if a.no_dashboard:
        return
    try:
        from databricks.sdk.service.dashboards import Dashboard
        me = w.current_user.me().user_name
        d = w.lakeview.create(dashboard=Dashboard(
            display_name="Auckland property",
            parent_path=f"/Users/{me}",
            warehouse_id=wh.id,
            serialized_dashboard=dashboard_spec(wh.id)))
        print(f"\n  dashboard: {d.dashboard_id}")
    except Exception as exc:  # noqa: BLE001 - the views are the deliverable
        print(f"\n  dashboard not created: {str(exc)[:160]}")
        print("  the views and saved queries are in place; build one from a "
              "saved query in the SQL editor")


if __name__ == "__main__":
    main()

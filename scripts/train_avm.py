#!/usr/bin/env python3
"""Model the gap between the two price sources, and log it to MLflow.

The page carries one caveat everywhere: `price` is a commercial automated
valuation, not a sale price, and it comes from a single vendor. The council's
capital values are a completely independent second opinion covering every
parcel. In aggregate they agree — the median of their ratios is about 1.0 —
which is reassuring and also uninformative, because it says nothing about
*where* they disagree.

So this does not try to build a better valuation. It asks a narrower and more
answerable question: how much of the commercial AVM is explained by the council
valuation plus plain geography, and which suburbs refuse to be explained. The
residual is the useful output — a suburb whose AVM sits far from what its own
CV distribution predicts is a suburb where the two sources disagree, and that
is exactly the per-suburb confidence the roadmap has been asking for.

Trained in CI on a few hundred rows and logged to the workspace's MLflow, which
is the honest shape of this: the modelling is small, the tracking is what makes
it repeatable. Predictions are written back as a table so the page can read a
confidence without re-running anything.

    python3 scripts/train_avm.py
    python3 scripts/train_avm.py --no-write   # train and log, write nothing back
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from databricks_sync import CATALOG, SCHEMA, sql, warehouse  # noqa: E402

NS = f"{CATALOG}.{SCHEMA}"
EXPERIMENT = "auckland-source-agreement"

FEATURES = ["cv_median", "entry_price", "cv_p75", "units",
            "cbd_km", "area_km2", "population"]
TARGET = "avg_house_value"


def load(w, wh_id):
    """Features come out of the lakehouse, not the local database. That is the
    point of having put them there."""
    cols = ", ".join(["name", "zone", TARGET] + FEATURES)
    r = sql(w, wh_id, f"""
        SELECT {cols} FROM {NS}.suburb_overview
        WHERE {TARGET} IS NOT NULL AND cv_median IS NOT NULL
          AND units >= 100""")
    rows = r.result.data_array or []
    names = [x[0] for x in rows]
    zones = [x[1] or "unknown" for x in rows]
    y = [float(x[2]) for x in rows]
    X = [[float(v) if v is not None else float("nan") for v in x[3:]] for x in rows]
    return names, zones, X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("DATABRICKS_HOST"):
        sys.exit("DATABRICKS_HOST is not set")

    import numpy as np
    import mlflow
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import RidgeCV
    from sklearn.model_selection import KFold, cross_val_predict
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    wh = warehouse(w)
    names, zones, X, y = load(w, wh.id)
    n = len(y)
    if n < 50:
        sys.exit(f"only {n} suburbs have both sources — too few to model")
    print(f"{n} suburbs with both a commercial AVM and a council CV distribution")

    Xn = np.array(X, dtype=float)
    Z = np.array(zones, dtype=object).reshape(-1, 1)
    yv = np.array(y, dtype=float)

    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), list(range(len(FEATURES)))),
        ("zone", OneHotEncoder(handle_unknown="ignore"), [len(FEATURES)]),
    ])
    design = np.hstack([Xn, Z])

    models = {
        "ridge": RidgeCV(alphas=np.logspace(-3, 3, 25)),
        "gbr": GradientBoostingRegressor(random_state=0, n_estimators=300,
                                         max_depth=3, learning_rate=0.05),
    }

    mlflow.set_tracking_uri("databricks")
    me = w.current_user.me().user_name
    mlflow.set_experiment(f"/Users/{me}/{EXPERIMENT}")

    # Out-of-fold predictions, not in-sample: with a few hundred rows an
    # in-sample R^2 would look excellent and mean nothing.
    cv = KFold(n_splits=5, shuffle=True, random_state=0)
    best, results = None, {}
    for label, est in models.items():
        pipe = Pipeline([("pre", pre), ("est", est)])
        with mlflow.start_run(run_name=label):
            pred = cross_val_predict(pipe, design, yv, cv=cv)
            err = pred - yv
            mape = float(np.mean(np.abs(err / yv)) * 100)
            rmse = float(np.sqrt(np.mean(err ** 2)))
            r2 = float(1 - np.sum(err ** 2) / np.sum((yv - yv.mean()) ** 2))
            mlflow.log_params({"model": label, "n_suburbs": n,
                               "features": ",".join(FEATURES), "folds": 5})
            mlflow.log_metrics({"cv_mape_pct": mape, "cv_rmse": rmse, "cv_r2": r2})
            pipe.fit(design, yv)
            # cloudpickle, not the default: MLflow now serialises sklearn
            # through skops, which refuses numpy.dtype as an untrusted type and
            # fails on any pipeline with a scaler in it.
            mlflow.sklearn.log_model(pipe, name=label,
                                     serialization_format="cloudpickle")
            results[label] = (mape, rmse, r2, pred)
            print(f"  {label:<6} out-of-fold  MAPE {mape:5.2f}%   "
                  f"RMSE {rmse:>10,.0f}   R2 {r2:.3f}")
            if best is None or mape < results[best][0]:
                best = label

    mape, rmse, r2, pred = results[best]
    print(f"\nbest: {best} (MAPE {mape:.2f}%)")

    # The residual is the deliverable. A suburb the model cannot explain is one
    # where the vendor's AVM and the council's valuations tell different
    # stories, and that is what a reader deserves to be warned about.
    resid_pct = (yv - pred) / yv * 100
    order = np.argsort(-np.abs(resid_pct))
    print("\nwhere the two sources disagree most:")
    for i in order[:8]:
        print(f"  {names[i]:<24} AVM {yv[i]:>10,.0f}   "
              f"model {pred[i]:>10,.0f}   {resid_pct[i]:+6.1f}%")

    if a.no_write:
        return
    # A confidence band rather than a raw residual: the number the page would
    # show has to survive being read quickly.
    vals = []
    for name, p, r in zip(names, pred, resid_pct):
        band = "high" if abs(r) < 10 else ("medium" if abs(r) < 25 else "low")
        vals.append(f"('{name.replace(chr(39), chr(39) * 2)}', {p:.0f}, "
                    f"{r:.2f}, '{band}')")
    sql(w, wh.id, f"""
        CREATE OR REPLACE TABLE {NS}.suburb_confidence AS
        SELECT * FROM VALUES {','.join(vals)}
        AS t(name, model_value, residual_pct, confidence)""")
    print(f"\nwrote {NS}.suburb_confidence ({len(vals)} suburbs)")
    for band in ("high", "medium", "low"):
        c = sum(1 for v in vals if f"'{band}')" in v)
        print(f"  {band:<7} {c:>4}")


if __name__ == "__main__":
    main()

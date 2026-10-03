"""Expanding-window ridge fits with a small number of sign restrictions."""

import numpy as np
from scipy.optimize import lsq_linear
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .features import PARTS


def training_rows(rows, target, columns, outcome):
    return [
        r
        for r in rows
        if r["target_month"] < target["target_month"]
        and r["release_date"]
        and r["release_date"] <= target["forecast_cutoff"]
        and r.get(outcome) is not None
        and all(r.get(c) is not None for c in columns)
    ]


def fit(train, target, spec, outcome):
    columns, alpha = spec["columns"], spec["alpha"]
    scale = StandardScaler().fit([[r[c] for c in columns] for r in train])
    x = scale.transform([[r[c] for c in columns] for r in train])
    tx = scale.transform([[target[c] for c in columns]])
    y = np.array([r[outcome] for r in train])
    if spec["positive"]:
        xm, ym = x.mean(axis=0), y.mean()
        xx = np.vstack([x - xm, np.sqrt(alpha) * np.eye(len(columns))])
        yy = np.concatenate([y - ym, np.zeros(len(columns))])
        lower = np.array([0.0 if c in spec["positive"] else -np.inf for c in columns])
        fitted = lsq_linear(xx, yy, bounds=(lower, np.inf), tol=1e-10, max_iter=1000)
        if not fitted.success:
            raise ValueError("Constrained fit failed: " + fitted.message)
        coef = fitted.x
        intercept = float(ym - xm @ coef)
        prediction = float(tx[0] @ coef + intercept)
    else:
        model = Ridge(alpha=alpha).fit(x, y)
        coef, intercept = model.coef_, float(model.intercept_)
        prediction = float(model.predict(tx)[0])
    if not np.isfinite(prediction):
        raise ValueError("Nonfinite prediction")
    return prediction, {
        "columns": columns,
        "positive": spec["positive"],
        "alpha": alpha,
        "training_months": [r["target_month"] for r in train],
        "latest_training_release": max(r["release_date"] for r in train),
        "means": scale.mean_.tolist(),
        "scales": scale.scale_.tolist(),
        "coefficients": coef.tolist(),
        "intercept": intercept,
    }


def evaluate(rows, config):
    records, fits, exclusions = [], [], []
    with threadpool_limits(limits=1):
        for target in rows:
            month = target["target_month"]
            if not config["evaluation_start"] <= month <= config["evaluation_end"]:
                continue
            reasons = []
            if target["actual_percent"] is None:
                reasons.append("No genuine adjacent-month first-release outcome")
            if any(target["core_" + k] is None for k in ("lag1", "avg3", "avg12")):
                reasons.append("Insufficient core CPI history")
            if target["weights"] is None:
                reasons.append("No January weights")
            prepared = {}
            for part, spec in config["parent"].items():
                train = training_rows(rows, target, spec["columns"], part + "_actual")
                missing = [c for c in spec["columns"] if target[c] is None]
                if missing or len(train) < config["minimum_training_rows"]:
                    reasons.append(
                        f"{part}: missing inputs {missing} or only {len(train)} training months"
                    )
                prepared[part] = train
            factory_spec = config["factory"]
            factory_train = training_rows(
                rows, target, factory_spec["columns"], "actual_percent"
            )
            if (
                any(target[c] is None for c in factory_spec["columns"])
                or len(factory_train) < config["minimum_training_rows"]
            ):
                reasons.append("Factory benchmark unavailable")
            if reasons:
                exclusions.append({"target_month": month, "reason": "; ".join(reasons)})
                continue
            prior, final = {}, {}
            for part in PARTS:
                outcome = part + "_actual"
                prior[part], detail = fit(
                    prepared[part], target, config["parent"][part], outcome
                )
                fits.append(
                    {
                        "month": month,
                        "model": "prior",
                        "part": part,
                        "prediction": prior[part],
                        **detail,
                    }
                )
                spec = config["final"][part]
                if spec == config["parent"][part]:
                    final[part] = prior[part]
                    continue
                train = training_rows(rows, target, spec["columns"], outcome)
                fallback = len(train) < config["minimum_training_rows"] or any(
                    target[c] is None for c in spec["columns"]
                )
                if fallback:
                    final[part], detail = prior[part], {"fallback": True}
                else:
                    final[part], detail = fit(train, target, spec, outcome)
                fits.append(
                    {
                        "month": month,
                        "model": "final",
                        "part": part,
                        "prediction": final[part],
                        **detail,
                    }
                )
            factory, detail = fit(factory_train, target, factory_spec, "actual_percent")
            fits.append(
                {
                    "month": month,
                    "model": "factory",
                    "part": "core",
                    "prediction": factory,
                    **detail,
                }
            )
            predictions = {
                "final": sum(target["weights"][p] * final[p] for p in PARTS),
                "prior": sum(target["weights"][p] * prior[p] for p in PARTS),
                "factory": factory,
                "average12": target["core_avg12"],
            }
            for name, prediction in predictions.items():
                error = prediction - target["actual_percent"]
                records.append(
                    {
                        "model": name,
                        "target_month": month,
                        "forecast_cutoff": target["forecast_cutoff"],
                        "release_date": target["release_date"],
                        "forecast_percent": prediction,
                        "actual_percent": target["actual_percent"],
                        "error_pp": error,
                        "absolute_error_pp": abs(error),
                    }
                )
    return records, fits, exclusions


def scores(records):
    result = {}
    for model in ("final", "prior", "factory", "average12"):
        selected = [r for r in records if r["model"] == model]
        periods = {
            "2019-2024": [r for r in selected if r["target_month"] < "2025"],
            "2025-2026": [r for r in selected if r["target_month"] >= "2025"],
        }
        periods.update(
            {
                str(y): [r for r in selected if r["target_month"].startswith(str(y))]
                for y in range(2019, 2027)
            }
        )
        result[model] = {}
        for name, rows in periods.items():
            if not rows:
                continue
            e = np.array([r["error_pp"] for r in rows])
            result[model][name] = {
                "months": len(e),
                "mae_pp": float(abs(e).mean()),
                "rmse_pp": float(np.sqrt(np.mean(e * e))),
                "max_error_pp": float(abs(e).max()),
                "p90_error_pp": float(np.quantile(abs(e), 0.9)),
                "bias_pp": float(e.mean()),
                "misses_over_020_pp": int(sum(abs(e) > 0.2)),
            }
    return result


def verify_reference(records, reference, outcomes, tolerance=1e-8):
    actual = {(r["target_month"], r["model"]): r["forecast_percent"] for r in records}
    expected = {
        (month, model): value
        for month, models in reference.items()
        for model, value in models.items()
    }
    if actual.keys() != expected.keys():
        raise ValueError("Forecast dates/models differ from the published reference")
    for row in records:
        outcome = row["actual_percent"]
        if (
            not np.isfinite(outcome)
            or abs(outcome - outcomes[row["target_month"]]) > tolerance
        ):
            raise ValueError(
                "First-release outcome differs from the published reference"
            )
    if not all(np.isfinite(value) for value in actual.values()):
        raise ValueError("Nonfinite forecast in reference check")
    largest = max(abs(actual[k] - v) for k, v in expected.items())
    if largest > tolerance:
        raise ValueError(
            f"Forecasts differ from published results by {largest:g} pp (tolerance {tolerance:g})"
        )
    return largest

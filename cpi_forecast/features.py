"""Convert dated source observations into model inputs. No fitted parameters here."""

import math
from datetime import date

PARTS = ("rent", "oer", "used", "air", "hotel", "medical", "remainder")


def offset(month, steps):
    year, m = divmod(month.year * 12 + month.month - 1 + steps, 12)
    return date(year, m + 1, 1)


def growth(snapshot, month, periods=1):
    a, b = snapshot.get(str(month)), snapshot.get(str(offset(month, -periods)))
    if a is None or b is None:
        return None
    if a <= 0 or b <= 0:
        raise ValueError("Index levels must be positive")
    return 100 * (a / b - 1)


def lags(snapshot, month):
    if any(d >= str(month) and x is not None for d, x in snapshot.items()):
        raise ValueError("A cutoff snapshot contains unreleased CPI")
    values = [growth(snapshot, offset(month, -i)) for i in range(1, 13)]
    recent = [x for x in values[:3] if x is not None]
    annual = [x for x in values if x is not None]
    return {
        "lag1": values[0],
        "avg3": sum(recent) / len(recent) if len(recent) >= 2 else None,
        "avg12": sum(annual) / len(annual) if len(annual) >= 10 else None,
    }


def build_features(observations, calendar):
    rows = []
    snapshots = observations["snapshots"]
    for entry in calendar:
        r = dict(entry)
        month = date.fromisoformat(r["target_month"])
        cutoff, release = r["forecast_cutoff"], r["release_date"]
        for name in ("core", *PARTS[:-1]):
            s = snapshots[name].get(cutoff, {})
            r.update({name + "_" + k: v for k, v in lags(s, month).items()})
            actual = growth(snapshots[name].get(release, {}), month)
            r["actual_percent" if name == "core" else name + "_actual"] = actual
        for name in ("wage", "ppi", "inventory"):
            s = snapshots[name].get(cutoff, {})
            available = [d for d, x in s.items() if x is not None and d < str(month)]
            latest = date.fromisoformat(max(available)) if available else None
            if (
                latest
                and (month.year - latest.year) * 12 + month.month - latest.month > 3
            ):
                latest = None
            r[name + "_growth3"] = growth(s, latest, 3) if latest else None
            r[name + "_level"] = s[str(latest)] if latest else None
        s = snapshots["jet"].get(cutoff, {})
        means = {}
        for lag in (0, 1, 3):
            prefix = str(offset(month, -lag))[:7]
            values = [
                v
                for d, v in s.items()
                if v is not None and d < cutoff and d.startswith(prefix)
            ]
            means[lag] = sum(values) / len(values) if len(values) >= 10 else None
        for lag in (1, 3):
            r["jet_change" + str(lag)] = (
                100 * (means[0] / means[lag] - 1) if means[0] and means[lag] else None
            )
        factory = observations["factory"]
        current = factory.get(str(month))
        r["empire_prices_paid"] = (
            current["value"] if current and current["release_date"] <= cutoff else None
        )
        prior = [factory.get(str(offset(month, -i))) for i in range(4)]
        r["factory_change3"] = (
            current["value"] - prior[-1]["value"]
            if all(p and p["release_date"] <= cutoff for p in prior)
            else None
        )
        for lag in (6, 12):
            r["zori_growth12_lag" + str(lag)] = growth(
                observations["zori"], offset(month, -lag), 12
            )
        for lag in (1, 2, 3):
            r["manheim_growth1_lag" + str(lag)] = growth(
                observations["manheim"], offset(month, -lag)
            )
        car3 = growth(observations["manheim"], offset(month, -1), 3)
        car_changes = [r["manheim_growth1_lag" + str(i)] for i in (1, 2, 3)]
        wholesale = (
            sum(car_changes) / 3 if all(v is not None for v in car_changes) else None
        )
        r["wholesale_positive"] = max(0, wholesale) if wholesale is not None else None
        r["wholesale_negative"] = min(0, wholesale) if wholesale is not None else None
        retail = growth(snapshots["used"].get(cutoff, {}), offset(month, -1), 3)
        r["retail_catchup_gap3_exact"] = (
            car3 - retail if car3 is not None and retail is not None else None
        )
        for prefix in ("month", "year"):
            r[prefix + "_sin"] = math.sin(2 * math.pi * month.month / 12)
            r[prefix + "_cos"] = math.cos(2 * math.pi * month.month / 12)
        claims = sorted(
            (d, v)
            for d, v in snapshots["claims"].get(cutoff, {}).items()
            if v is not None and d < cutoff
        )
        valid = (
            len(claims) >= 8
            and (date.fromisoformat(cutoff) - date.fromisoformat(claims[-1][0])).days
            <= 14
        )
        recent = sum(v for _, v in claims[-4:]) / 4 if valid else None
        past = sum(v for _, v in claims[-8:-4]) / 4 if valid else None
        r["demand_level"] = -math.log(recent / 250000) if valid else None
        r["demand_change"] = -math.log(recent / past) if valid else None
        r["health_reset"] = float(
            month.month == 10 or (month >= date(2024, 4, 1) and month.month == 4)
        )
        health = observations["health"].get(str(offset(month, -1)))
        value = health["value"] if health and health["release_date"] <= cutoff else None
        r["health_continuation"] = (
            value * (1 - r["health_reset"]) if value is not None else None
        )
        weight = observations["weights"].get(str(month.year))
        if weight and weight["release_date"] > cutoff:
            raise ValueError("Weights published after the forecast cutoff")
        r["weights"] = weight["values"] if weight else None
        for suffix in ("lag1", "avg3", "avg12", "actual"):
            values = {p: r[p + "_" + suffix] for p in PARTS[:-1]}
            core = r["actual_percent"] if suffix == "actual" else r["core_" + suffix]
            w = r["weights"]
            r["remainder_" + suffix] = (
                (core - sum(w[p] * v for p, v in values.items())) / w["remainder"]
                if w
                and core is not None
                and all(v is not None for v in values.values())
                else None
            )
        rows.append(r)
    return rows

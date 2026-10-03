"""Small, static report suitable for a GitHub README."""

import csv
import json
from datetime import date
from pathlib import Path

LABELS = {
    "final": "Final component model",
    "prior": "Earlier component model",
    "factory": "CPI + factory regression",
    "average12": "12-month average",
}


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def write_csv(path, rows):
    if not rows:
        raise ValueError("Refusing to write an empty report: " + str(path))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(output, rows, fits, exclusions, metrics):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "forecasts.csv", rows)
    write_csv(output / "exclusions.csv", exclusions)
    write_json(output / "metrics.json", metrics)
    write_json(output / "fits.json", fits)
    lines = [
        "# Results",
        "",
        "Errors are percentage points of monthly core CPI. Lower is better.",
        "",
        "| Model | 2019–24 MAE (71 months) | 2025–Aug 2026 MAE (16 months) |",
        "|---|---:|---:|",
    ]
    for model, label in LABELS.items():
        lines.append(
            f"| {label} | {metrics[model]['2019-2024']['mae_pp']:.4f} | {metrics[model]['2025-2026']['mae_pp']:.4f} |"
        )
    lines += [
        "",
        "Both periods were inspected during development. Zillow and Manheim use revised histories.",
        "The 12-month average beats the final model in the recent period.",
        "",
    ]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    # Headless backend makes the same command work on CI and servers.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}
    )
    final = [r for r in rows if r["model"] == "final"]
    from .features import offset

    lookup = {r["target_month"]: r for r in final}
    xs = []
    current = date.fromisoformat(final[0]["target_month"])
    end = date.fromisoformat(final[-1]["target_month"])
    while current <= end:
        xs.append(current)
        current = offset(current, 1)
    # Break the lines at excluded months rather than visually filling the gaps.
    actual = [lookup.get(str(m), {}).get("actual_percent", float("nan")) for m in xs]
    predicted = [
        lookup.get(str(m), {}).get("forecast_percent", float("nan")) for m in xs
    ]
    fig, ax = plt.subplots(figsize=(11, 4.5), layout="constrained")
    ax.plot(xs, actual, color="#27272a", label="First-release core CPI", linewidth=1.4)
    ax.plot(xs, predicted, color="#216a8c", label="Final model", linewidth=1.4)
    ax.axhline(0, color="#aaa", linewidth=0.6)
    ax.set(
        title="Monthly core CPI: forecast and first release",
        ylabel="Monthly change (%)",
    )
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="y", alpha=0.15)
    fig.savefig(output / "forecasts.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4.5), layout="constrained")
    years = list(range(2019, 2027))
    for j, (model, color) in enumerate(
        [("final", "#216a8c"), ("factory", "#a1b8b8"), ("average12", "#c3c3c3")]
    ):
        ax.bar(
            [i + (j - 1) * 0.25 for i in range(len(years))],
            [metrics[model][str(y)]["mae_pp"] for y in years],
            width=0.24,
            label=LABELS[model],
            color=color,
        )
    ax.set_xticks(
        range(len(years)), [str(y) + ("*" if y >= 2025 else "") for y in years]
    )
    ax.set(
        title="Forecast error by year", ylabel="Mean absolute error (percentage points)"
    )
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.15)
    ax.set_xlabel(
        "* 2025–26 have missing months; 2026 ends in August. See exclusions.csv.",
        fontsize=9,
        loc="left",
    )
    fig.savefig(output / "yearly_errors.png", dpi=160)
    plt.close(fig)

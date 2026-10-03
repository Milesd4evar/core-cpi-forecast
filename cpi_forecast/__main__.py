"""Run with python -m cpi_forecast from the repository root."""

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

from .features import build_features
from .model import evaluate, scores, verify_reference
from .report import write_json, write_report

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser(
        "reproduce",
        help="Build inputs, refit models and check historical forecasts (offline)",
    )
    rep.add_argument(
        "--observations", type=Path, default=ROOT / "data/observations.json.gz"
    )
    rep.add_argument("--output", type=Path, default=ROOT / "build/results")
    rep.add_argument(
        "--no-reference-check",
        action="store_true",
        help="Allow revised source data to produce different results",
    )
    fetch = sub.add_parser(
        "fetch",
        help="Download source observations into a separate file (network required)",
    )
    fetch.add_argument("--cache", type=Path, default=ROOT / "build/cache")
    fetch.add_argument(
        "--output", type=Path, default=ROOT / "build/downloaded_observations.json.gz"
    )
    fetch.add_argument(
        "--offline", action="store_true", help="Parse only already-cached raw downloads"
    )
    args = parser.parse_args()
    if args.command == "fetch":
        from .sources import collect, save_observations

        if args.output.resolve() == (ROOT / "data/observations.json.gz").resolve():
            parser.error(
                "Choose a separate output; keep the published snapshot intact."
            )
        try:
            obs, audit = collect(
                read_json(ROOT / "data/sources.json"), args.cache, args.offline
            )
        except (OSError, ValueError) as exc:
            parser.exit(1, f"Download failed: {exc}\n")
        save_observations(args.output, obs)
        print(
            f"Saved {args.output.resolve()}. {len(audit['changed_sources'])} source files differ from the original download."
        )
        return
    # Check all shipped inputs; custom downloads have their own audit in the cache.
    manifest = read_json(ROOT / "data/checksums.json")
    for name, expected in manifest.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Bundled input changed: " + name)
    observations = json.loads(gzip.decompress(args.observations.read_bytes()))
    features = build_features(observations, read_json(ROOT / "data/calendar.json"))
    records, fits, exclusions = evaluate(features, read_json(ROOT / "data/model.json"))
    difference = (
        None
        if args.no_reference_check
        else verify_reference(
            records,
            read_json(ROOT / "data/reference_forecasts.json"),
            read_json(ROOT / "data/reference_outcomes.json"),
        )
    )
    metrics = scores(records)
    write_report(args.output, records, fits, exclusions, metrics)
    write_json(args.output / "features.json", features)
    write_json(
        args.output / "run.json",
        {
            "python": platform.python_version(),
            "packages": {
                p: importlib.metadata.version(p)
                for p in ("numpy", "scipy", "scikit-learn", "matplotlib", "pypdf")
            },
            "observation_sha256": hashlib.sha256(
                args.observations.read_bytes()
            ).hexdigest(),
            "reference_checked": not args.no_reference_check,
            "largest_forecast_difference_pp": difference,
            "feature_rows": len(features),
            "scored_months": len(records) // 4,
        },
    )
    print(
        f"Rebuilt {len(features)} monthly input rows; refitted {len(fits)} equations; scored {len(records) // 4} months."
    )
    if difference is not None:
        print(
            f"All {len(records)} forecasts match the reference within 1e-8 pp; maximum difference {difference:.3g}."
        )
    else:
        print(
            "Reference check skipped: these results may differ from the published snapshot."
        )
    print((args.output / "summary.md").read_text(encoding="utf-8"))
    print("Outputs:", args.output.resolve())


if __name__ == "__main__":
    main()

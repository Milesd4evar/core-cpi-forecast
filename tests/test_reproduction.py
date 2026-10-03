"""Check real forecast equivalence, chronology, missing data and source parsing."""

import copy
import gzip
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from cpi_forecast.features import build_features, growth, lags
from cpi_forecast.model import evaluate, training_rows, verify_reference
from cpi_forecast.parsers import parse_release
from cpi_forecast.sources import fetch

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class ReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observations = json.loads(
            gzip.decompress((ROOT / "data/observations.json.gz").read_bytes())
        )
        cls.calendar = read("data/calendar.json")
        # A hidden network dependency must fail, rather than silently use local credentials.
        with patch(
            "socket.socket",
            side_effect=AssertionError("Reproduction attempted network access"),
        ):
            cls.rows = build_features(cls.observations, cls.calendar)
            cls.records, cls.fits, cls.exclusions = evaluate(
                cls.rows, read("data/model.json")
            )

    def test_all_348_refitted_forecasts_match_research_results(self):
        self.assertEqual(len(self.records), 348)
        self.assertLess(
            verify_reference(
                self.records,
                read("data/reference_forecasts.json"),
                read("data/reference_outcomes.json"),
            ),
            1e-8,
        )

    def test_changed_outcome_cannot_pass_as_reproduced_results(self):
        changed = copy.deepcopy(self.records)
        changed[-1]["actual_percent"] += 1.0
        with self.assertRaisesRegex(ValueError, "First-release outcome differs"):
            verify_reference(
                changed,
                read("data/reference_forecasts.json"),
                read("data/reference_outcomes.json"),
            )

    def test_all_inputs_match_original_research(self):
        expected = read("tests/reference_features.json")
        self.assertEqual(len(self.rows), len(expected))
        for actual, reference in zip(self.rows, expected):
            for key, value in reference.items():
                with self.subTest(month=reference["target_month"], column=key):
                    if isinstance(value, (int, float)):
                        self.assertAlmostEqual(actual[key], value, places=10)
                    else:
                        self.assertEqual(actual[key], value)

    def test_every_fit_uses_earlier_released_outcomes_and_nonnegative_constrained_slopes(
        self,
    ):
        lookup = {r["target_month"]: r for r in self.rows}
        for fit in self.fits:
            if fit.get("fallback"):
                continue
            target = lookup[fit["month"]]
            self.assertLessEqual(
                fit["latest_training_release"], target["forecast_cutoff"]
            )
            for month in fit["training_months"]:
                self.assertLess(month, target["target_month"])
                self.assertLessEqual(
                    lookup[month]["release_date"], target["forecast_cutoff"]
                )
            for col, coef in zip(fit["columns"], fit["coefficients"]):
                if col in fit["positive"]:
                    self.assertGreaterEqual(coef, -1e-9)

    def test_published_result_dates_and_missing_month_exclusions(self):
        dates = {r["target_month"] for r in self.records}
        self.assertEqual(sum(m < "2025" for m in dates), 71)
        self.assertEqual(sum(m >= "2025" for m in dates), 16)
        self.assertEqual(
            {r["target_month"] for r in self.exclusions},
            {"2024-06-01", "2025-10-01", "2025-11-01", "2025-12-01", "2026-01-01"},
        )
        for model in ("prior", "factory", "average12"):
            self.assertEqual(
                dates, {r["target_month"] for r in self.records if r["model"] == model}
            )

    def test_future_outcomes_do_not_change_earlier_predictions(self):
        target = next(r for r in self.rows if r["target_month"] == "2025-01-01")
        altered = copy.deepcopy(self.rows)
        for r in altered:
            if r["target_month"] >= target["target_month"]:
                for key in r:
                    if key.endswith("_actual") or key == "actual_percent":
                        r[key] = 10000.0
        config = read("data/model.json")
        config["evaluation_start"] = config["evaluation_end"] = target["target_month"]
        changed, _, _ = evaluate(altered, config)
        expected = {
            r["model"]: r["forecast_percent"]
            for r in self.records
            if r["target_month"] == target["target_month"]
        }
        for row in changed:
            self.assertAlmostEqual(
                row["forecast_percent"], expected[row["model"]], places=12
            )

    def test_calendar_earlier_but_unreleased_outcome_is_excluded(self):
        rows = [
            {
                "target_month": "2024-12-01",
                "release_date": "2025-02-01",
                "x": 2.0,
                "y": 1.0,
            }
        ]
        target = {"target_month": "2025-01-01", "forecast_cutoff": "2025-01-31"}
        self.assertEqual(training_rows(rows, target, ["x"], "y"), [])

    def test_missing_adjacent_level_is_not_interpolated(self):
        snapshot = {"2025-09-01": 100.0, "2025-10-01": None, "2025-11-01": 101.0}
        self.assertIsNone(growth(snapshot, date(2025, 11, 1)))
        self.assertIsNone(lags(snapshot, date(2025, 12, 1))["lag1"])

    def test_future_cpi_level_in_input_snapshot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unreleased CPI"):
            lags({"2025-01-01": 100.0}, date(2025, 1, 1))

    def test_weights_reconstruct_core_outcome(self):
        for row in self.rows:
            weights = row["weights"]
            if weights and all(row[p + "_actual"] is not None for p in weights):
                self.assertAlmostEqual(sum(weights.values()), 1.0)
                self.assertAlmostEqual(
                    sum(w * row[p + "_actual"] for p, w in weights.items()),
                    row["actual_percent"],
                    places=12,
                )

    def test_all_bundled_data_hashes_match(self):
        for name, expected in read("data/checksums.json").items():
            self.assertEqual(
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected
            )


class SourceTests(unittest.TestCase):
    def test_spaced_pdf_digits_preserve_cell_boundaries(self):
        parsed = parse_release((ROOT / "tests/fixtures/cpi_20161117.pdf").read_bytes())
        self.assertEqual(
            parsed["health"]["numeric_values"], [1.016, 6.9, -0.1, 1.1, -0.1, -0.1]
        )

    def test_pdf_missing_current_value_remains_missing(self):
        parsed = parse_release((ROOT / "tests/fixtures/cpi_20260113.pdf").read_bytes())
        self.assertIsNone(parsed["motor"]["monthly"])
        self.assertEqual(parsed["health"]["monthly"], -1.1)

    def test_missing_offline_download_is_explicit_and_does_not_use_network(self):
        with (
            tempfile.TemporaryDirectory() as cache,
            patch("urllib.request.urlopen", side_effect=AssertionError("network")),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "Missing offline source"):
                fetch("https://example.com/missing", cache, offline=True)


if __name__ == "__main__":
    unittest.main()

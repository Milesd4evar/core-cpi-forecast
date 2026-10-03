# Reproducing and inspecting the project

## Supported route: saved observations → freshly fitted results

Follow the commands in the [README](../README.md). Use Python 3.13 and the pinned `requirements.txt`. The repository has all required data and parser fixtures. It does not read from the original research folder, home directory, browser session or environment secrets.

`python -m cpi_forecast reproduce`:

1. Checks the bundled input hashes.
2. Converts saved source observations into 176 monthly feature rows.
3. Refits the earlier and final component models plus the factory benchmark, using only prior released outcomes and training-sample scaling.
4. Computes the trailing-average benchmark on the same dates.
5. Checks every forecast against the historical reference, with tolerance `1e-8` percentage points.
6. Writes the results to `build/results/` without overwriting the committed result examples.

The golden forecasts are read only after fitting. Altered inputs or a different sample cannot silently pass as the original result. Tests also compare every retained model input to the original research values, check publication cutoffs, preserve calendar gaps, and block network calls during reproduction.

### Output files

| File | Contents |
|---|---|
| `forecasts.csv` | Each forecast, first-release outcome, cutoff, release date and error. |
| `metrics.json` | MAE, RMSE, bias, worst/p90 errors and large-miss counts by period/year. |
| `exclusions.csv` | Every excluded evaluation month and its data-availability reason. |
| `features.json` | Rebuilt model input rows. |
| `fits.json` | Training dates, coefficients, standardization and fallback details. |
| `run.json` | Python/package versions, data hash and reference-check result. |
| `summary.md`, `forecasts.png`, `yearly_errors.png` | Readable summary and charts. |

Choose another output directory with `--output`. Paths passed as arguments are relative to your current directory; bundled inputs are located relative to the code, not a hard-coded machine path. From outside the repository, invoke its entry script by absolute path:

```bash
/path/to/repo/.venv/bin/python /path/to/repo/run.py reproduce --output /path/to/results
```

## Optional: download the raw sources again

**Current limitation:** the full network route could not be completed during publication checks because ALFRED and FRASER returned HTTP 403. The supported saved-data route above was verified from a clean export. The downloader checks access before launching the larger job and reports the failure explicitly.

When those providers allow access from your connection:

```bash
python -m cpi_forecast fetch
python -m cpi_forecast reproduce --observations build/downloaded_observations.json.gz --output build/downloaded_results
```

The downloader reads the versioned source manifest, retrieves ALFRED CSV ZIPs, parses original BLS/New York Fed PDFs, and extracts the national Zillow and Manheim series. No account or API key is used. Raw files go into `build/cache/`; request metadata and hashes are saved alongside them. The published observation file is protected from overwrite.

- Repeat the same command after a transient failure; verified successful downloads are reused.
- `fetch --offline` parses a **complete** existing raw cache. It cannot manufacture missing downloads.
- For a different cache directory use `--cache PATH`; `--output PATH` controls the extracted observation file.
- `build/cache/audit.json` records successful source requests, changed file hashes and failures. Access-check failures are written to `access_check.json`.
- If a file's contents change, its new hash is recorded. The subsequent forecast reference check must still pass; otherwise the original result has not been reproduced.
- Zillow histories may change as later data arrive. To intentionally inspect the new vintage, add `--no-reference-check` to `reproduce` and use a separate output folder. `run.json` records that the check was skipped. Keep those results distinct from the published snapshot.

## Code map

| File | Responsibility |
|---|---|
| `cpi_forecast/features.py` | Timing rules, transformations, component weights and missing data. |
| `cpi_forecast/model.py` | Training selection, regressions, forecasts, metrics and equivalence check. |
| `cpi_forecast/sources.py` | Public downloads, cache checks and raw-source extraction. |
| `cpi_forecast/parsers.py` | BLS PDF, New York Fed PDF and Manheim workbook parsers. |
| `cpi_forecast/report.py` | CSV/JSON/Markdown reports and static charts. |
| `cpi_forecast/__main__.py` | Command-line entry point. |
| `tests/test_reproduction.py` | Numerical, timing, missing-data and source-parser checks. |

## Verification scope

Publication checks use a new Python environment and a clean export containing only Git-indexed files, followed by the documented reproduction command and test suite. Tests require no local raw-data archive. A GitHub Actions workflow is included for Linux, macOS and Windows with Python 3.13; those remote jobs have **not** run until this repository is pushed to GitHub. A successful local macOS run is not proof that every platform has already passed.

### Observed checks — October 3, 2026

- Fresh Git export and fresh Python 3.13.7 environment on macOS; all pinned packages installed without using the original environment.
- All **14 tests passed**.
- Full report generation passed with outbound socket connections and DNS lookups disabled.
- **348/348 forecasts and their first-release outcomes matched** the original reference; the largest forecast difference was `1.11e-16` pp.
- Absolute-path entry point passed from outside the repository, with spaces in the export and output paths.
- Full raw-source retrieval was blocked as described above; it is not counted as a successful verification.

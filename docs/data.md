# Data sources and limitations

The bundled snapshot covers January 2012–August 2026. The published evaluation starts in January 2019. Its numerical extracts were assembled from the research downloads available by October 2, 2026.

| Data | Provider / identifier | Timing treatment |
|---|---|---|
| Core CPI | BLS via [ALFRED CPILFESL](https://alfred.stlouisfed.org/series?seid=CPILFESL) | Month-end predictor vintages; first-release outcome vintages. |
| Rent / owners' equivalent rent | BLS via ALFRED `CUSR0000SEHA`, `CUSR0000SEHC` | Dated component vintages. |
| Used cars / airfares / lodging | BLS via ALFRED `CUSR0000SETA02`, `CUSR0000SETG01`, `CUSR0000SEHB` | Dated component vintages. |
| Medical services | BLS via ALFRED `CUSR0000SAM2` | Dated component vintages. |
| Core producer prices | BLS via ALFRED `PPIFES` | Latest observation available at cutoff, with a maximum observation age of 3 months. |
| Hourly earnings | BLS via ALFRED `AHETPI` | Same cutoff/age rule; used in the earlier medical equation. |
| Retail inventory-to-sales ratio | Census Bureau via ALFRED `RETAILIRSA` | Same cutoff/age rule. |
| Gulf Coast jet fuel | EIA via ALFRED `DJFUELUSGULF` | Daily observations strictly before cutoff; monthly averages need at least 10 observations. |
| Initial unemployment claims | Labor Department via ALFRED `ICSA` | Last 8 available weekly observations before cutoff; latest must be no more than 14 days old. |
| Empire State prices paid | [New York Fed original survey reports](https://www.newyorkfed.org/survey/empire/empiresurvey_archives) | Current and three-month-prior original reports, subject to publication date. |
| New-lease rents | [Zillow Observed Rent Index](https://www.zillow.com/research/data/), national SA series | Annual growth delayed 6/12 months; **revised current history**, not original vintages. |
| Wholesale used-car prices | [Manheim Used Vehicle Value Index](https://site.manheim.com/consulting), August 2026 workbook | Monthly changes delayed 1/2/3 months and a three-month comparison; **revised history**, not original vintages. |
| Annual CPI weights and health-insurance changes | Original BLS CPI releases, archived by [FRASER](https://fraser.stlouisfed.org/title/consumer-price-index-58) | January-known weights; previous month's published health change. |

Exact download URLs, release dates, requested ALFRED vintages and original PDF/file hashes are in [`sources.json`](../data/sources.json). The source calendar is in [`calendar.json`](../data/calendar.json). Those dates are fixed research metadata: a fresh download rebuilds the existing historical study, not a new live forecasting period.

## Files shipped with the project

- `data/observations.json.gz`: compressed numerical source observations, including dated index snapshots, original report extracts, weights, and national rent/used-car series. Standard gzip JSON; no special data service needed.
- `data/model.json`: chosen equations, inputs, penalties and fitting rules.
- `data/calendar.json`: target months, forecast cutoffs and CPI release dates.
- `data/sources.json`: public source locations and retrieval specifications.
- `data/provenance.json`: source metadata from the original ALFRED collection, including original request bodies and hashes where recorded. Archive-relative paths identify research records; reproduction does not read those paths.
- `data/reference_forecasts.json` and `data/reference_outcomes.json`: historical forecast and outcome values used **only to check** freshly fitted results, never as model inputs.
- `data/checksums.json`: SHA-256 integrity checks for the shipped inputs.
- `tests/reference_features.json`: expected feature values from the original research, used only by tests.
- `tests/fixtures/`: two original BLS PDFs needed for parser regression tests; their sources are listed below.

To read the compressed file directly:

```python
import gzip, json
with gzip.open('data/observations.json.gz', 'rt', encoding='utf-8') as f:
    observations = json.load(f)
```

## Known limitations

**Revised private-sector histories.** Lagging Zillow and Manheim makes the economic delay explicit; it does not reverse later historical revisions. The full model is therefore not a strictly real-time vintage backtest.

**Source coverage.** ALFRED vintage coverage starts at different dates for different series. Missing histories stay missing. January and February 2012 health-insurance table extraction was unavailable in the research dataset. The health manifest includes only the 172 successfully extracted releases; it is not a claim of complete early coverage.

**Publication-based reconstruction.** A release date does not establish the exact time an individual could have downloaded a file that day. This is a month-end research cutoff, not an intraday execution simulation.

**Mutable downloads and access controls.** Files may be revised or moved, and source sites may reject automated requests. On October 3, 2026, fresh retrieval succeeded for all 176 New York Fed reports, Zillow and Manheim, but ALFRED and FRASER returned HTTP 403. The bundled-data route is independent of these services. The optional full fresh-download route remains unverified end to end on this connection.

## Attribution and use

BLS, the Federal Reserve Bank of St. Louis/ALFRED/FRASER, the Federal Reserve Bank of New York, EIA, the Census Bureau, the Department of Labor, Zillow and Cox Automotive/Manheim are credited for their source data. This project is unaffiliated with these providers.

The MIT license covers project code and documentation. It does not relicense third-party data or imply provider endorsement. The repository includes numerical extracts for this research; consult each provider's terms before republishing source datasets for a different purpose.

Parser fixtures are U.S. BLS publications:

- [November 17, 2016 CPI release](https://fraser.stlouisfed.org/files/docs/publications/bls/newsreleases/cpi/cpi_20161117.pdf)
- [January 13, 2026 CPI release](https://fraser.stlouisfed.org/files/docs/publications/bls/newsreleases/cpi/cpi_20260113.pdf)

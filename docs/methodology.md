# Methodology

## What is being forecast

The target is the **seasonally adjusted monthly change in core CPI**, which excludes food and energy. It is a percentage change, not an index level, annual inflation or an annualized monthly rate.

For each month, the forecast cutoff is the last calendar day of that month. The outcome is `100 × (current index / previous month's index − 1)`, with both index levels taken from the vintage in which the current month first appeared. This avoids mixing an original current reading with a subsequently revised prior reading.

This is a reconstruction of historical forecasts. Every regression is refitted using earlier months whose outcomes had been published by the forecast cutoff. The code does not use the target month's outcome to predict that same month. Historical predictor rows retain the vintage associated with their own forecast dates.

## Models

The final model has separate equations for rent, owners' equivalent rent, used cars, airfares, lodging, medical services and the remainder of core CPI. Each equation predicts a monthly component change. Their weighted sum is the core forecast.

| Part | Final equation's inputs | Why try them? |
|---|---|---|
| Rent and owners' equivalent rent | Own last month, 3/12-month averages; Zillow annual rent growth delayed 6/12 months | New leases can move before measured housing inflation. |
| Used cars | Own last month and 3-month average; positive/negative wholesale movements; wholesale-versus-retail gap | Wholesale prices may pass through to retail prices with a delay. |
| Airfares and lodging | Own last month and 3/12-month averages; jet fuel changes; unemployment-claims level/change; month-of-year terms | Fuel costs and travel demand may help explain volatile travel prices. |
| Medical services | Own last month and 3/12-month averages; previous published health-insurance change adjusted for scheduled resets | Health-insurance measurement changes can persist between resets. |
| Remainder | Own last month and 3/12-month averages; Empire State prices paid, core producer prices, retail inventories | These proxy broader cost and supply conditions. |

These are plausible forecasting relationships, not evidence of causation. Oil enters indirectly through jet fuel. Gold is not in the final model.

### Fitting

- Standardize each input using the current training sample's mean and standard deviation.
- Fit ridge regression with penalty `alpha = 10`, leaving the intercept unpenalized.
- Require at least 24 released training rows with complete inputs; expand the training period over time.
- Constrain selected slopes to be nonnegative: Zillow in housing; every used-car input; own history and demand inputs in travel; health continuation in medical services. Other slopes are unrestricted.
- If a revised component equation lacks inputs or training history, retain its earlier component forecast and record the fallback. The published final fits needed no such fallbacks.

The earlier model uses the same housing and remainder equations. It has simpler used-car and travel equations, and uses wages plus seasonal terms for medical services. The factory benchmark is a direct ridge regression on core CPI history, current Empire State prices paid and its three-month change. The simple benchmark averages the available monthly core changes in the preceding 12 calendar months.

Exact equations and column lists are in [`data/model.json`](../data/model.json); fitted coefficients, training dates and scaling parameters are produced in `build/results/fits.json`.

### Component weights

Weights come from the prior December CPI report published in January, normalized to core CPI and held fixed for that year. They are used only after that report's release. There are no weights for 2012 in this implementation.

The remainder is defined algebraically so its weighted sum with the six named components equals core CPI. It is an accounting residual, not an independently published BLS series. Fixed annual relative-importance weights approximate CPI aggregation; this is not a replication of the complete BLS index formula.

## Missing months and timing

A monthly change needs both adjacent calendar-month levels. Missing observations are never interpolated, annualized or divided across months. The immediately preceding change is required; the 3/12-month averages need at least 2/10 valid changes inside their actual calendar windows.

All four models share eligible scoring months. June 2024 lacks required jet-fuel inputs. October 2025 has no valid core CPI outcome; November lacks the adjacent prior level; December and January 2026 do not meet the lag requirements. These five exclusions leave 71 earlier and 16 recent months. Exclusions are based on data availability, not error size; the exact reasons are regenerated in `exclusions.csv`.

## Evaluation and interpretation

MAE is the average absolute difference between a forecast and its outcome. RMSE puts more weight on large misses. We also report bias, worst error, the 90th-percentile error and the number of misses above 0.20 pp.

The model improved earlier-period MAE from 0.1102 to 0.1003 pp relative to its immediate predecessor. Recent MAE improved from 0.0967 to 0.0930 pp, but the 12-month average scored 0.0827 pp. The worst earlier error remained about 0.6112 pp: April 2021's actual 0.9166% versus a 0.3054% forecast.

Both periods informed the overall research process. The last automated selection rules used earlier-period scores, including shock and quieter years, but that does not erase earlier inspection of recent results. Repeated comparison of models can overfit historical events. Results should be described as development backtests with explicit data limitations. No claim of beating professional forecasters is made; their targets, dates and information sets may differ.

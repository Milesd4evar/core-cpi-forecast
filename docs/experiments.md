# Selected experiment notes

This is a curated record of the research decisions behind the published model. Earlier explorations used different samples; their scores should not be compared directly with the final same-date table.

| Stage | What was tried | What changed in the project |
|---|---|---|
| Establish benchmarks | Repeat the last CPI change; average the previous 3 or 12 changes | Created a simple standard that complicated models must earn their way past. |
| Add economic information | Ridge regressions with CPI history and factory prices; housing, used cars, wages and unemployment-related measures | Factory information was useful; several similar inputs added little or unstable benefit. |
| Change representations | Levels, changes, delayed values, averages, capped extreme inputs; oil and gold comparisons | How an input is represented mattered. Capping extreme predictors sometimes helped a weak equation and hurt a stronger one. Gold did not earn a place in the final specification. |
| Broaden the search | 541 candidate variants covering more datasets, component models and combinations | Found attractive recent-period results that had poor earlier performance. They were not treated as validated winners. |
| Diagnose component errors | Split core CPI into housing, used cars, travel, medical services and a remainder | Showed which price categories contributed to large misses and made revisions easier to explain. |
| Restrict unstable relationships | Nonnegative rental/wholesale slopes and other robustness variants | Produced the earlier component model used as the final model's reference. |
| Investigate remaining misses | 30 component specifications and 22 combinations across the final rounds | Tested used-car pass-through, sustained travel changes, and health-insurance continuation/reset behavior. |
| Select the published version | Require earlier-period and shock-period improvements; limit damage in quieter years | Combined the used-car, airfare, lodging and medical changes. Housing and remainder equations stayed as before. |

## Lessons

**More data did not automatically improve a forecast.** Closely related series can add complexity without new information. A model can look strong in one stretch and extrapolate badly elsewhere.

**Timing is part of the model.** A series describing January is not necessarily available in January. Original releases and archived snapshots were needed to reconstruct the information cutoff.

**A big miss is useful diagnostic evidence.** The travel equations sometimes predicted a reversal while a collapse or reopening continued. Restrictions on the signs of selected coefficients tested whether reducing that behavior helped across dates.

**A plausible explanation still needs checking.** Rules were applied across every date, not just manually patched into a bad month. Nevertheless, rules proposed after seeing historical failures can fit those failures too closely.

**The recent results do not settle the question.** They cover only 16 eligible months, were previously inspected, and favor a simple average over the final model. A future untouched evaluation would provide stronger evidence.

The publication code refits the chosen specification and benchmarks. It does not rerun the entire exploratory search or automatically select whichever variant scores best. Development used Python and AI-assisted coding; the equations, data handling and limitations are documented so the work can be inspected.

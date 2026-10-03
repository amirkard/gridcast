
### Publication lag
Measured load arrives roughly 2 hours behind real time. At prediction time the
most recent measurement available is therefore ~2 h old. Lag features must
respect this offset; short lags that exist in the training table are not
available in production.

## Week 3 — day-ahead forecasting

Task: at midday, predict all 96 intervals of the following day (12–36 h horizon).

Feature constraint: measurements arrive ~2 h late and the furthest target is 36 h
ahead, so no feature may use data newer than 48 h. All lags and rolling windows
end at 192 slots (2 days) before the target.

Validation: 6 walk-forward folds of 30 days, expanding training window, no shuffling.

Known limitation: row-offset lags are shifted by one slot after each of the three
dropped 2023 rows. Effect is negligible (3 of 131,550); a generated time grid
would remove it.

### Paired comparison across folds (n = 6)

- LightGBM − Ridge: −0.48 pp MAPE, 95% CI [−0.98, +0.03], p = 0.061.
  Suggestive but not significant at this sample size.
- LightGBM − Elia day-ahead: +0.21 pp MAPE, 95% CI [−0.71, +1.14], p = 0.584.
  Not distinguishable at n = 6. The interval is too wide to claim parity with the
  TSO forecast; it reflects low statistical power, not demonstrated equivalence.

Caveat: expanding training windows make folds partly dependent, so the paired
t-test is mildly optimistic. Reported for scale, not as a strict hypothesis test.

### Re-run with higher power (24 folds × 14 days)

| Model          | MAE (MW)       | MAPE (%)     |
|----------------|----------------|--------------|
| Elia day-ahead | 318.9 ± 78.2   | 3.35 ± 0.81  |
| LightGBM       | 357.6 ± 115.7  | 3.75 ± 1.14  |
| Ridge          | 383.1 ± 119.7  | 4.05 ± 1.19  |
| Seasonal naive | 490.9 ± 180.4  | 5.17 ± 1.84  |

- LightGBM − Ridge: −0.30 pp, 95% CI [−0.56, −0.03], p = 0.028. Significant.
- LightGBM − Elia:  +0.40 pp, 95% CI [+0.03, +0.77], p = 0.036. The model is
  measurably worse than the TSO's weather-informed forecast.

This supersedes the 6-fold result, where neither comparison resolved. At n = 6 the
LightGBM–Elia difference appeared indistinguishable; that was insufficient power,
not equivalence. The shorter 14-day windows also raised the reference forecast's
own fold variance from 0.23 to 0.81 pp, so the earlier claim that the gap was
mainly about stability rather than accuracy does not hold. Both models vary more
across short windows; LightGBM is worse on average by ~0.4 pp.

### Weather features
Population-weighted Belgian temperature from the Open-Meteo archive (Brussels 0.30,
Antwerp 0.25, Ghent 0.15, Liege 0.15, Charleroi 0.15). Hourly values joined
step-wise onto the 15-minute grid. Derived: heating degrees (base 16.5 C),
cooling degrees (base 18 C), and 24 h mean temperature for thermal inertia.

Limitation: these are measured temperatures, not day-ahead weather forecasts.
A production system would use a forecast carrying its own error, so any
improvement measured here is an upper bound on the achievable gain.

### With weather features (24 folds × 14 days, identical test rows)

| Model          | MAE (MW)       | MAPE (%)     |
|----------------|----------------|--------------|
| LightGBM       | 308.2 ± 94.9   | 3.22 ± 0.95  |
| Elia day-ahead | 318.9 ± 78.2   | 3.35 ± 0.81  |
| Ridge          | 359.9 ± 108.1  | 3.83 ± 1.13  |
| Seasonal naive | 490.9 ± 180.4  | 5.17 ± 1.84  |

Adding temperature, 24 h mean temperature, heating degrees and cooling degrees
reduced LightGBM MAPE from 3.75 to 3.22 (−0.53 pp). The baseline is unchanged, so
the comparison isolates the feature change.

- LightGBM − Elia:  −0.13 pp, 95% CI [−0.49, +0.23], p = 0.451. Statistically
  indistinguishable. Unlike the n = 6 run, this is an informative null: the
  interval excludes any difference beyond ~0.5 pp in either direction.
- LightGBM − Ridge: −0.61 pp, 95% CI [−0.93, −0.29], p = 0.001.

Conclusion: the previously measured +0.40 pp shortfall against the TSO forecast is
explained by the absence of weather inputs.

Outstanding caveat: measured temperature was used, not forecast temperature. The
reference forecast had to rely on a weather forecast with its own error, so this
comparison favours the model. Re-running with archived day-ahead forecast
temperature would make it fair.

# Verification Methodology

## Data model

### Internal dimensions

All datasets in the library share a common dimensional convention:

| Dimension | Description |
|-----------|-------------|
| `forecast_reference_time` | Date the forecast was issued (parsed from ZIP filename) |
| `drought_region_id` | Integer region ID (1–38) |
| `lead_week` | Integer lead time in weeks (0 = current week, 1–3 = future weeks) |
| `valid_at` | Derived coordinate: Monday of the target forecast week |

`lead_week` is computed as:

```
monday_of_frt = forecast_reference_time - weekday(forecast_reference_time)
lead_week     = round((valid_at - monday_of_frt).days / 7)
```

### Variable categories

| Category | Mode | Available quantities |
|----------|------|---------------------|
| **CDI and index variables** | deterministic (p50 only) | `cdi`, `precip_1m_index`, `precip_3m_index`, `precip_24m_index`, `hydro_index`, `soil_moisture_index` |
| **SPI and precipitation/moisture** | quantile (p10/p50/p90) | `spi_1m/3m/6m/12m/24m`, `precip_sum_*`, `soil_moisture_ufc` |

---

## Reference forecasts

### Climatology reference

For each target `(drought_region_id, week_of_year)`, the historical distribution
of observations is computed using all years available in the archive, restricted
to ISO weeks within ±`week_window` weeks of the target week-of-year.

The target year itself is excluded to avoid data leakage.

Output: p10 / p50 / p90 per variable, on the same `(frt, region, lead_week)` grid
as the forecast.

**Parameter:** `week_window` (default = 4) controls the seasonal smoothing window.

### Persistence reference

The last observed value **strictly before** `forecast_reference_time` is used as
the flat forecast for all lead weeks.  This produces a deterministic reference
stored as `_ref_p50`.

---

## Scoring

### Deterministic metrics (applied to p50 forecast)

| Metric | Formula | Notes |
|--------|---------|-------|
| **MAE** | mean\|f − o\| | Lower is better |
| **RMSE** | √mean(f − o)² | Penalises large errors more than MAE |
| **MSE** | mean(f − o)² | Squared version of RMSE |
| **Bias** | mean(f − o) | Signed; positive = overforecast |
| **Correlation** | Pearson r | Higher is better; range −1 to 1 |
| **MAE Skill Score** | 1 − MAE(fcst)/MAE(ref) | 1 = perfect, 0 = same as reference, <0 = worse |
| **ROC-AUC** | Area under ROC curve | Binary event: CDI ≥ threshold; 0.5 = no skill |

### Quantile / probabilistic metrics (applied to p10/p50/p90)

| Metric | Formula | Notes |
|--------|---------|-------|
| **Pinball loss** | Averaged over q ∈ {0.1, 0.5, 0.9} | Lower is better |
| **Interval score** | width + (2/α)·penalties | Winkler 1990; 80% interval (α=0.2) |
| **RPSS** | 1 − RPS(fcst)/RPS(ref) | Ranked Probability Skill Score |

### Approximate RPS from 3-quantile forecast

Because only p10/p50/p90 are available (not a full ensemble), RPS is approximated
by constructing a piecewise-linear CDF anchored at these three quantiles and
integrating the squared CDF difference over a grid of thresholds:

```
RPS ≈ Σ_t  (F_fcst(t) − F_obs(t))² · Δt
```

where `F_obs(t) = 1[obs ≤ t]` (step function) and `F_fcst(t)` is the
interpolated forecast CDF.

This is a deliberate approximation.  When comparing forecast RPSS against a
reference built from the same 3-quantile structure, the approximation cancels
and relative skill is well-defined.

### Skill score convention

All skill scores follow the convention:

```
SS = 1 − score(forecast) / score(reference)
```

| Value | Interpretation |
|-------|----------------|
| 1.0 | Perfect forecast |
| 0.0 | No improvement over reference |
| < 0 | Worse than reference |

---

## ROC-AUC for CDI

The CDI is an ordinal index (typically 1–5 or similar).  ROC-AUC is computed
for the binary event **CDI ≥ threshold** (default threshold = 2, configurable).

The p50 forecast is used as the rank-ordering variable (higher forecast → higher
predicted probability of the event).

Scores are computed per lead week, pooling over all `forecast_reference_time` ×
`drought_region_id` cells.

---

## Output dataset structure

```
ds_scores dims: (lead_week, drought_region_id)

Variables (one per variable × metric combination):
    cdi_mae              float64  (lead_week, drought_region_id)
    cdi_rmse             float64  (lead_week, drought_region_id)
    spi_1m_mae           float64  (lead_week, drought_region_id)
    spi_1m_rpss          float64  (lead_week, drought_region_id)
    spi_1m_pinball       float64  (lead_week, drought_region_id)
    ...

Global attributes:
    source               drought_forecast_eval
    variables_scored     cdi,spi_1m,spi_6m,...
    scores_computed      mae,rmse,rpss,...
    cdi_threshold        2.0
    reference_type       climatology
```

Results are exported to NetCDF4 for archiving and reproducibility.

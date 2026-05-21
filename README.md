# drought-forecast-eval
[![codecov](https://codecov.io/gh/MeteoSwiss/drought-forecast-eval/branch/main/graph/badge.svg)](https://codecov.io/gh/MeteoSwiss/drought-forecast-eval)
[![Python 3.11 | 3.12 | 3.13](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/downloads/)
[![Tests](https://github.com/MeteoSwiss/drought-forecast-eval/actions/workflows/CI_test.yaml/badge.svg)](https://github.com/MeteoSwiss/drought-forecast-eval/actions)


**Verification and evaluation library for Swiss drought forecasts.**

> ⚠️  This is still a sharp tool, it is not fully tested yet ⚠️

Quantifies the quality of operational drought forecasts issued by the Swiss
drought monitoring system ([drought.admin.ch](https://drought.admin.ch)) across
the 38 official drought warning regions, for all forecast variables (SPI,
precipitation, streamflow, soil moisture, CDI) and all lead times (week 0–3).

---

## Features

- **Data loading** — parse flat archives of daily BGDI ZIP dumps into `xr.Dataset`
- **Observation loading** — read the full historic observation archive
- **Alignment** — merge forecast and observation grids on `(region, valid_at)`
- **Reference forecasts** — climatology (week-of-year ± window) and persistence
- **Scoring** — MAE, RMSE, Bias, Correlation, Pinball loss, Interval score, RPSS, ROC-AUC
- **Extensible registry** — add custom metrics with `register_score()`
- **Visualisation** — skill-vs-lead curves, 4-panel regional maps, experiment diffs
- **Report generation** — HTML report with embedded plots, CSV/NetCDF export
- **Experiment comparison** — compare two time periods or data sources side-by-side

---

## Quick start

```bash
poetry install --with dev,report,notebook
```

```python
from drought_forecast_eval import (
    load_forecasts, load_observations,
    align_obs_to_forecast, climatology_reference,
    compute_scores, ReportBuilder,
)

# Load data
ds_fcst = load_forecasts("/data/zips", date_range=("2025-01-01", "2025-12-31"))
ds_obs  = load_observations("/data/historic.zip")

# Align and score
ds      = align_obs_to_forecast(ds_fcst, ds_obs)
ds_ref  = climatology_reference(ds_obs, ds_fcst)
scores  = compute_scores(ds, variables="all", scores="default", ds_ref=ds_ref)
scores.to_netcdf("scores.nc")

# Or run the full pipeline at once
builder = ReportBuilder(
    archive_dir="/data/zips",
    historic_path="/data/historic.zip",
    date_range=("2025-01-01", "2025-12-31"),
    output_dir="./output",
)
builder.run()   # → output/scores.nc, output/report.html, output/scores_summary.csv
```

---

## CLI

After installation the `drought-eval` command is available via the Poetry
environment.

```bash
# Run with all defaults — uses every ZIP in data/zipfiles/
poetry run drought-eval

# Restrict to a specific date window
poetry run drought-eval --start 2025-07-04 --end 2025-12-31

# Persistence reference, only SPI variables, MAE + RPSS
poetry run drought-eval \
  --reference persistence \
  --variables spi_1m,spi_3m,spi_6m \
  --scores mae,rpss

# Full run including an HTML report (requires: poetry install --with report)
poetry run drought-eval --html

# Custom archive and output directory, with verbose logging
poetry run drought-eval \
  --archive-dir /data/zipfiles \
  --output-dir  /results/2025 \
  --verbose
```

Full option reference:

```
Options:
  --archive-dir  DIRECTORY        Flat directory of daily forecast ZIPs.
                                  [default: data/zipfiles]
  --historic-path FILE            Historic observations ZIP from BGDI.
                                  [default: data/historic/trockenheitsdaten-
                                  numerisch_historic.csv.zip]
  --output-dir   DIRECTORY        Directory for scores .nc and summary .csv.
                                  [default: output]
  --start       YYYY-MM-DD        Start date (inclusive).
  --end         YYYY-MM-DD        End date (inclusive).
  --reference   [climatology|persistence|both]
                                  Reference forecast strategy.
                                  [default: climatology]
  --variables   TEXT              'all', a group (cdi/spi/precip), or
                                  comma-separated variable keys.
  --scores      TEXT              'default' or comma-separated metric names.
  --html                          Render an HTML report to OUTPUT_DIR/report.html
                                  (requires poetry install --with report).
  -v, --verbose                   Enable DEBUG logging.
  --help                          Show this message and exit.
```

---

## Installation

| Use case | Command |
|----------|---------|
| Core library | `poetry install` |
| + HTML reports | `poetry install --with report` |
| + Jupyter notebook | `poetry install --with notebook` |
| Everything | `poetry install --with dev,report,notebook` |

Python ≥ 3.11 required.

---

## Project layout

```
drought_forecast_eval/
├── io/            # archive scanning, ZIP loading, schema validation, downloader
├── processing/    # lead-time computation, obs/fcst alignment, reference forecasts
├── scoring/       # variable map, score registry, dispatcher, skill functions
├── visualization/ # skill curves, regional maps, experiment comparisons
├── report/        # ReportBuilder + Jinja2 HTML template
└── config/        # defaults and constants
notebooks/         # template_verification.ipynb
tests/             # pytest suite with synthetic fixtures
docs/              # data_access.md, methodology.md, reproducibility.md
```

---

## Variables and scoring modes

| Variable group | Mode | Metrics |
|----------------|------|---------|
| CDI, hydro/soil/precip indices | Deterministic | MAE, RMSE, Bias, Correlation, MAE-Skill, ROC-AUC |
| SPI-1/3/6/12/24, precip sums, soil_moisture_ufc | Quantile (p10/p50/p90) | + Pinball loss, Interval score, RPSS |

---

## Documentation

- [Data access](docs/data_access.md) — BGDI URLs, download scripts, CSV column reference
- [Methodology](docs/methodology.md) — scoring formulas, RPS approximation, skill score convention
- [Reproducibility](docs/reproducibility.md) — environment setup, pinning, error handling, custom experiments

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see LICENSE.

## Citation

If you use this library in a publication, please cite the `scores` library it depends on:

> Leeuwenburg et al. (2024). scores: A Python package for verifying and evaluating models
> and predictions with xarray. *Journal of Open Source Software, 9*(99), 6889.
> https://doi.org/10.21105/joss.06889

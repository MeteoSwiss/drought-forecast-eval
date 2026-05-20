# Reproducibility & Error Handling

## Environment setup

### Recommended setup (Poetry)

```bash
git clone https://service.meteoswiss.ch/git/climateanalysis/collab/drought-forecast-eval
cd drought-forecast-eval
poetry install --with dev,report
```

### Verify installation

```bash
poetry run python -c "import drought_forecast_eval; print(drought_forecast_eval.__version__)"
poetry run pytest
```

---

## Pinning dependencies

To fully reproduce a verification run, export the resolved lockfile:

```bash
poetry export --without-hashes --with dev,report -o requirements-lock.txt
```

Include `poetry.lock` (already committed to the repo) and `requirements-lock.txt`
alongside the output NetCDF file so that re-runs use identical versions.

Key dependencies and their roles:

| Library | Role |
|---------|------|
| `xarray` | Core n-dimensional data model |
| `pandas` | CSV parsing and date handling |
| `numpy` | Numerical operations |
| `scores` | Verified meteorological scoring functions |
| `geopandas` | Shapefile loading for regional maps |
| `matplotlib` | All plotting |
| `scipy` | Percentile calculations in reference forecasts |
| `sklearn` (scikit-learn) | ROC-AUC computation |
| `jinja2` | HTML report templating |
| `netCDF4` | NetCDF4 file I/O |

---

## Reproducibility checklist

Before archiving a verification run, ensure:

- [ ] **Data checksums:** Record `md5sum` or `sha256sum` of the input ZIP files.
- [ ] **Date range:** The exact `date_range` is stored in `ds_scores.attrs`.
- [ ] **Reference type:** Stored in `ds_scores.attrs["reference_type"]`.
- [ ] **CDI threshold:** Stored in `ds_scores.attrs["cdi_threshold"]`.
- [ ] **Library version:** Stored in `ds_scores.attrs` (set by dispatcher).
- [ ] **Requirements lock:** `requirements-lock.txt` alongside the output NC file.

Example:

```python
import xarray as xr
ds = xr.open_dataset("scores_20250101_20251231.nc")
print(ds.attrs)
# {'source': 'drought_forecast_eval', 'variables_scored': '...', ...}
```

---

## Error handling

### Common errors and resolutions

| Error | Cause | Resolution |
|-------|-------|------------|
| `FileNotFoundError` | Archive dir or historic ZIP path incorrect | Check path; run `download_archive()` / `download_historic()` |
| `RuntimeError: No valid ZIP files found` | Date range outside available archive | Widen `date_range` or check flat dir contents with `scan_archive()` |
| `SchemaError: Missing required columns` | CSV format has changed | Check the actual column list with `pd.read_csv()`, update `FORECAST_SCHEMA` in `schema.py` |
| `UserWarning: Unexpected columns` | New columns added to CSV | Non-fatal: new columns are retained but not validated. Consider updating `FORECAST_SCHEMA`. |
| `ValueError: No scores could be computed` | Observation or forecast columns absent from merged dataset | Check `align_obs_to_forecast()` coverage logs |
| `ImportError: jinja2 ...` | HTML export requested without jinja2 installed | `poetry install --with report` |

### Logging

The library uses Python's standard `logging` module.  To see INFO-level
pipeline messages:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

For debugging data coverage issues:

```python
logging.basicConfig(level=logging.DEBUG)
```

---

## Integrity checks

### Data coverage check

After `align_obs_to_forecast()`, coverage per variable is logged at INFO level.
Variables with < 80% non-NaN cells trigger a WARNING.

To inspect programmatically:

```python
import numpy as np
obs_vars = [v for v in ds_merged.data_vars if v.endswith("_obs")]
for v in obs_vars:
    pct = 100 * np.isfinite(ds_merged[v].values).mean()
    print(f"{v}: {pct:.1f}% coverage")
```

### Schema cross-validation

The loader cross-validates the `# letzte Aktualisierung` header date in each
CSV against the date parsed from the ZIP filename.  A mismatch triggers a
WARNING but does not abort loading (filename date takes precedence).

### Duplicate ZIP handling

If two ZIP files in the archive share the same `YYYYMMDD` date (re-runs),
`scan_archive()` retains only the lexicographically latest one (highest `HHII`
suffix), ensuring deterministic behaviour.

---

## Custom experiments

To substitute specific inputs (e.g., a modified forecast file for a sensitivity
experiment):

```python
from drought_forecast_eval.io.loader import load_forecasts, load_observations
from drought_forecast_eval.scoring.dispatcher import compute_scores
from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

# Load standard observations
ds_obs = load_observations("path/to/historic.zip")

# Load modified forecast from a separate directory
ds_fcst_exp = load_forecasts("path/to/experiment_zips", date_range=("2025-01-01","2025-12-31"))

# Run scoring with a custom variable map (subset or modified entries)
custom_map = {k: v for k, v in VARIABLE_MAP.items() if k in ["spi_1m", "cdi"]}

ds_scores_exp = compute_scores(
    align_obs_to_forecast(ds_fcst_exp, ds_obs),
    variable_map=custom_map,
    scores=["mae", "rpss"],
    ds_ref=climatology_reference(ds_obs, ds_fcst_exp),
)
```

# Drought forecast skill report

Builds an interactive HTML report on the skill of the weekly drought forecasts
(lead weeks 0–3, 38 BAFU drought regions, Monday issues only). It has three parts:

1. **Drought levels.** The CDI and its sub-indices, with the p50 scored as
   levels 1–5. Scores: Gerrity, Heidke and Peirce skill scores, POD, FAR,
   frequency bias, ETS and SEDI for "level ≥ k", and onset detection.
2. **Numerical variables.** Precipitation sums, SPI and soil moisture, using
   the full p10/p50/p90 forecast. Scores: MAE skill, quantile skill score,
   calibration of p10–p90, and Brier skill and ROC area for dry-decile weeks.
3. **Meteograms.** Per-region forecast plumes, by lead week and for single
   issue dates.

The benchmarks are persistence and the 1991–2020 climatology. Confidence
intervals come from a 4-week moving-block bootstrap over issue weeks.

## View the committed report

The built report in `out/site/` is committed, so you can open it without any
data:

```bash
python3 -m http.server -d reports/skill_report/out/site 8000
# open http://localhost:8000
```

The rest of this page is only needed to rebuild it.

## Inputs

The scripts read the NetCDF files that `notebooks/verification_summer2026.ipynb`
writes to `data/netcdf/` (run it with `RECREATE_NETCDF = True`):

| File | Used by |
|------|---------|
| `merged.nc` | all scripts |
| `persistence_reference.nc` | `categorical_skill.py`, `numeric_skill.py` |
| `climatology_reference.nc` | `numeric_skill.py` |
| `observations_2026-10-23.nc` | `numeric_skill.py` (meteogram history) |
| `shapefiles/BAFU_Grossregionen_v3.shp` | `prep_report_data.py` (region map and names) |

The observation file name has a date in it and is hard-coded in
`numeric_skill.py` (`load()`). Update it when you refresh the data.

## Reproduce

Run these from the repository root, in the project's Poetry environment
(the same one the notebook uses):

```bash
poetry run python reports/skill_report/categorical_skill.py reports/skill_report/out
poetry run python reports/skill_report/numeric_skill.py reports/skill_report/out
poetry run python reports/skill_report/prep_report_data.py reports/skill_report/out
```

The first two take about a minute together. They write:

- `out/categorical_skill.json`: scores for the drought levels
- `out/numeric_skill.json`: scores for the numerical variables
- `out/mg/<variable>.json`: meteogram data, one file per variable

The third step builds the report in `out/site/`, the only output that is
committed (`.gitignore` skips the intermediate files). `index.html` holds the
template with the scores inlined, and the meteogram data is copied to `mg/`.

## View

The page loads the meteogram files with `fetch`, and a browser won't do that
for a file opened from disk. Serve the folder instead:

```bash
python -m http.server -d reports/skill_report/out/site 8000
# open http://localhost:8000
```

`index.html` has no `<html>`/`<head>` wrapper because it is written to be
published as a claude.ai artifact. Browsers render it fine anyway; the leading
`<meta charset="utf-8">` keeps the special characters intact when served locally.

## Settings

These are set at the top of `categorical_skill.py`, and `numeric_skill.py`
imports them:

| Name | Default | Meaning |
|------|---------|---------|
| `PERIODS` | full record, 2026 drought season, Jul 2025 – Apr 2026 | issue-date windows scored separately (the report's period switch) |
| `N_BOOT` | 2000 | bootstrap resamples |
| `BLOCK` | 4 | bootstrap block length in weeks |
| `SEED` | 42 | random seed (`numeric_skill.py` uses `SEED + 1`) |
| `THRESHOLDS` | 2, 3, 4 | levels for the "level ≥ k" event scores |

If you change `PERIODS`, also update `PERIOD_RANGE` and `PERIOD_NOTE` in
`report_template.html`. The written findings in the template quote numbers
from the current data, so check them against the new output after a rerun.

## Files

| File | Purpose |
|------|---------|
| `categorical_skill.py` | Contingency-table scores for the ordinal indices, regional GSS, timeline |
| `numeric_skill.py` | Scores for the quantile variables and the meteogram data files |
| `prep_report_data.py` | Packs the outputs into `report_template.html` and copies the meteogram files |
| `report_template.html` | Report page, with a `__DATA__` placeholder for the inlined scores |

# Data Access

## Overview

All input data originates from the Swiss Federal Office for the Environment (BAFU) via the
BGDI (Federal Geoportal) open-data API.  No authentication is required.

---

## Forecast archive (rolling daily dumps)

Each day at 21:00 CET, a ZIP file containing the current week's forecast CSV is published at:

```
https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/
trockenheitsdaten-numerisch_current/
trockenheitsdaten-numerisch_current.csv.{YYYYMMDD}2100.zip
```

The date block `YYYYMMDD` in the filename encodes the `forecast_reference_time` used by
the library.  The ZIP contains `weekly_forecast_regions.csv` with columns documented in
the [Appendix](#appendix-csv-column-reference).

### Automated download with the library

```python
from drought_forecast_eval.io.downloader import download_archive

download_archive(
    dest_dir="/data/drought_zips",
    start="2025-01-01",
    end="2025-12-31",
)
```

### Manual wget (cron-compatible)

```bash
DATE=$(date +%Y%m%d)
URL="https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/\
trockenheitsdaten-numerisch_current/\
trockenheitsdaten-numerisch_current.csv.${DATE}2100.zip"
wget -q -P /data/drought_zips "$URL"
```

A typical cron entry to run at 21:30 every day:

```
30 21 * * * wget -q -P /data/drought_zips \
  "https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/\
trockenheitsdaten-numerisch_current/\
trockenheitsdaten-numerisch_current.csv.$(date +\%Y\%m\%d)2100.zip"
```

---

## Historic observation archive

The full time series of weekly observations is provided as a single ZIP:

```
https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/
trockenheitsdaten-numerisch_historic/
trockenheitsdaten-numerisch_historic.csv.zip
```

This file is updated weekly and contains `weekly_historic_regions.csv`.

```python
from drought_forecast_eval.io.downloader import download_historic

download_historic("/data/historic/trockenheitsdaten-numerisch_historic.csv.zip")
```

---

## Regional shapefile

The 38 official drought warning regions (Grossregionen) are defined by BAFU.
The authoritative shapefile is hosted in the MeteoSwiss internal GitLab:

```
https://service.meteoswiss.ch/git/climateanalysis/pycats/droughtmonitor/
-/tree/main/droughtmonitor/regions/BAFU_Grossregionen_v3_reproj
```

Clone that repository and supply the `.shp` path to `plot_region_map()` or
`ReportBuilder(shapefile_path=...)`.  If the shapefile is not provided, the
library falls back to bar charts per region.

---

## Expected folder layout

```
/data/
├── drought_zips/                          # flat directory — daily forecast ZIPs
│   ├── trockenheitsdaten-numerisch_current.csv.202501012100.zip
│   ├── trockenheitsdaten-numerisch_current.csv.202501022100.zip
│   └── ...
└── historic/
    └── trockenheitsdaten-numerisch_historic.csv.zip
```

---

## Appendix: CSV column reference

### `weekly_forecast_regions.csv`

| Column | Type | Description |
|--------|------|-------------|
| `drought_region_id` | int | Region ID (1–38) |
| `valid_at` | date (DD.MM.YYYY) | Monday of the forecast target week |
| `cdi_p50` | float | Combined Drought Indicator (median) |
| `spi_1m_p10/p50/p90` | float | SPI-1 month (10th / 50th / 90th percentile) |
| `spi_3m_p10/p50/p90` | float | SPI-3 months |
| `spi_6m_p10/p50/p90` | float | SPI-6 months |
| `spi_12m_p10/p50/p90` | float | SPI-12 months |
| `spi_24m_p10/p50/p90` | float | SPI-24 months |
| `precip_sum_1m_p10/p50/p90` | float | Precipitation sum 1 month (mm) |
| `precip_sum_3m_p10/p50/p90` | float | Precipitation sum 3 months (mm) |
| `precip_sum_6m_p10/p50/p90` | float | Precipitation sum 6 months (mm) |
| `precip_sum_12m_p10/p50/p90` | float | Precipitation sum 12 months (mm) |
| `precip_sum_24m_p10/p50/p90` | float | Precipitation sum 24 months (mm) |
| `soil_moisture_ufc_p10/p50/p90` | float | Soil moisture (% of usable field capacity) |
| `hydro_index_p50` | float | Streamflow index (median only) |
| `soil_moisture_index_p50` | float | Soil moisture index (median only) |
| `precip_1m_index_p50` | float | 1-month precipitation index (median) |
| `precip_3m_index_p50` | float | 3-month precipitation index (median) |
| `precip_24m_index_p50` | float | 24-month precipitation index (median) |

### `weekly_historic_regions.csv`

| Column | Type | Description |
|--------|------|-------------|
| `drought_region_id` | int | Region ID (1–38) |
| `measured_at` | date | Date of observation (Monday of the ISO week) |
| `cdi` | float | Combined Drought Indicator |
| `spi_1m / spi_3m / spi_6m / spi_12m / spi_24m` | float | SPI values |
| `precip_sum_1m / 3m / 6m / 12m / 24m` | float | Precipitation sums (mm) |
| `soil_moisture_ufc` | float | Soil moisture (% UFC) |
| `hydro_index` | float | Streamflow index |
| `soil_moisture_index` | float | Soil moisture index |
| `precip_1m_index / 3m_index / 24m_index` | float | Precipitation indices |
| `vhi` | float | Vegetation Health Index |

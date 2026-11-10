# Drought platform prototype

A local copy of the look and flow of the national drought platform
(trockenheit.admin.ch), built on the archived forecasts in this repository.
Use it to try out new ideas quickly. It is plain HTML, CSS and JavaScript, with
no build step and no framework.

It adds three things the live platform doesn't have:

- **A fixed issue date.** Pick the forecast reference time on the landing page
  ("Situation bis …"). Every link into the regions keeps that date, so you can
  step through past forecasts and drill down without losing it.
- **Evaporation ("Verdunstung").** A new row on the region page shows
  observations and the p10/p50/p90 forecast in the same style as the other factors.
- **Combined precipitation and evaporation.** A switch merges the two rows into
  one chart, with precipitation bars pointing up, evaporation bars pointing down,
  and the water balance between them.

The page is marked "Prototyp" in the header and footer. It is for internal
development and isn't meant to be published.

## Quick start (no data needed)

The exported JSON snapshot is committed in `site/data/`, so the site runs
straight from a fresh clone:

```bash
git clone <repo-url> drought-forecast-eval
cd drought-forecast-eval
git switch prototypes
python3 -m http.server -d prototypes/drought_platform/site 8000
```

Open <http://localhost:8000>. Any Python 3 works here; you don't need Poetry
for this step. You do need a local web server, because the page loads its data
with `fetch`, which browsers block for `file://` URLs.

Places to start:

- <http://localhost:8000/#/?frt=2026-06-15>: map at the start of the 2026 drought
- <http://localhost:8000/#/regionen/42/aktuelle-lage?frt=2026-06-15>: region page
- <http://localhost:8000/#/regionen/42/aktuelle-lage?frt=2026-06-15&kombi=1>: precipitation and evaporation combined

The snapshot covers the Monday issue dates from 7 Jul 2025 to 28 Sep 2026, with
observations up to 19 Oct 2026. The evaporation in it is synthetic demo data
(see [Evaporation data](#evaporation-data)).

## Rebuild the data

You only need this to refresh the data or to change what gets exported.
First install the project environment:

```bash
poetry install
```

The export reads two NetCDF files from `data/netcdf/`. They are **not in git**
(about 40 MB), so either get them or build them.

### Option A: you have the NetCDF files

Ask the repository owner for `merged.nc` and `observations_<date>.nc`, and put
them in `data/netcdf/`. Then:

```bash
poetry run python prototypes/drought_platform/export_data.py
```

This takes about 15 seconds and rewrites `site/data/`. It picks the newest
`observations_*.nc` file; use `--obs FILE` to choose a different one.

### Option B: build them from the raw ZIP archives

The NetCDF files come from two BGDI archives:

| Input | Where it comes from |
|-------|---------------------|
| `data/historic.csv.zip` | Observations since 1991. Download it with `poetry run python -c "from drought_forecast_eval.io.downloader import download_historic; download_historic('data/historic.csv.zip')"` |
| `data/zipfiles/*.zip` | One file per day with the forecasts, July 2025 onwards (about 110 MB) |

The daily forecast files **can't be downloaded again**. BGDI only serves the
latest file, and older dated files return "Access Denied". The existing
collection was built up by a daily download, so ask the repository owner for a
copy of `data/zipfiles/`. Then:

```bash
poetry run python prototypes/drought_platform/build_netcdf.py \
    --archive data/zipfiles --historic data/historic.csv.zip
poetry run python prototypes/drought_platform/export_data.py
```

`build_netcdf.py` writes the same files that
`notebooks/verification_summer2026.ipynb` produces. The alignment step takes a
few minutes.

## Evaporation data

The archive has no evaporation data. Without further input, the export builds
**synthetic demo data**, and the UI labels it "Demo-Daten":

- Potential evaporation (ETp) follows a seasonal cycle. It is lower in alpine
  regions and higher in dry spells (SPI-1).
- Actual evaporation is ETa = ETp × f(soil moisture). Forecast quantiles come
  from the soil-moisture forecast quantiles.

To use real data, pass a NetCDF file:

```bash
poetry run python prototypes/drought_platform/export_data.py --evap path/to/evap.nc
```

with these variables (units mm/week, same region ids and Monday dates as the rest):

| Variable | Dims |
|----------|------|
| `eta_obs` | `drought_region_id, valid_at` |
| `etp_obs` (optional, draws the potential-evaporation line) | `drought_region_id, valid_at` |
| `eta_p10`, `eta_p50`, `eta_p90` | `forecast_reference_time, drought_region_id, lead_week` |
| `etp_p50` (optional) | `forecast_reference_time, drought_region_id, lead_week` |

The "Demo-Daten" label disappears once real data is loaded.

## Pages and URL parameters

| Route | Content |
|-------|---------|
| `#/?frt=2026-06-15` | Map coloured by CDI. The week switch shows last week's observation or forecast weeks 0–3 (hatched). "Liste anzeigen" shows a table instead. Below are an auto-generated bulletin with level counts and the factor cards. |
| `#/regionen/42/aktuelle-lage?frt=…` | 24 observed weeks plus 4 forecast weeks per factor, with threshold, minimum and p10–p90 whiskers |
| `#/regionen/42/zeitreihe?frt=…` | The same rows from January 2023 up to the issue date |
| `#/regionen/42/jahresvergleich?frt=…` | One line per year by calendar week, with the forecast band for the current year |

| Parameter | Effect |
|-----------|--------|
| `frt=YYYY-MM-DD` | Issue date (a Monday). Defaults to the latest one. |
| `w=0..4` | Map week: 0 = last observed week, 1–4 = forecast weeks 0–3 |
| `view=liste` | List instead of map |
| `kombi=1` | Combined precipitation and evaporation row |
| `unsicher=1` | Mark forecast weeks +2 and +3 as uncertain |
| `f=<row>` | Scroll to a row: `niederschlag`, `bodenfeuchte`, `verdunstung`, `vegetation` |

On the region page, **"Spätere Beobachtungen einblenden"** draws the observations
that came in after the issue date over the forecast weeks. Use it to judge a
past forecast at a glance.

**"Unsicherheit anzeigen"** marks forecast weeks +2 and +3 (the last two
forecast bars) as unreliable. Their bars fade (55 % and 35 % opacity), but the
p10–p90 whiskers keep full strength. A faint tint and an "unsicher" bracket
cover the two weeks, and their tooltips say why. The rule is fixed for now and
comes from the skill report (`reports/skill_report`): for the CDI, the forecast
matches persistence at lead week 2 and does significantly worse at lead week 3.
Change `UNC_FROM` and `FC_OPACITY` in `app.js` to adjust it. The Jahresvergleich
tab doesn't change.

### Combined precipitation and evaporation

The switch **"Niederschlag & Verdunstung kombinieren"** sits on the precipitation
and evaporation rows. It replaces the two rows with one chart: precipitation
bars point up, actual evaporation bars point down, and both use the same mm
scale. Dots show the water balance (precipitation − evaporation), and the
potential-evaporation line runs below. In the Jahresvergleich tab the row shows
the water balance per year instead.

Precipitation in the archive is a 30-day sum, so evaporation is shown as a
30-day sum as well: four weekly sums × 30/28. These are computed in the browser
(`enrich` and `balanceFc` in `app.js`). For the forecast weeks, the weeks before
the issue date are observed and the rest are forecast. The evaporation p10/p90
are summed week by week, which assumes the weeks are perfectly correlated, so
the range comes out on the wide side.

## Differences from the live platform

- Abfluss, Seepegel and Grundwasser are left out because they need station
  data that isn't in the archive.
- Thresholds are the 1991–2020 10th percentile for each calendar week (±1 week),
  and "Minimalwert" is the 1991–2020 minimum. The platform's own definitions may differ.
- The "Niederschlagssumme" row shows the 30-day sum (`precip_sum_1m`).
- The map is a plain SVG without a basemap. The bulletin text is generated from the data.
- There's no natural-hazard warning banner. That slot holds the issue-date control instead.
- German only.

## Files

| File | Purpose |
|------|---------|
| `build_netcdf.py` | Raw BGDI ZIPs → `data/netcdf/merged.nc` and `observations_<date>.nc` |
| `export_data.py` | NetCDF → `site/data/*.json`, plus synthetic evaporation |
| `site/index.html` | Page shell: top bar, masthead, navigation, footer |
| `site/styles.css` | Styles. The colour tokens use the platform's Tailwind names (`secondary-*`, `cdi-*`, `factor-*`) |
| `site/app.js` | Hash router, map and list, region rows and charts |
| `site/data/` | Exported JSON snapshot (committed, about 1.2 MB) |

To add a factor row, add an entry to `ROWS` in `app.js`, export its series in
`export_data.py`, and add a hatch colour token in `styles.css`.

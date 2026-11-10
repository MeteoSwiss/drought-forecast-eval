"""Export JSON data for the drought platform prototype.

Run from the repo root:
    poetry run python prototypes/drought_platform/export_data.py [--obs FILE] [--evap FILE]

Inputs: data/netcdf/merged.nc and the newest data/netcdf/observations_*.nc
(override with --obs). Build them with build_netcdf.py if you don't have them.

Writes prototypes/drought_platform/site/data/:
    overview.json       issue dates, CDI per region (obs + forecast) for the map, and
                        how often drought followed each forecast state (reliability)
    regions.json        region names and SVG outlines
    region/<id>.json    weekly series for one region (obs, thresholds, forecasts)

Evaporation: if --evap is given it must hold
    eta_obs(drought_region_id, valid_at)                         mm/week
    etp_obs(drought_region_id, valid_at)                         mm/week (optional)
    eta_p10/p50/p90(forecast_reference_time, drought_region_id, lead_week)
Without it, a synthetic demo series is derived from soil moisture and SPI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import MultiPolygon

NC = Path("data/netcdf")
SHAPEFILE = "shapefiles/BAFU_Grossregionen_v3.shp"
OUT = Path(__file__).parent / "site" / "data"

HISTORY_START = "2023-01-02"  # first week kept for the time-series tab
CLIM_PERIOD = ("1991-01-01", "2020-12-31")
WEEK_WINDOW = 1  # ± ISO weeks pooled for thresholds
QUANTILE_VARS = ["precip_sum_1m", "soil_moisture_ufc"]
OBS_VARS = ["cdi", "precip_sum_1m", "soil_moisture_ufc", "vhi"]
DECIMALS = {"precip_sum_1m": 1, "soil_moisture_ufc": 1, "vhi": 1, "eta": 1, "etp": 1}

# Regions above ~1200 m mean elevation get a lower potential evaporation in the demo data
ALPINE = {35, 41, 45, 46, 48, 49, 50, 52, 58, 59, 60, 61, 63, 66, 67, 68}


# ---------------------------------------------------------------------------
# Synthetic evaporation (demo only)
# ---------------------------------------------------------------------------


def etp_week(dates: pd.DatetimeIndex, rid: int, spi_1m: np.ndarray) -> np.ndarray:
    """Potential evapotranspiration, mm/week: seasonal cycle, scaled up in dry spells."""
    doy = dates.dayofyear.values
    season = ((1 - np.cos(2 * np.pi * (doy - 20) / 365)) / 2) ** 1.4
    daily = 0.35 + 3.8 * season
    alt = 0.78 if rid in ALPINE else 1.0
    sunny = 1 - 0.06 * np.clip(np.nan_to_num(spi_1m), -3, 3)
    return 7 * daily * alt * sunny


def stress(sm: np.ndarray) -> np.ndarray:
    """Fraction of potential evaporation realised at a given soil moisture (% uFC)."""
    return np.clip((sm - 15) / 45, 0.12, 1.0)


def synthetic_evap(obs: xr.Dataset, fc: xr.Dataset) -> tuple[xr.Dataset, xr.Dataset]:
    """Demo evaporation: observed ETa/ETp per week and ETa forecast quantiles."""
    dates = pd.to_datetime(obs.valid_at.values)
    eta = np.full((obs.sizes["drought_region_id"], len(dates)), np.nan)
    etp = np.full_like(eta, np.nan)
    for i, rid in enumerate(obs.drought_region_id.values):
        spi = obs["spi_1m"].sel(drought_region_id=rid).values
        sm = obs["soil_moisture_ufc"].sel(drought_region_id=rid).values
        etp[i] = etp_week(dates, int(rid), spi)
        eta[i] = etp[i] * stress(sm)
    coords = {"drought_region_id": obs.drought_region_id.values, "valid_at": obs.valid_at.values}
    ev_obs = xr.Dataset(
        {
            "eta_obs": (("drought_region_id", "valid_at"), eta),
            "etp_obs": (("drought_region_id", "valid_at"), etp),
        },
        coords=coords,
    )

    z = {"p10": -1.2816, "p50": 0.0, "p90": 1.2816}
    out = {f"eta_{q}": np.full(fc["soil_moisture_ufc_p50"].shape, np.nan) for q in z}
    out["etp_p50"] = np.full(fc["soil_moisture_ufc_p50"].shape, np.nan)
    va = fc["valid_at"].transpose("forecast_reference_time", "drought_region_id", "lead_week")
    for ri, rid in enumerate(fc.drought_region_id.values):
        for lw in range(fc.sizes["lead_week"]):
            d = pd.to_datetime(va.values[:, ri, lw])
            sel = dict(drought_region_id=rid, lead_week=lw)
            etp_f = etp_week(d, int(rid), fc["spi_1m_p50"].sel(sel).values)
            out["etp_p50"][:, ri, lw] = etp_f
            for q, zq in z.items():
                sm_q = fc[f"soil_moisture_ufc_{q}"].sel(sel).values
                eta_q = etp_f * stress(sm_q) * (1 + zq * 0.05 * (lw + 1))
                out[f"eta_{q}"][:, ri, lw] = np.minimum(eta_q, etp_f)
    dims = ("forecast_reference_time", "drought_region_id", "lead_week")
    ev_fc = xr.Dataset(
        {k: (dims, v) for k, v in out.items()},
        coords={d: fc[d].values for d in dims},
    )
    return ev_obs, ev_fc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def rnd(a: np.ndarray | list, d: int = 1) -> list[float | int | None]:
    """Round for JSON, with NaN as None."""
    a = np.round(np.asarray(a, dtype=float), d)
    return [None if not np.isfinite(x) else (int(x) if d == 0 else float(x)) for x in a]


def week_thresholds(series: pd.Series) -> dict[str, list]:
    """p10 and minimum per ISO week over the climate period, pooling ±WEEK_WINDOW weeks."""
    s = series.loc[slice(*CLIM_PERIOD)].dropna()
    if s.empty:
        return {"p10": [None] * 53, "min": [None] * 53}
    woy = s.index.isocalendar().week.values.astype(int)
    p10, mn = [], []
    for w in range(1, 54):
        dist = np.minimum(np.abs(woy - w), 53 - np.abs(woy - w))
        v = s.values[dist <= WEEK_WINDOW]
        p10.append(float(np.percentile(v, 10)) if v.size >= 5 else None)
        mn.append(float(v.min()) if v.size >= 5 else None)
    return {"p10": p10, "min": mn}


def drought_hit_rates(fc: xr.Dataset, obs: xr.Dataset, thr: dict) -> dict:
    """How often drought followed each forecast state, per variable and lead week.

    Drought means the observation is below the chart threshold (p10 for the
    calendar week), or CDI level 3 and higher. Forecast states:
    dry (p50 below), possible (p50 above, p10 below), no (p10 above too).
    The CDI has only a median, so it has no "possible" state.
    Pooled over all regions and Monday issue dates with an observation.
    """
    frts = pd.to_datetime(fc.forecast_reference_time.values)
    regions = [int(r) for r in fc.drought_region_id.values]
    out = {}
    for var in ["cdi", *QUANTILE_VARS]:
        leads = []
        for lw in range(4):
            valid = frts + pd.Timedelta(days=7 * lw)
            woy = valid.isocalendar().week.values.astype(int)
            k = {s: [0, 0] for s in ("dry", "possible", "no")}  # [drought weeks, all weeks]
            for rid in regions:
                o = obs[var].sel(drought_region_id=rid).to_series().reindex(valid).values
                f = fc.sel(drought_region_id=rid).isel(lead_week=lw)
                if var == "cdi":
                    f50 = f["cdi_p50"].values
                    ok = np.isfinite(o) & np.isfinite(f50)
                    event = o >= 3
                    state = np.where(f50 >= 3, "dry", "no")
                else:
                    t = np.array([np.nan if x is None else x for x in thr[var][rid]])[woy - 1]
                    f10, f50 = f[f"{var}_p10"].values, f[f"{var}_p50"].values
                    ok = np.isfinite(o) & np.isfinite(f10) & np.isfinite(f50) & np.isfinite(t)
                    event = o < t
                    state = np.where(f50 < t, "dry", np.where(f10 < t, "possible", "no"))
                for st in k:
                    m = ok & (state == st)
                    k[st][0] += int(event[m].sum())
                    k[st][1] += int(m.sum())
            n_all = sum(v[1] for v in k.values())
            e = {st: {"n": n, "rate": round(d / n, 3)} for st, (d, n) in k.items() if n}
            e["base"] = round(sum(v[0] for v in k.values()) / n_all, 3) if n_all else None
            leads.append(e)
        out[var] = leads
    return {"period": [frts[0].strftime("%Y-%m-%d"), frts[-1].strftime("%Y-%m-%d")], "vars": out}


def region_paths() -> dict:
    """Region names and simplified outlines as SVG paths (equirectangular at 46.8°N)."""
    g = gpd.read_file(SHAPEFILE)
    g["geometry"] = g.geometry.simplify(0.0025, preserve_topology=True)
    lat0 = np.deg2rad(46.8)
    minx, miny, maxx, maxy = g.total_bounds
    w = 1000.0
    sx = w / ((maxx - minx) * np.cos(lat0))

    def ring(coords: list[tuple[float, float]]) -> str:
        pts = [f"{(x - minx) * np.cos(lat0) * sx:.1f},{(maxy - y) * sx:.1f}" for x, y in coords]
        return "M" + "L".join(pts) + "Z"

    regions = []
    for _, row in g.sort_values("REGION_NR").iterrows():
        polys = row.geometry.geoms if isinstance(row.geometry, MultiPolygon) else [row.geometry]
        c = row.geometry.representative_point()
        regions.append(
            {
                "id": int(row.REGION_NR),
                "name": row.Name,
                "d": "".join(ring(p.exterior.coords) for p in polys),
                "cx": round((c.x - minx) * np.cos(lat0) * sx, 1),
                "cy": round((maxy - c.y) * sx, 1),
            }
        )
    return {"w": w, "h": round(float((maxy - miny) * sx), 1), "regions": regions}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Write overview.json, regions.json and one JSON per region."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--obs",
        type=Path,
        help="observation NetCDF (default: newest data/netcdf/observations_*.nc)",
    )
    ap.add_argument("--evap", type=Path, help="NetCDF with real evaporation (see module doc)")
    args = ap.parse_args()

    obs_file = args.obs or max(NC.glob("observations_*.nc"), default=None)
    if obs_file is None or not (NC / "merged.nc").exists():
        raise SystemExit(
            f"Missing inputs in {NC}/: need merged.nc and observations_*.nc (see README)."
        )
    print(f"reading {NC / 'merged.nc'} and {obs_file}")
    obs = xr.open_dataset(obs_file)
    ds = xr.open_dataset(NC / "merged.nc")
    fc = ds.isel(forecast_reference_time=(ds.forecast_reference_time.dt.weekday == 0).values)

    if args.evap:
        ev = xr.open_dataset(args.evap)
        ev_obs = ev[[v for v in ("eta_obs", "etp_obs") if v in ev]]
        ev_fc = ev[[f"eta_{q}" for q in ("p10", "p50", "p90")]]
        evap_source = f"file:{args.evap.name}"
    else:
        ev_obs, ev_fc = synthetic_evap(obs, fc)
        evap_source = "synthetic"

    frts = pd.to_datetime(fc.forecast_reference_time.values)
    regions = [int(r) for r in fc.drought_region_id.values]
    hist_dates = pd.to_datetime(obs.valid_at.sel(valid_at=slice(HISTORY_START, None)).values)

    (OUT / "region").mkdir(parents=True, exist_ok=True)

    # --- overview: CDI per issue date for the map ---
    obs_cdi = obs["cdi"].to_pandas()  # region x valid_at
    overview = {
        "frts": [d.strftime("%Y-%m-%d") for d in frts],
        "evap_source": evap_source,
        "cdi": {},
    }
    for i, f in enumerate(frts):
        last = f - pd.Timedelta(days=7)
        row = {}
        for rid in regions:
            o = obs_cdi.loc[rid].get(last, np.nan)
            p = fc["cdi_p50"].isel(forecast_reference_time=i).sel(drought_region_id=rid).values
            row[str(rid)] = rnd(np.concatenate([[o], p]), 0)  # [obs last week, lead 0..3]
        overview["cdi"][f.strftime("%Y-%m-%d")] = row
    thr = {
        v: {rid: week_thresholds(obs[v].sel(drought_region_id=rid).to_series())["p10"] for rid in regions}
        for v in QUANTILE_VARS
    }
    overview["reliability"] = drought_hit_rates(fc, obs, thr)
    (OUT / "overview.json").write_text(json.dumps(overview, separators=(",", ":")))

    (OUT / "regions.json").write_text(
        json.dumps(region_paths(), separators=(",", ":"), ensure_ascii=False)
    )

    # --- one file per region ---
    for rid in regions:
        o = obs.sel(drought_region_id=rid)
        eo = ev_obs.sel(drought_region_id=rid)
        series = {v: o[v].to_series() for v in OBS_VARS}
        series["eta"] = eo["eta_obs"].to_series()
        if "etp_obs" in eo:
            series["etp"] = eo["etp_obs"].to_series()

        rec = {
            "id": rid,
            "dates": [d.strftime("%Y-%m-%d") for d in hist_dates],
            "obs": {
                v: rnd(s.reindex(hist_dates).values, DECIMALS.get(v, 0)) for v, s in series.items()
            },
            "thr": {
                v: {k: rnd(x, DECIMALS[v]) for k, x in week_thresholds(series[v]).items()}
                for v in ("precip_sum_1m", "soil_moisture_ufc", "vhi", "eta")
            },
            "fc": {},
        }
        f_r = fc.sel(drought_region_id=rid)
        e_r = ev_fc.sel(drought_region_id=rid)
        for i, f in enumerate(frts):
            sel = dict(forecast_reference_time=f)
            e = {"cdi": rnd(f_r["cdi_p50"].sel(sel).values, 0)}
            for v in QUANTILE_VARS:
                e[v] = [
                    rnd(f_r[f"{v}_{q}"].sel(sel).values, DECIMALS[v]) for q in ("p10", "p50", "p90")
                ]
            e["eta"] = [rnd(e_r[f"eta_{q}"].sel(sel).values, 1) for q in ("p10", "p50", "p90")]
            if "etp_p50" in e_r:
                e["etp"] = rnd(e_r["etp_p50"].sel(sel).values, 1)
            rec["fc"][f.strftime("%Y-%m-%d")] = e
        (OUT / "region" / f"{rid}.json").write_text(json.dumps(rec, separators=(",", ":")))

    size = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    print(
        f"wrote {len(regions)} regions, {len(frts)} issue dates, "
        f"{size / 1e6:.1f} MB, evap={evap_source}"
    )


if __name__ == "__main__":
    main()

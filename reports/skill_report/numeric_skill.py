"""Verification of the numerical (quantile) variables, plus meteogram data shards.

Run from the repo root:
    poetry run python <this file> <out_dir>

Writes <out_dir>/numeric_skill.json and <out_dir>/mg/<var>.json.
Same sample and bootstrap as categorical_skill.py: Monday issues, pooled over
regions per lead week, 4-week moving-block bootstrap over issue weeks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from categorical_skill import BLOCK, N_BOOT, PERIODS, SEED, block_indices, ci, _clean

NC = "data/netcdf"
NUMERIC = [
    "precip_sum_1m",
    "precip_sum_3m",
    "precip_sum_6m",
    "precip_sum_12m",
    "precip_sum_24m",
    "spi_1m",
    "spi_3m",
    "spi_6m",
    "spi_12m",
    "spi_24m",
    "soil_moisture_ufc",
]
INDICES = [
    "cdi",
    "precip_1m_index",
    "precip_3m_index",
    "precip_24m_index",
    "hydro_index",
    "soil_moisture_index",
]
QUANTILES = (0.1, 0.5, 0.9)
# Decimals kept in the meteogram shards
DECIMALS = {"precip_sum_1m": 1, "soil_moisture_ufc": 1} | {f"spi_{a}": 2 for a in ("1m", "3m", "6m", "12m", "24m")}


def load():
    ds = xr.open_dataset(f"{NC}/merged.nc")
    ds = ds.isel(forecast_reference_time=(ds.forecast_reference_time.dt.weekday == 0).values)
    frt = ds.forecast_reference_time
    pers = xr.open_dataset(f"{NC}/persistence_reference.nc").sel(forecast_reference_time=frt)
    clim = xr.open_dataset(f"{NC}/climatology_reference.nc").sel(forecast_reference_time=frt)
    obs = xr.open_dataset(f"{NC}/observations_2026-10-23.nc")
    return ds, pers, clim, obs


def cdf_from_quantiles(x, q10, q50, q90):
    """Piecewise-linear CDF through (q10, .1), (q50, .5), (q90, .9), extrapolated linearly."""
    lo = 0.4 / np.maximum(q50 - q10, 1e-9)
    hi = 0.4 / np.maximum(q90 - q50, 1e-9)
    f = np.where(x <= q50, 0.5 - (q50 - x) * lo, 0.5 + (x - q50) * hi)
    return np.clip(f, 0.0, 1.0)


def pinball(o, q, tau):
    d = o - q
    return np.maximum(tau * d, (tau - 1) * d)


def weekly_sums(o, f10, f50, f90, c10, c50, c90, p):
    """Per-issue-week sums (t, n_stats) so that bootstrap resamples are just row sums."""
    ok = np.isfinite(o) & np.isfinite(f50) & np.isfinite(c50) & np.isfinite(p)
    z = lambda a: np.where(ok, a, 0.0)  # noqa: E731
    qs_f = np.mean([pinball(o, q, t) for q, t in zip((f10, f50, f90), QUANTILES)], axis=0)
    qs_c = np.mean([pinball(o, q, t) for q, t in zip((c10, c50, c90), QUANTILES)], axis=0)
    event = (o < c10).astype(float)
    prob_f = cdf_from_quantiles(c10, f10, f50, f90)
    cols = {
        "n": ok.astype(float),
        "ae_f": np.abs(f50 - o),
        "ae_p": np.abs(p - o),
        "ae_c": np.abs(c50 - o),
        "err_f": f50 - o,
        "err_p": p - o,
        "obs": o,
        "qs_f": qs_f,
        "qs_c": qs_c,
        "bs_f": (prob_f - event) ** 2,
        "bs_c": (0.1 - event) ** 2,
        "event": event,
        "b0_f": (o < f10).astype(float),
        "b1_f": ((o >= f10) & (o < f50)).astype(float),
        "b2_f": ((o >= f50) & (o <= f90)).astype(float),
        "b3_f": (o > f90).astype(float),
        "b0_c": (o < c10).astype(float),
        "b1_c": ((o >= c10) & (o < c50)).astype(float),
        "b2_c": ((o >= c50) & (o <= c90)).astype(float),
        "b3_c": (o > c90).astype(float),
        "w_f": f90 - f10,
        "w_c": c90 - c10,
    }
    names = list(cols)
    arr = np.stack([np.nansum(z(cols[k]), axis=1) for k in names], axis=1)
    return names, arr, (prob_f[ok], event[ok])


def stats(names, s) -> dict:
    g = dict(zip(names, s))
    n = g["n"]
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "n": n,
            "mae_f": g["ae_f"] / n,
            "mae_p": g["ae_p"] / n,
            "mae_c": g["ae_c"] / n,
            "maess_p": 1 - g["ae_f"] / g["ae_p"],
            "maess_c": 1 - g["ae_f"] / g["ae_c"],
            "qss_c": 1 - g["qs_f"] / g["qs_c"],
            "bss": 1 - g["bs_f"] / g["bs_c"],
            "event_rate": g["event"] / n,
            "bias": g["err_f"] / n,
            "bias_p": g["err_p"] / n,
            "rbias": g["err_f"] / g["obs"],
            "bins_f": [g[f"b{i}_f"] / n for i in range(4)],
            "bins_c": [g[f"b{i}_c"] / n for i in range(4)],
            "cov80_f": (g["b1_f"] + g["b2_f"]) / n,
            "cov80_c": (g["b1_c"] + g["b2_c"]) / n,
            "width_ratio": g["w_f"] / g["w_c"],
        }


def arrays(dss, ps, cs, var, lw):
    sel = dict(lead_week=lw)
    get = lambda d, k: d[k].sel(sel).transpose("forecast_reference_time", ...).values  # noqa: E731
    return (
        get(dss, f"{var}_obs"),
        get(dss, f"{var}_p10"),
        get(dss, f"{var}_p50"),
        get(dss, f"{var}_p90"),
        get(cs, f"{var}_ref_p10"),
        get(cs, f"{var}_ref_p50"),
        get(cs, f"{var}_ref_p90"),
        get(ps, f"{var}_ref_p50"),
    )


def evaluate(ds, pers, clim, start, end, rng) -> dict:
    sl = slice(start, end)
    dss, ps, cs = (x.sel(forecast_reference_time=sl) for x in (ds, pers, clim))
    n_t = dss.sizes["forecast_reference_time"]
    boots = [block_indices(n_t, rng) for _ in range(N_BOOT)]
    out: dict = {"n_weeks": n_t, "vars": {}}
    for var in NUMERIC:
        leads = []
        for lw in range(4):
            names, arr, (prob, ev) = weekly_sums(*arrays(dss, ps, cs, var, lw))
            e = stats(names, arr.sum(0))
            e["auc"] = float(roc_auc_score(ev, prob)) if 0 < ev.sum() < ev.size else None
            bs = {k: [] for k in ("maess_p", "maess_c", "qss_c", "bss")}
            for b in boots:
                sb = stats(names, arr[b].sum(0))
                for k in bs:
                    bs[k].append(sb[k])
            e["ci90"] = {k: ci(v) for k, v in bs.items()}
            leads.append(e)
        out["vars"][var] = leads
        print(f"  {var} done", flush=True)
    return out


def rnd(a, d):
    a = np.round(np.asarray(a, dtype=float), d)
    return [None if not np.isfinite(x) else (int(x) if d == 0 else float(x)) for x in a]


def meteogram_shards(ds, clim, obs, out_dir: Path) -> None:
    """One JSON per variable: obs and climatology on valid dates, forecasts on issue dates."""
    frt = pd.to_datetime(ds.forecast_reference_time.values)
    start = frt[0] - pd.Timedelta(days=7 * 9)
    end = pd.to_datetime(ds.valid_at.values.max())
    dates = pd.date_range(start, end, freq="7D")
    obs_w = obs.sel(valid_at=dates)
    regions = [int(r) for r in ds.drought_region_id.values]

    # Climatology depends on (region, valid week) only: take it from the reference grid by valid date
    va = pd.to_datetime(ds.valid_at.isel(drought_region_id=0).values.ravel())
    out_dir.mkdir(parents=True, exist_ok=True)
    for var in NUMERIC + INDICES:
        d = DECIMALS.get(var, 0)
        shard = {"dates": [x.strftime("%Y-%m-%d") for x in dates], "frt": [x.strftime("%Y-%m-%d") for x in frt], "r": {}}
        for rid in regions:
            e = {"obs": rnd(obs_w[var].sel(drought_region_id=rid).values, d)}
            if var in NUMERIC:
                cl = {}
                for q in ("p10", "p50", "p90"):
                    vals = clim[f"{var}_ref_{q}"].sel(drought_region_id=rid).values.ravel()
                    s = pd.Series(vals, index=va).groupby(level=0).first()
                    cl[q] = rnd(s.reindex(dates).values, d)
                e["clim"] = cl
                e["f"] = {
                    q: [rnd(ds[f"{var}_{q}"].sel(drought_region_id=rid, lead_week=lw).values, d) for lw in range(4)]
                    for q in ("p10", "p50", "p90")
                }
            else:
                e["f"] = {"p50": [rnd(ds[f"{var}_p50"].sel(drought_region_id=rid, lead_week=lw).values, 0) for lw in range(4)]}
            shard["r"][str(rid)] = e
        s = json.dumps(shard, separators=(",", ":"))
        (out_dir / f"{var}.json").write_text(s)
        print(f"  shard {var}: {len(s) / 1e3:.0f} kB", flush=True)


def check_clim_by_valid_date(ds, clim) -> None:
    """Same region and valid date must give the same climatology on every (frt, lead)."""
    va = pd.to_datetime(ds.valid_at.isel(drought_region_id=0).values.ravel())
    v = clim["precip_sum_1m_ref_p50"].isel(drought_region_id=0).values.ravel()
    spread = pd.Series(v, index=va).groupby(level=0).agg(lambda s: s.max() - s.min()).max()
    assert spread == 0, spread


def main() -> None:
    out_dir = Path(sys.argv[1])
    ds, pers, clim, obs = load()
    check_clim_by_valid_date(ds, clim)
    rng = np.random.default_rng(SEED + 1)
    res = {"periods": {}, "meta": {"n_boot": N_BOOT, "block_weeks": BLOCK}}
    for name, (a, b) in PERIODS.items():
        print(name, flush=True)
        res["periods"][name] = evaluate(ds, pers, clim, a, b, rng)
    (out_dir / "numeric_skill.json").write_text(json.dumps(_clean(res), separators=(",", ":")))
    meteogram_shards(ds, clim, obs, out_dir / "mg")


if __name__ == "__main__":
    main()

"""Categorical verification of the p50 forecast of the ordinal drought indices.

Run from the repo root:
    poetry run python reports/skill_report/categorical_skill.py <out_dir>

Indices take levels 1 (no drought) .. 5. Scores are computed per lead week,
pooled over Monday issue dates x drought regions. Uncertainty comes from a
moving-block bootstrap over issue weeks (all regions kept together), so both
spatial correlation and week-to-week autocorrelation are respected.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

NC = "data/netcdf"
INDICES = [
    "cdi",
    "precip_1m_index",
    "precip_3m_index",
    "precip_24m_index",
    "hydro_index",
    "soil_moisture_index",
]
K = 5
THRESHOLDS = [2, 3, 4]  # event: level >= k
PERIODS = {
    "full": ("2025-07-01", "2026-09-30"),
    "season2026": ("2026-04-13", "2026-09-30"),
    "before2026season": ("2025-07-01", "2026-04-12"),
}
N_BOOT = 2000
BLOCK = 4  # weeks
SEED = 42


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def load() -> tuple[xr.Dataset, xr.Dataset]:
    ds = xr.open_dataset(f"{NC}/merged.nc")
    ds = ds.isel(forecast_reference_time=(ds.forecast_reference_time.dt.weekday == 0).values)
    frt = ds.forecast_reference_time
    pers = xr.open_dataset(f"{NC}/persistence_reference.nc").sel(forecast_reference_time=frt)
    return ds, pers


def weekly_tables(f: np.ndarray, o: np.ndarray) -> np.ndarray:
    """(t, r) categorical arrays -> (t, K, K) counts, rows = forecast, cols = obs."""
    tab = np.zeros((f.shape[0], K, K))
    ok = np.isfinite(f) & np.isfinite(o)
    for t in range(f.shape[0]):
        fi = f[t][ok[t]].astype(int) - 1
        oi = o[t][ok[t]].astype(int) - 1
        np.add.at(tab[t], (fi, oi), 1)
    return tab


# ---------------------------------------------------------------------------
# Scores from a K x K table (rows forecast, cols obs)
# ---------------------------------------------------------------------------


def gerrity_weights(p_obs: np.ndarray) -> np.ndarray:
    """Gerrity (1992) scoring matrix for the categories with p_obs > 0."""
    k = len(p_obs)
    cum = np.cumsum(p_obs)[:-1]
    a = (1 - cum) / cum
    s = np.zeros((k, k))
    for i in range(k):
        for j in range(i, k):
            s[i, j] = (np.sum(1 / a[:i]) + np.sum(a[j:]) - (j - i)) / (k - 1)
            s[j, i] = s[i, j]
    return s


def multi_scores(tab: np.ndarray) -> dict:
    """Gerrity weights come from this table's own observed frequencies."""
    n = tab.sum()
    keep = tab.sum(0) > 0
    if n == 0 or keep.sum() < 2:
        return dict.fromkeys(("pc", "pc1", "hss", "pss", "gss", "under", "over"), np.nan)
    w = gerrity_weights(tab.sum(0)[keep] / n)
    # Categories never observed in the sample are folded into the nearest observed one
    kept_idx = np.flatnonzero(keep)
    to_kept = np.array([np.argmin(np.abs(kept_idx - c)) for c in range(K)])
    t = np.zeros((len(kept_idx), len(kept_idx)))
    np.add.at(t, (to_kept[:, None].repeat(K, 1), to_kept[None, :].repeat(K, 0)), tab)
    p = t / n
    pf, po = p.sum(1), p.sum(0)
    pc = np.trace(p)
    e = np.sum(pf * po)
    hss = (pc - e) / (1 - e) if e < 1 else np.nan
    pss = (pc - e) / (1 - np.sum(po**2)) if np.sum(po**2) < 1 else np.nan
    gss = np.sum(p * w)
    i, j = np.indices(tab.shape)
    return {
        "pc": pc,
        "pc1": tab[np.abs(i - j) <= 1].sum() / n,
        "hss": hss,
        "pss": pss,
        "gss": gss,
        "under": tab[i < j].sum() / n,  # forecast level lower (milder) than observed
        "over": tab[i > j].sum() / n,
    }


def binary_scores(tab: np.ndarray, k: int) -> dict:
    """Event = level >= k. a hits, b false alarms, c misses, d correct negatives."""
    ev = np.arange(1, K + 1) >= k
    a = tab[np.ix_(ev, ev)].sum()
    b = tab[np.ix_(ev, ~ev)].sum()
    c = tab[np.ix_(~ev, ev)].sum()
    d = tab[np.ix_(~ev, ~ev)].sum()
    n = a + b + c + d
    out = {"base_rate": (a + c) / n if n else np.nan}
    with np.errstate(divide="ignore", invalid="ignore"):
        pod = a / (a + c)
        pofd = b / (b + d)
        far = b / (a + b)
        fbi = (a + b) / (a + c)
        csi = a / (a + b + c)
        ar = (a + b) * (a + c) / n
        ets = (a - ar) / (a + b + c - ar)
        hss = 2 * (a * d - b * c) / ((a + c) * (c + d) + (a + b) * (b + d))
        pss = pod - pofd
        # SEDI (Ferro & Stephenson 2011): base-rate independent, defined for H, F in (0,1)
        h = np.clip(pod, 1e-6, 1 - 1e-6)
        f = np.clip(pofd, 1e-6, 1 - 1e-6)
        sedi = (np.log(f) - np.log(h) - np.log(1 - f) + np.log(1 - h)) / (
            np.log(f) + np.log(h) + np.log(1 - f) + np.log(1 - h)
        )
    out.update(
        pod=pod, far=far, pofd=pofd, fbi=fbi, csi=csi, ets=ets, hss=hss, pss=pss, sedi=sedi
    )
    return {kk: float(v) for kk, v in out.items()}


# ---------------------------------------------------------------------------
# Transition (change) diagnostics relative to the last observation
# ---------------------------------------------------------------------------


def change_counts(f: np.ndarray, o: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Per-week counts used for change diagnostics -> (t, 9).

    0 n_change, 1 change exact hit, 2 change direction hit,
    3 n_nochange, 4 nochange & fcst kept the level,
    5 n_onset (p<3, o>=3), 6 onset caught (f>=3),
    7 n_no-onset (p<3, o<3), 8 false onset (f>=3)
    """
    ok = np.isfinite(f) & np.isfinite(o) & np.isfinite(p)
    out = np.zeros((f.shape[0], 9))
    for t in range(f.shape[0]):
        ff, oo, pp = f[t][ok[t]], o[t][ok[t]], p[t][ok[t]]
        ch = oo != pp
        out[t, 0] = ch.sum()
        out[t, 1] = (ch & (ff == oo)).sum()
        out[t, 2] = (ch & (np.sign(ff - pp) == np.sign(oo - pp))).sum()
        out[t, 3] = (~ch).sum()
        out[t, 4] = (~ch & (ff == pp)).sum()
        dry0 = pp < 3
        out[t, 5] = (dry0 & (oo >= 3)).sum()
        out[t, 6] = (dry0 & (oo >= 3) & (ff >= 3)).sum()
        out[t, 7] = (dry0 & (oo < 3)).sum()
        out[t, 8] = (dry0 & (oo < 3) & (ff >= 3)).sum()
    return out


def change_scores(c: np.ndarray) -> dict:
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "n_change": float(c[0]),
            "frac_change": float(c[0] / (c[0] + c[3])),
            "change_exact": float(c[1] / c[0]),
            "change_direction": float(c[2] / c[0]),
            "nochange_kept": float(c[4] / c[3]),
            "n_onset": float(c[5]),
            "onset_pod": float(c[6] / c[5]),
            "onset_false_rate": float(c[8] / c[7]),
        }


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def block_indices(n: int, rng: np.random.Generator) -> np.ndarray:
    nb = int(np.ceil(n / BLOCK))
    starts = rng.integers(0, n - BLOCK + 1, nb)
    return (starts[:, None] + np.arange(BLOCK)).ravel()[:n]


def ci(samples: list[float]) -> list[float]:
    a = np.asarray(samples, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return [np.nan, np.nan]
    return [float(np.percentile(a, 5)), float(np.percentile(a, 95))]


def evaluate(ds, pers, start, end, rng) -> dict:
    sl = slice(start, end)
    dss, ps = (x.sel(forecast_reference_time=sl) for x in (ds, pers))
    n_t = dss.sizes["forecast_reference_time"]
    boots = [block_indices(n_t, rng) for _ in range(N_BOOT)]
    res: dict = {"n_weeks": n_t, "start": start, "end": end, "indices": {}}

    for var in INDICES:
        vres: dict = {}
        for lw in range(4):
            sel = dict(lead_week=lw)
            get = lambda d, k: d[k].sel(sel).transpose("forecast_reference_time", ...).values  # noqa: E731
            o = get(dss, f"{var}_obs")
            srcs = {"fcst": get(dss, f"{var}_p50"), "pers": get(ps, f"{var}_ref_p50")}
            tabs = {s: weekly_tables(a, o) for s, a in srcs.items()}
            tot = {s: t.sum(0) for s, t in tabs.items()}

            lres: dict = {
                "n": float(tot["fcst"].sum()),
                "obs_freq": (tot["fcst"].sum(0) / tot["fcst"].sum()).tolist(),
                "table": {s: tot[s].astype(int).tolist() for s in srcs},
            }
            for s in srcs:
                lres[s] = {
                    "multi": multi_scores(tot[s]),
                    "binary": {str(k): binary_scores(tot[s], k) for k in THRESHOLDS},
                }

            chg = change_counts(srcs["fcst"], o, srcs["pers"])
            lres["change"] = change_scores(chg.sum(0))

            # Bootstrap: scores for fcst and pers, and their paired difference
            bs: dict = {}
            for b in boots:
                tb = {s: tabs[s][b].sum(0) for s in srcs}
                ms = {s: multi_scores(tb[s]) for s in tb}
                bn = {s: {k: binary_scores(tb[s], k) for k in THRESHOLDS} for s in tb}
                for m in ("gss", "hss", "pc"):
                    bs.setdefault(f"diff.{m}", []).append(ms["fcst"][m] - ms["pers"][m])
                for k in THRESHOLDS:
                    for m in ("ets", "pss", "sedi"):
                        bs.setdefault(f"diff.{m}{k}", []).append(
                            bn["fcst"][k][m] - bn["pers"][k][m]
                        )
            lres["ci90"] = {kk: ci(v) for kk, v in bs.items()}
            lres["p_fcst_better"] = {
                kk.split(".", 1)[1]: float(np.mean(np.asarray(v) > 0)) for kk, v in bs.items()
            }
            vres[str(lw)] = lres
        res["indices"][var] = vres
        print(f"  {var} done", flush=True)
    return res


def regional_gss(ds, pers) -> dict:
    """GSS per region and lead (full period, no bootstrap) for cdi."""
    out: dict = {"cdi": {}}
    for lw in range(4):
        o = ds["cdi_obs"].sel(lead_week=lw)
        rows = {}
        for rid in ds.drought_region_id.values:
            oo = o.sel(drought_region_id=rid).values[:, None]
            r = {}
            for s, src in (("fcst", ds["cdi_p50"]), ("pers", pers["cdi_ref_p50"])):
                ff = src.sel(lead_week=lw, drought_region_id=rid).values[:, None]
                r[s] = multi_scores(weekly_tables(ff, oo).sum(0))["gss"]
            rows[int(rid)] = r
        out["cdi"][str(lw)] = rows
    return out


def timeline(ds, pers) -> dict:
    """Weekly fraction of regions at level >= 3: obs, fcst (by lead), persistence."""
    frt = pd.to_datetime(ds.forecast_reference_time.values)
    out = {"frt": [d.strftime("%Y-%m-%d") for d in frt]}
    frac = lambda da: (da >= 3).mean("drought_region_id").round(3).values.tolist()  # noqa: E731
    for var in INDICES:
        d = {}
        for lw in range(4):
            sel = dict(lead_week=lw)
            d[str(lw)] = {
                "valid": [
                    pd.Timestamp(v).strftime("%Y-%m-%d")
                    for v in ds.valid_at.sel(sel).isel(drought_region_id=0).values
                ],
                "obs": frac(ds[f"{var}_obs"].sel(sel)),
                "fcst": frac(ds[f"{var}_p50"].sel(sel)),
                "pers": frac(pers[f"{var}_ref_p50"].sel(sel)),
            }
        out[var] = d
    return out


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    if isinstance(x, float | np.floating):
        return None if not np.isfinite(x) else round(float(x), 4)
    return x


def main() -> None:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    ds, pers = load()
    rng = np.random.default_rng(SEED)
    result = {"periods": {}}
    for name, (a, b) in PERIODS.items():
        print(name, flush=True)
        result["periods"][name] = evaluate(ds, pers, a, b, rng)
    result["regional"] = regional_gss(ds, pers)
    result["timeline"] = timeline(ds, pers)
    result["meta"] = {"n_boot": N_BOOT, "block_weeks": BLOCK, "thresholds": THRESHOLDS}
    (out_dir / "categorical_skill.json").write_text(json.dumps(_clean(result)))


if __name__ == "__main__":
    main()

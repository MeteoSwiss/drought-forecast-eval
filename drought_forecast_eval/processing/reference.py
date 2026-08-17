"""Reference forecast construction for skill-score baselines.

Two reference strategies are implemented:

climatology_reference
    For each ``(drought_region_id, week_of_year)`` compute the historical
    distribution (p10 / p50 / p90) using all available years, with a
    ``±week_window`` buffer around the target week-of-year to smooth
    sparseness at weekly resolution.  Returns a reference dataset on the
    same ``(forecast_reference_time, drought_region_id, lead_week)`` grid
    as the forecast, so that RPSS = 1 − score(fcst) / score(ref) works
    dimension-cleanly.

persistence_reference
    For each ``forecast_reference_time``, uses the **last observed value
    before that date** as the flat reference forecast across all lead weeks.
    Returns a reference dataset on the same grid as the forecast.

Both functions return an ``xr.Dataset`` whose variable names match the
**observation** variable names (not the forecast quantile names), making
them directly usable as the ``ds_ref`` argument to
:func:`~drought_forecast_eval.scoring.skill.mae_skill` and
:func:`~drought_forecast_eval.scoring.skill.rpss`.
"""

from __future__ import annotations

import logging

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Climatology reference
# ---------------------------------------------------------------------------


def climatology_reference(
    ds_obs: xr.Dataset,
    ds_fcst: xr.Dataset,
    week_window: int = 4,
) -> xr.Dataset:
    """Build a climatological reference forecast on the forecast grid.

    For each target ``valid_at`` (Monday), collect all historical
    observations within ±``week_window`` ISO-weeks of the same week-of-year
    across all available years.  Return p10 / p50 / p90 of that sample as
    the probabilistic reference forecast.

    Parameters
    ----------
    ds_obs:
        Observation dataset with dims ``(drought_region_id, valid_at)``.
    ds_fcst:
        Forecast dataset used only for its grid coordinates
        ``(forecast_reference_time, drought_region_id, lead_week, valid_at)``.
    week_window:
        Half-width of the week-of-year window (inclusive).  Default 4 means
        ±4 ISO weeks around the target week are included in the sample.

    Returns
    -------
    xr.Dataset
        Dimensions ``(forecast_reference_time, drought_region_id, lead_week)``.
        For each observation variable ``v`` the dataset contains
        ``v_ref_p10``, ``v_ref_p50``, ``v_ref_p90``.
    """
    frt_dim = "forecast_reference_time"
    region_dim = "drought_region_id"
    lead_dim = "lead_week"

    # ISO week-of-year and year for observations — no DataFrame conversion
    obs_cal = ds_obs.valid_at.dt.isocalendar()
    obs_woy = obs_cal.week.values.astype(np.int32)
    obs_year = obs_cal.year.values.astype(np.int32)

    # Same quantities for every grid cell in the forecast valid_at array
    valid_at_da = ds_fcst["valid_at"]  # (frt, region, lead)
    fcst_cal = valid_at_da.dt.isocalendar()
    _woy = fcst_cal.week.values
    _year = fcst_cal.year.values
    nat_flag = np.isnan(_woy.astype(float))
    fcst_woy = np.where(nat_flag, -1, _woy).astype(np.int32)
    fcst_year = np.where(nat_flag, -1, _year).astype(np.int32)

    valid_flag = fcst_woy >= 0
    unique_pairs = (
        np.unique(np.column_stack([fcst_woy[valid_flag], fcst_year[valid_flag]]), axis=0)
        if valid_flag.any()
        else np.empty((0, 2), dtype=np.int32)
    )

    frt_vals = ds_fcst[frt_dim].values
    region_vals = ds_fcst[region_dim].values
    lead_vals = ds_fcst[lead_dim].values
    obs_vars = list(ds_obs.data_vars)
    n_frt, n_region, n_lead = len(frt_vals), len(region_vals), len(lead_vals)
    shape = (n_frt, n_region, n_lead)

    results: dict[str, np.ndarray] = {
        f"{v}_ref_{q}": np.full(shape, np.nan)
        for v in obs_vars for q in ("p10", "p50", "p90")
    }
    q_map = {"p10": 0.1, "p50": 0.5, "p90": 0.9}

    for woy_i, year_i in unique_pairs:
        woy_i, year_i = int(woy_i), int(year_i)
        lo, hi = woy_i - week_window, woy_i + week_window
        if lo < 1:
            in_window = (obs_woy >= lo + 52) | (obs_woy <= hi)
        elif hi > 52:
            in_window = (obs_woy >= lo) | (obs_woy <= hi - 52)
        else:
            in_window = (obs_woy >= lo) & (obs_woy <= hi)

        sel_idx = np.nonzero(in_window & (obs_year != year_i))[0]
        if sel_idx.size < 3:
            logger.debug(
                "Climatology: only %d samples for woy=%d year_excl=%d",
                sel_idx.size, woy_i, year_i,
            )
            continue

        # Percentiles for ALL regions at once — vectorised over region dim
        pct_ds = ds_obs.isel(valid_at=sel_idx).quantile([0.1, 0.5, 0.9], dim="valid_at")
        pair_mask = (fcst_woy == woy_i) & (fcst_year == year_i)  # (n_frt, n_region, n_lead)

        for v in obs_vars:
            pct_v = pct_ds[v].sel({region_dim: region_vals})
            for q_str, q_val in q_map.items():
                per_region = pct_v.sel(quantile=q_val).values  # (n_region,)
                key = f"{v}_ref_{q_str}"
                results[key] = np.where(
                    pair_mask,
                    np.broadcast_to(per_region[np.newaxis, :, np.newaxis], shape),
                    results[key],
                )

    coords = {frt_dim: frt_vals, region_dim: region_vals, lead_dim: lead_vals}
    data_vars = {k: ([frt_dim, region_dim, lead_dim], v) for k, v in results.items()}
    ds_ref = xr.Dataset(data_vars, coords=coords)
    ds_ref.attrs["reference_type"] = "climatology"
    ds_ref.attrs["week_window"] = week_window
    return ds_ref


# ---------------------------------------------------------------------------
# Persistence reference
# ---------------------------------------------------------------------------


def persistence_reference(
    ds_obs: xr.Dataset,
    ds_fcst: xr.Dataset,
) -> xr.Dataset:
    """Build a persistence reference forecast on the forecast grid.

    For each ``forecast_reference_time`` and ``drought_region_id``, the last
    observed value **strictly before** the ``forecast_reference_time`` is used
    as the flat reference across all lead weeks.

    Parameters
    ----------
    ds_obs:
        Observation dataset with dims ``(drought_region_id, valid_at)``.
    ds_fcst:
        Forecast dataset used for its grid coordinates.

    Returns
    -------
    xr.Dataset
        Dimensions ``(forecast_reference_time, drought_region_id, lead_week)``.
        For each observation variable ``v`` the dataset contains
        ``v_ref_p50`` (persistence is deterministic, stored as p50 for
        consistency with the climatology reference interface).
    """
    frt_dim = "forecast_reference_time"
    region_dim = "drought_region_id"
    lead_dim = "lead_week"

    ds_obs = ds_obs.sortby("valid_at")
    obs_valid_at = ds_obs.valid_at.values  # sorted datetime64

    frt_vals = ds_fcst[frt_dim].values
    region_vals = ds_fcst[region_dim].values
    lead_vals = ds_fcst[lead_dim].values
    obs_vars = list(ds_obs.data_vars)

    # For each frt, find the index of the last obs strictly before it
    frt_cast = frt_vals.astype(obs_valid_at.dtype)
    indices = np.searchsorted(obs_valid_at, frt_cast, side="left") - 1  # (n_frt,)
    valid_frt = indices >= 0

    indices_da = xr.DataArray(
        np.where(valid_frt, indices, 0),
        dims=[frt_dim],
        coords={frt_dim: frt_vals},
    )
    valid_da = xr.DataArray(valid_frt, dims=[frt_dim], coords={frt_dim: frt_vals})

    # Select last prior obs for every region simultaneously — vectorised
    last_obs = ds_obs.isel(valid_at=indices_da).where(valid_da)  # (region, frt)

    n_lead = len(lead_vals)
    coords = {frt_dim: frt_vals, region_dim: region_vals, lead_dim: lead_vals}
    data_vars = {}

    for v in obs_vars:
        vals_2d = (
            last_obs[v].sel({region_dim: region_vals}).transpose(frt_dim, region_dim).values
        )  # (n_frt, n_region)
        data_vars[f"{v}_ref_p50"] = (
            [frt_dim, region_dim, lead_dim],
            np.repeat(vals_2d[:, :, np.newaxis], n_lead, axis=2),
        )

    ds_ref = xr.Dataset(data_vars, coords=coords)
    ds_ref.attrs["reference_type"] = "persistence"
    return ds_ref

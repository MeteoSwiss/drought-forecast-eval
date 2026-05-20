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
import pandas as pd
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
    # Convert observations to pandas for efficient grouped operations
    obs_df = ds_obs.to_dataframe().reset_index()
    obs_df["week_of_year"] = obs_df["valid_at"].dt.isocalendar().week.astype(int)

    # Target grid: valid_at per (frt, region, lead_week)
    valid_at_da = ds_fcst["valid_at"]  # dims: (frt, region, lead_week)
    region_dim = "drought_region_id"
    frt_dim = "forecast_reference_time"
    lead_dim = "lead_week"

    # Flatten the grid to iterate efficiently
    frt_vals = ds_fcst[frt_dim].values
    region_vals = ds_fcst[region_dim].values
    lead_vals = ds_fcst[lead_dim].values

    obs_vars = list(ds_obs.data_vars)

    # Build output arrays:  shape (n_frt, n_region, n_lead)
    n_frt = len(frt_vals)
    n_region = len(region_vals)
    n_lead = len(lead_vals)
    shape = (n_frt, n_region, n_lead)

    results: dict[str, np.ndarray] = {
        f"{v}_ref_{q}": np.full(shape, np.nan)
        for v in obs_vars
        for q in ("p10", "p50", "p90")
    }

    for i_r, region in enumerate(region_vals):
        region_obs = obs_df[obs_df[region_dim] == region]
        for i_f, frt in enumerate(frt_vals):
            for i_l, lead in enumerate(lead_vals):
                target_valid_at = valid_at_da.sel(
                    {frt_dim: frt, region_dim: region, lead_dim: lead}
                ).values
                if pd.isna(target_valid_at):
                    continue
                target_ts = pd.Timestamp(target_valid_at)
                target_woy = target_ts.isocalendar().week

                # Weeks within window (handle wrap-around at 52/53)
                lo = int(target_woy) - week_window
                hi = int(target_woy) + week_window
                if lo < 1:
                    mask = (region_obs["week_of_year"] >= lo + 52) | (
                        region_obs["week_of_year"] <= hi
                    )
                elif hi > 52:
                    mask = (region_obs["week_of_year"] >= lo) | (
                        region_obs["week_of_year"] <= hi - 52
                    )
                else:
                    mask = (region_obs["week_of_year"] >= lo) & (
                        region_obs["week_of_year"] <= hi
                    )

                # Exclude the target year itself to avoid data leakage
                target_year = target_ts.year
                mask = mask & (region_obs["valid_at"].dt.year != target_year)

                sample = region_obs[mask]
                if len(sample) < 3:
                    logger.debug(
                        "Climatology: only %d samples for region=%s woy=%s ±%d",
                        len(sample), region, target_woy, week_window,
                    )

                for v in obs_vars:
                    vals = sample[v].dropna().values
                    if len(vals) == 0:
                        continue
                    results[f"{v}_ref_p10"][i_f, i_r, i_l] = np.percentile(vals, 10)
                    results[f"{v}_ref_p50"][i_f, i_r, i_l] = np.percentile(vals, 50)
                    results[f"{v}_ref_p90"][i_f, i_r, i_l] = np.percentile(vals, 90)

    coords = {
        frt_dim: frt_vals,
        region_dim: region_vals,
        lead_dim: lead_vals,
    }
    data_vars = {
        k: ([frt_dim, region_dim, lead_dim], v)
        for k, v in results.items()
    }
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
    obs_df = ds_obs.to_dataframe().reset_index()
    obs_df = obs_df.sort_values("valid_at")

    frt_dim = "forecast_reference_time"
    region_dim = "drought_region_id"
    lead_dim = "lead_week"

    frt_vals = ds_fcst[frt_dim].values
    region_vals = ds_fcst[region_dim].values
    lead_vals = ds_fcst[lead_dim].values

    obs_vars = list(ds_obs.data_vars)
    n_frt = len(frt_vals)
    n_region = len(region_vals)
    n_lead = len(lead_vals)
    shape = (n_frt, n_region, n_lead)

    results: dict[str, np.ndarray] = {
        f"{v}_ref_p50": np.full(shape, np.nan) for v in obs_vars
    }

    for i_r, region in enumerate(region_vals):
        region_obs = obs_df[obs_df[region_dim] == region].set_index("valid_at")
        for i_f, frt in enumerate(frt_vals):
            frt_ts = pd.Timestamp(frt)
            # Last observation strictly before frt
            prior = region_obs[region_obs.index < frt_ts]
            if prior.empty:
                logger.debug(
                    "Persistence: no prior obs for region=%s before %s", region, frt_ts
                )
                continue
            last_obs = prior.iloc[-1]
            for v in obs_vars:
                if v in last_obs.index:
                    val = last_obs[v]
                    for i_l in range(n_lead):
                        results[f"{v}_ref_p50"][i_f, i_r, i_l] = val

    coords = {
        frt_dim: frt_vals,
        region_dim: region_vals,
        lead_dim: lead_vals,
    }
    data_vars = {
        k: ([frt_dim, region_dim, lead_dim], v)
        for k, v in results.items()
    }
    ds_ref = xr.Dataset(data_vars, coords=coords)
    ds_ref.attrs["reference_type"] = "persistence"
    return ds_ref

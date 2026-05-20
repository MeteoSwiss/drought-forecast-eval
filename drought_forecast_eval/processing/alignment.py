"""Align observation data onto the forecast grid and merge into one Dataset.

The forecast dataset has dimensions ``(forecast_reference_time, drought_region_id,
lead_week)`` with a derived ``valid_at`` coordinate.  Observations are indexed by
``(drought_region_id, valid_at)``.

Alignment strategy
------------------
1. For every ``(forecast_reference_time, drought_region_id, lead_week)`` cell,
   look up ``valid_at`` from the forecast coordinates.
2. Select the corresponding observation row at the same ``(drought_region_id,
   valid_at)`` point.
3. Attach observation variables to the merged dataset with an ``_obs`` suffix
   to avoid clashes with forecast variable names.

Missing observations (NaN) are kept — coverage statistics are reported via
``logging`` so the caller is informed without crashing.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)


def align_obs_to_forecast(
    ds_fcst: xr.Dataset,
    ds_obs: xr.Dataset,
) -> xr.Dataset:
    """Merge observations onto the forecast ``(frt, region, lead_week)`` grid.

    Parameters
    ----------
    ds_fcst:
        Forecast dataset with dims ``(forecast_reference_time, drought_region_id,
        lead_week)`` and coordinate ``valid_at``.
    ds_obs:
        Observation dataset with dims ``(drought_region_id, valid_at)``.

    Returns
    -------
    xr.Dataset
        The forecast dataset with observation variables appended under the
        suffix ``_obs``.  Dimensions remain
        ``(forecast_reference_time, drought_region_id, lead_week)``.

    Raises
    ------
    ValueError
        If ``ds_fcst`` is missing the ``valid_at`` coordinate.
    """
    if "valid_at" not in ds_fcst.coords:
        raise ValueError(
            "ds_fcst must contain a 'valid_at' coordinate. "
            "Run load_forecasts() before calling align_obs_to_forecast()."
        )

    # Reindex observations to the valid_at values present in the forecast.
    # We use advanced indexing: broadcast valid_at over all (frt, region, lead)
    # cells and pull the matching obs row.

    # valid_at has shape (forecast_reference_time, drought_region_id, lead_week)
    valid_at_da = ds_fcst["valid_at"]  # DataArray

    # For each obs variable, select along valid_at using the forecast grid
    # ------------------------------------------------------------------ #
    # Build a lookup from (drought_region_id, valid_at_day) → obs values #
    # ------------------------------------------------------------------ #
    frt_dim = "forecast_reference_time"
    region_dim = "drought_region_id"
    lead_dim = "lead_week"

    frt_vals = ds_fcst[frt_dim].values
    region_vals = ds_fcst[region_dim].values
    lead_vals = ds_fcst[lead_dim].values
    n_frt = len(frt_vals)
    n_region = len(region_vals)
    n_lead = len(lead_vals)

    # Flatten valid_at to (n_frt, n_region, n_lead) array of date strings for lookup
    valid_at_np = valid_at_da.values  # shape (n_frt, n_region, n_lead), dtype datetime64

    # Build observation lookup: {(region_id, date_day): {var: value}}
    obs_df = ds_obs.to_dataframe().reset_index()
    obs_df["obs_day"] = pd.to_datetime(obs_df["valid_at"]).dt.floor("D")
    obs_lookup: dict[tuple, dict] = {}
    obs_var_names = [
        c for c in obs_df.columns if c not in ["drought_region_id", "valid_at", "obs_day"]
    ]
    for _, row in obs_df.iterrows():
        key = (int(row["drought_region_id"]), row["obs_day"])
        obs_lookup[key] = {v: row[v] for v in obs_var_names}

    obs_vars: dict[str, xr.DataArray] = {}
    shape = (n_frt, n_region, n_lead)
    coords = {
        frt_dim: frt_vals,
        region_dim: region_vals,
        lead_dim: lead_vals,
    }
    dims = [frt_dim, region_dim, lead_dim]

    for var in ds_obs.data_vars:
        arr = np.full(shape, np.nan)
        for i_f in range(n_frt):
            for i_r, region_id in enumerate(region_vals):
                for i_l in range(n_lead):
                    raw_ts = valid_at_np[i_f, i_r, i_l]
                    if raw_ts is None or (
                        hasattr(raw_ts, "__class__") and raw_ts.__class__.__name__ == "NaTType"
                    ):
                        continue
                    day = pd.Timestamp(raw_ts).floor("D")
                    val_dict = obs_lookup.get((int(region_id), day))
                    if val_dict is not None and var in val_dict:
                        v = val_dict[var]
                        if v is not None and not (isinstance(v, float) and np.isnan(v)):
                            arr[i_f, i_r, i_l] = float(v)
        obs_vars[f"{var}_obs"] = xr.DataArray(arr, coords=coords, dims=dims)

    if not obs_vars:
        logger.warning("No observation variables could be aligned to the forecast grid.")
        return ds_fcst

    ds_merged = ds_fcst.assign(obs_vars)

    # Report coverage
    _log_coverage(ds_merged, list(obs_vars.keys()))
    return ds_merged


def _log_coverage(ds: xr.Dataset, obs_var_names: list[str]) -> None:
    """Log NaN coverage statistics for the aligned observation variables."""
    for var in obs_var_names:
        da = ds[var]
        total = da.size
        n_valid = int(np.isfinite(da.values).sum())
        pct = 100.0 * n_valid / total if total > 0 else 0.0
        level = logging.INFO if pct >= 80 else logging.WARNING
        logger.log(
            level,
            "Coverage for '%s': %d / %d cells (%.1f%%)",
            var,
            n_valid,
            total,
            pct,
        )

"""Skill score wrappers and helper scoring functions.

All functions accept and return ``xr.DataArray`` / ``xr.Dataset`` objects so
that they compose cleanly with the ``scores`` library and with xarray's
``groupby`` / ``mean`` machinery.

Functions
---------
mae_skill
    Skill score relative to a reference based on MAE.
    SS = 1 − MAE(fcst, obs) / MAE(ref, obs)

rpss
    Ranked Probability Skill Score relative to a reference.
    RPSS = 1 − RPS(fcst, obs) / RPS(ref, obs)

rps_from_quantiles
    Approximate RPS from p10/p50/p90 quantile forecasts by constructing
    a piecewise-linear CDF and integrating.

roc_auc_xr
    Area under the ROC curve for a binary event defined by a threshold.
    Operates on the p50 (median) forecast treated as a deterministic
    probability proxy, or on an ensemble.

interval_score_xr
    Winkler interval score for a (p10, p90) prediction interval.

pinball_loss_xr
    Pinball (quantile) loss for a single quantile level.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

try:
    import scores.continuous as _scores_cont
    _SCORES_AVAILABLE = True
except ImportError:
    _SCORES_AVAILABLE = False


# ---------------------------------------------------------------------------
# MAE skill score
# ---------------------------------------------------------------------------

def mae_skill(
    fcst: xr.DataArray,
    obs: xr.DataArray,
    ref: xr.DataArray,
    reduce_dims: list[str] | None = None,
) -> xr.DataArray:
    """Compute MAE-based skill score.

    SS = 1 - MAE(fcst, obs) / MAE(ref, obs)

    A skill score of 1 is perfect; 0 means equal to reference; negative
    means worse than reference.

    Parameters
    ----------
    fcst:
        Forecast DataArray (deterministic or p50).
    obs:
        Observation DataArray.
    ref:
        Reference forecast DataArray (same shape as obs).
    reduce_dims:
        Dimensions over which to average MAE before computing the ratio.
        Defaults to ``["forecast_reference_time"]``.

    Returns
    -------
    xr.DataArray
    """
    if reduce_dims is None:
        reduce_dims = ["forecast_reference_time"]

    if _SCORES_AVAILABLE:
        # scores library rejects simultaneous reduce_dims + preserve_dims; use only reduce_dims
        mae_f = _scores_cont.mae(fcst, obs, reduce_dims=reduce_dims)
        mae_r = _scores_cont.mae(ref, obs, reduce_dims=reduce_dims)
    else:
        mae_f = np.abs(fcst - obs).mean(dim=reduce_dims)
        mae_r = np.abs(ref - obs).mean(dim=reduce_dims)

    # Avoid division by zero: if reference MAE is 0 the forecast is perfect too
    skill = xr.where(mae_r == 0, 1.0, 1.0 - mae_f / mae_r)
    skill.attrs["long_name"] = "MAE Skill Score"
    skill.attrs["units"] = "1"
    return skill


# ---------------------------------------------------------------------------
# RPS / RPSS
# ---------------------------------------------------------------------------

def rps_from_quantiles(
    obs: xr.DataArray,
    p10: xr.DataArray,
    p50: xr.DataArray,
    p90: xr.DataArray,
    thresholds: np.ndarray | None = None,
) -> xr.DataArray:
    """Compute approximate RPS from three-quantile forecast.

    A piecewise-linear CDF is constructed from p10 / p50 / p90 and evaluated
    at ``thresholds``.  The observed CDF is a step function at the observed
    value.  RPS is the squared area between the two CDFs (discrete
    approximation).

    Parameters
    ----------
    obs:
        Observed values DataArray.
    p10, p50, p90:
        Forecast quantile DataArrays.
    thresholds:
        Evaluation points.  If ``None``, 20 equally-spaced percentiles of the
        combined forecast range are used.

    Returns
    -------
    xr.DataArray
        RPS values (same dims as obs, minus the quantile axis).
    """
    # Stack quantile values for interpolation
    quantile_levels = np.array([0.10, 0.50, 0.90])
    fcst_quantiles = xr.concat([p10, p50, p90], dim="quantile_level")
    fcst_quantiles["quantile_level"] = quantile_levels

    if thresholds is None:
        # Use a fixed grid spanning the typical range of the forecast
        q_min = float(p10.min())
        q_max = float(p90.max())
        if not np.isfinite(q_min) or not np.isfinite(q_max):
            return xr.full_like(obs, fill_value=np.nan)
        thresholds = np.linspace(q_min, q_max, 21)

    rps_vals = xr.full_like(obs, fill_value=0.0)

    for thr in thresholds[:-1]:
        # Forecast CDF at threshold: fraction of ensemble ≤ threshold
        # Interpolate the 3-quantile CDF at thr
        fcst_cdf = _interp_quantile_cdf(fcst_quantiles, thr, quantile_levels)
        # Observed CDF: 1 if obs ≤ thr, else 0
        obs_cdf = (obs <= thr).astype(float)
        step = thresholds[1] - thresholds[0]
        rps_vals = rps_vals + ((fcst_cdf - obs_cdf) ** 2) * step

    rps_vals.attrs["long_name"] = "Ranked Probability Score (approx. from 3 quantiles)"
    return rps_vals


def _interp_quantile_cdf(
    fcst_quantiles: xr.DataArray,
    threshold: float,
    quantile_levels: np.ndarray,
) -> xr.DataArray:
    """Linearly interpolate forecast CDF probability at a given threshold value.

    ``fcst_quantiles`` has a ``quantile_level`` dimension with values of the
    forecast at probability levels [0.10, 0.50, 0.90].  We invert this to get
    the probability that the forecast ≤ threshold.
    """
    # Build a piecewise linear CDF: (value, prob) anchor points
    # Anchor below p10: prob=0; above p90: prob=1
    p10_vals = fcst_quantiles.sel(quantile_level=0.10, method="nearest").values
    p90_vals = fcst_quantiles.sel(quantile_level=0.90, method="nearest").values

    # Vectorised linear interpolation via numpy
    # Extend anchors: [−∞→0, p10→0.10, p50→0.50, p90→0.90, +∞→1]
    result = np.interp(
        threshold,
        xp=np.array([float(p10_vals.flat[0]) - 1e6,
                     float(p10_vals.flat[0]),
                     float(  # noqa: E501
                         fcst_quantiles.sel(quantile_level=0.50, method="nearest").values.flat[0]
                     ),
                     float(p90_vals.flat[0]),
                     float(p90_vals.flat[0]) + 1e6]),
        fp=np.array([0.0, 0.10, 0.50, 0.90, 1.0]),
        left=0.0, right=1.0,
    )
    # This scalar result needs to be broadcast; for DataArray inputs build a
    # same-shaped array
    return xr.full_like(
        fcst_quantiles.isel(quantile_level=0, drop=True),
        fill_value=float(result),
    )


def rpss(
    obs: xr.DataArray,
    fcst_p10: xr.DataArray,
    fcst_p50: xr.DataArray,
    fcst_p90: xr.DataArray,
    ref_p10: xr.DataArray,
    ref_p50: xr.DataArray,
    ref_p90: xr.DataArray,
    reduce_dims: list[str] | None = None,
) -> xr.DataArray:
    """Ranked Probability Skill Score (RPSS).

    RPSS = 1 − mean(RPS_fcst) / mean(RPS_ref)

    Parameters
    ----------
    obs:
        Observation DataArray.
    fcst_p10, fcst_p50, fcst_p90:
        Forecast quantile DataArrays.
    ref_p10, ref_p50, ref_p90:
        Reference quantile DataArrays.
    reduce_dims:
        Dimensions over which to average RPS.  Defaults to
        ``["forecast_reference_time"]``.

    Returns
    -------
    xr.DataArray
    """
    if reduce_dims is None:
        reduce_dims = ["forecast_reference_time"]

    rps_f = rps_from_quantiles(obs, fcst_p10, fcst_p50, fcst_p90)
    rps_r = rps_from_quantiles(obs, ref_p10, ref_p50, ref_p90)

    mean_rps_f = rps_f.mean(dim=reduce_dims)
    mean_rps_r = rps_r.mean(dim=reduce_dims)

    skill = xr.where(mean_rps_r == 0, 1.0, 1.0 - mean_rps_f / mean_rps_r)
    skill.attrs["long_name"] = "RPSS"
    skill.attrs["units"] = "1"
    return skill


# ---------------------------------------------------------------------------
# Interval score
# ---------------------------------------------------------------------------

def interval_score_xr(
    obs: xr.DataArray,
    lower: xr.DataArray,
    upper: xr.DataArray,
    alpha: float = 0.2,
) -> xr.DataArray:
    """Winkler interval score for a (1−alpha) prediction interval.

    IS = (upper − lower) + (2/alpha)·max(lower − obs, 0) + (2/alpha)·max(obs − upper, 0)

    Default alpha=0.2 corresponds to the 80% prediction interval (p10–p90).

    Parameters
    ----------
    obs:
        Observation DataArray.
    lower:
        Lower bound of the prediction interval (e.g. p10 forecast).
    upper:
        Upper bound of the prediction interval (e.g. p90 forecast).
    alpha:
        Significance level; ``alpha=0.2`` means 80% interval.

    Returns
    -------
    xr.DataArray
    """
    width = upper - lower
    penalty_lower = (2.0 / alpha) * xr.where(lower > obs, lower - obs, 0.0)
    penalty_upper = (2.0 / alpha) * xr.where(obs > upper, obs - upper, 0.0)
    score = width + penalty_lower + penalty_upper
    score.attrs["long_name"] = f"Interval Score (alpha={alpha})"
    score.attrs["alpha"] = alpha
    return score


# ---------------------------------------------------------------------------
# Pinball loss
# ---------------------------------------------------------------------------

def pinball_loss_xr(
    obs: xr.DataArray,
    fcst: xr.DataArray,
    quantile: float,
) -> xr.DataArray:
    """Pinball (quantile) loss for a single quantile level.

    L(q, y, f) = (y − f) · q         if y ≥ f
               = (f − y) · (1 − q)   if y < f

    Parameters
    ----------
    obs:
        Observation DataArray.
    fcst:
        Forecast DataArray at the given quantile level.
    quantile:
        Quantile probability level (e.g. 0.10, 0.50, 0.90).

    Returns
    -------
    xr.DataArray
    """
    diff = obs - fcst
    loss = xr.where(diff >= 0, quantile * diff, (quantile - 1.0) * diff)
    loss.attrs["long_name"] = f"Pinball Loss (q={quantile})"
    loss.attrs["quantile"] = quantile
    return loss


# ---------------------------------------------------------------------------
# ROC-AUC (binary event)
# ---------------------------------------------------------------------------

def roc_auc_xr(
    obs: xr.DataArray,
    fcst_p50: xr.DataArray,
    threshold: float = 2.0,
    reduce_dims: list[str] | None = None,
) -> xr.DataArray:
    """Compute ROC-AUC for a binary drought event.

    The binary event is defined as ``value >= threshold``.  The p50
    forecast is used as a deterministic probability proxy (rank-based AUC).

    Parameters
    ----------
    obs:
        Observation DataArray.
    fcst_p50:
        Forecast median DataArray.
    threshold:
        Event threshold.  Default 2 (CDI ≥ 2 = drought event).
    reduce_dims:
        Dimensions over which to pool samples for the ROC curve.  Defaults
        to ``["forecast_reference_time", "drought_region_id"]``.

    Returns
    -------
    xr.DataArray
        AUC value(s), one per remaining dimension (typically ``lead_week``).
    """
    from sklearn.metrics import roc_auc_score  # lazy import

    if reduce_dims is None:
        reduce_dims = ["forecast_reference_time", "drought_region_id"]

    # Remaining dims after reduction
    keep_dims = [d for d in obs.dims if d not in reduce_dims]

    if not keep_dims:
        # Scalar result
        obs_bin = (obs >= threshold).values.ravel().astype(int)
        fcst_flat = fcst_p50.values.ravel()
        valid = np.isfinite(obs_bin.astype(float)) & np.isfinite(fcst_flat)
        if valid.sum() < 2 or obs_bin[valid].sum() == 0 or obs_bin[valid].sum() == valid.sum():
            return xr.DataArray(np.nan, attrs={"long_name": "ROC-AUC"})
        auc = roc_auc_score(obs_bin[valid], fcst_flat[valid])
        return xr.DataArray(auc, attrs={"long_name": "ROC-AUC", "threshold": threshold})

    # Iterate over remaining dimensions
    results = []
    coords_list = []
    first_keep_dim = keep_dims[0]
    for idx in obs[first_keep_dim].values:
        sel_kwargs = {first_keep_dim: idx}
        obs_slice = obs.sel(sel_kwargs).values.ravel().astype(float)
        fcst_slice = fcst_p50.sel(sel_kwargs).values.ravel().astype(float)
        obs_bin = (obs_slice >= threshold).astype(int)
        valid = np.isfinite(obs_slice) & np.isfinite(fcst_slice)
        if valid.sum() < 2 or obs_bin[valid].sum() == 0 or obs_bin[valid].sum() == valid.sum():
            auc = np.nan
        else:
            try:
                auc = roc_auc_score(obs_bin[valid], fcst_slice[valid])
            except ValueError:
                auc = np.nan
        results.append(auc)
        coords_list.append(idx)

    da = xr.DataArray(
        results,
        coords={first_keep_dim: coords_list},
        dims=[first_keep_dim],
        attrs={"long_name": "ROC-AUC", "threshold": threshold},
    )
    return da

"""Scoring dispatcher: route variable bundles to the correct scorers.

``compute_scores`` is the single entry point.  It:

1. Resolves the ``variables`` argument against ``VARIABLE_MAP``.
2. Resolves the ``scores`` argument against ``SCORE_REGISTRY``.
3. For every (variable, score) pair, checks whether the mode
   (deterministic / quantile) is compatible with the metric.
4. Calls the appropriate scorer, reducing over ``forecast_reference_time``
   so the output has dims ``(lead_week, drought_region_id)``.
5. Attaches reference-forecast skill scores when ``ds_ref`` is provided.
6. Returns a single ``xr.Dataset`` with one variable per
   ``{variable_key}_{metric_name}`` combination.
7. Optionally writes the result to a NetCDF4 file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import xarray as xr

from drought_forecast_eval.scoring.registry import (
    DETERMINISTIC_METRICS,
    QUANTILE_METRICS,
    SCORE_REGISTRY,
)
from drought_forecast_eval.scoring.variable_map import VARIABLE_GROUPS, VARIABLE_MAP

logger = logging.getLogger(__name__)

# Reduce over these dims to obtain (lead_week, drought_region_id) output
_REDUCE_DIMS = ["forecast_reference_time"]

# Lazy resolver: string sentinels in the registry → actual callables
def _resolve(name: str):  # noqa: ANN202
    """Resolve a registry entry that may be a string sentinel."""
    entry = SCORE_REGISTRY.get(name)
    if isinstance(entry, str):
        # Import from skill module
        from drought_forecast_eval.scoring import skill as _skill
        return getattr(_skill, entry)
    return entry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_scores(
    ds: xr.Dataset,
    variables: list[str] | Literal["all"] = "all",
    scores: list[str] | Literal["default"] = "default",
    ds_ref: xr.Dataset | None = None,
    cdi_threshold: float = 2.0,
    output_path: str | Path | None = None,
    variable_map: dict | None = None,
) -> xr.Dataset:
    """Compute verification scores for all requested variables.

    Parameters
    ----------
    ds:
        Merged dataset from
        :func:`~drought_forecast_eval.processing.alignment.align_obs_to_forecast`.
        Must contain both forecast and observation variables.
    variables:
        List of variable keys from ``VARIABLE_MAP`` (e.g. ``["spi_1m", "cdi"]``),
        a group name (``"precipitation"``, ``"streamflow"``, ``"soil_moisture"``,
        ``"cdi"``), or ``"all"`` to score everything.
    scores:
        List of metric names from ``SCORE_REGISTRY``, or ``"default"`` which
        expands to ``["mae", "rmse", "bias", "correlation"]`` plus quantile
        metrics for quantile-mode variables.
    ds_ref:
        Optional reference forecast dataset (from
        :func:`~drought_forecast_eval.processing.reference.climatology_reference`
        or :func:`~drought_forecast_eval.processing.reference.persistence_reference`).
        Required for ``"mae_skill"`` and ``"rpss"``.
    cdi_threshold:
        Threshold for binary drought event used in ROC-AUC.  Default 2.
    output_path:
        If provided, the result dataset is written to this NetCDF4 path.
    variable_map:
        Override the global ``VARIABLE_MAP``.  Useful for custom experiments.

    Returns
    -------
    xr.Dataset
        Dimensions: ``(lead_week, drought_region_id)``.
        Variables: ``{var_key}_{metric}`` for every computed score.
        Global attributes record the computation parameters.

    Raises
    ------
    ValueError
        If none of the requested variables are present in the dataset.
    """
    vmap = variable_map or VARIABLE_MAP
    var_keys = _resolve_variables(variables, vmap)
    score_names = _resolve_score_names(scores)

    result_vars: dict[str, xr.DataArray] = {}
    computed_count = 0

    for var_key in var_keys:
        entry = vmap[var_key]
        obs_col = entry["obs"]
        fcst_cols = entry["fcst"]
        mode = entry["mode"]

        # Check required columns are present
        if obs_col not in ds:
            logger.warning(
                "Skipping '%s': observation column '%s' not in dataset.", var_key, obs_col
            )
            continue
        missing_fcst = [c for c in fcst_cols if c not in ds]
        if missing_fcst:
            logger.warning(
                "Skipping '%s': forecast column(s) %s not in dataset.", var_key, missing_fcst
            )
            continue

        obs = ds[obs_col]
        p50_col = fcst_cols[-1] if mode == "deterministic" else _pick_quantile(fcst_cols, "p50")
        fcst_p50 = ds[p50_col]

        # --- Deterministic scores (applied to p50) ---
        for score_name in score_names:
            if score_name not in DETERMINISTIC_METRICS:
                continue
            if score_name in ("mae_skill",) and ds_ref is None:
                logger.debug("Skipping mae_skill for '%s': no ds_ref provided.", var_key)
                continue
            if score_name == "roc_auc" and var_key != "cdi":
                # ROC-AUC is only meaningful for the ordinal CDI by default;
                # users can force it via a custom variable_map
                continue

            result_da = _compute_deterministic_score(
                score_name=score_name,
                fcst_p50=fcst_p50,
                obs=obs,
                ds_ref=ds_ref,
                var_key=var_key,
                cdi_threshold=cdi_threshold,
                mode=mode,
            )
            if result_da is not None:
                out_name = f"{var_key}_{score_name}"
                result_vars[out_name] = result_da
                computed_count += 1

        # --- Quantile-only scores ---
        if mode == "quantile":
            fcst_p10 = ds[_pick_quantile(fcst_cols, "p10")]
            fcst_p90 = ds[_pick_quantile(fcst_cols, "p90")]

            for score_name in score_names:
                if score_name not in QUANTILE_METRICS:
                    continue
                if score_name == "rpss" and ds_ref is None:
                    logger.debug("Skipping rpss for '%s': no ds_ref provided.", var_key)
                    continue

                result_da = _compute_quantile_score(
                    score_name=score_name,
                    obs=obs,
                    fcst_p10=fcst_p10,
                    fcst_p50=fcst_p50,
                    fcst_p90=fcst_p90,
                    ds_ref=ds_ref,
                    var_key=var_key,
                )
                if result_da is not None:
                    out_name = f"{var_key}_{score_name}"
                    result_vars[out_name] = result_da
                    computed_count += 1

    if not result_vars:
        raise ValueError(
            "No scores could be computed. Check that the dataset contains the "
            "expected observation and forecast variables."
        )

    logger.info(
        "Computed %d score variable(s) for %d variable key(s).", computed_count, len(var_keys)
    )

    ds_scores = xr.Dataset(result_vars)
    ds_scores.attrs.update(
        {
            "source": "drought_forecast_eval",
            "variables_scored": ",".join(var_keys),
            "scores_computed": ",".join(score_names),
            "cdi_threshold": cdi_threshold,
            "reference_type": ds_ref.attrs.get("reference_type", "none") if ds_ref else "none",
        }
    )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ds_scores.to_netcdf(output_path)
        logger.info("Scores written to %s", output_path)

    return ds_scores


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_variables(
    variables: list[str] | Literal["all"],
    vmap: dict,
) -> list[str]:
    """Expand variables argument to a list of var_key strings."""
    if variables == "all":
        return list(vmap.keys())
    # Allow group names
    resolved: list[str] = []
    for v in variables:
        if v in VARIABLE_GROUPS:
            resolved.extend(k for k in VARIABLE_GROUPS[v] if k in vmap)
        elif v in vmap:
            resolved.append(v)
        else:
            logger.warning("Unknown variable key or group: '%s' — skipping.", v)
    return list(dict.fromkeys(resolved))  # deduplicate, preserve order


def _resolve_score_names(scores: list[str] | Literal["default"]) -> list[str]:
    """Expand score names; 'default' gives the standard set."""
    if scores == "default":
        return ["mae", "rmse", "bias", "correlation", "pinball", "interval_score"]
    unknown = [s for s in scores if s not in SCORE_REGISTRY]
    if unknown:
        logger.warning("Unknown score names (not in registry): %s", unknown)
    return [s for s in scores if s in SCORE_REGISTRY]


def _pick_quantile(fcst_cols: list[str], quantile: str) -> str:
    """Return the forecast column name for the requested quantile suffix."""
    for col in fcst_cols:
        if col.endswith(f"_{quantile}"):
            return col
    raise KeyError(f"No column with suffix '_{quantile}' in {fcst_cols}")


def _compute_deterministic_score(
    score_name: str,
    fcst_p50: xr.DataArray,
    obs: xr.DataArray,
    ds_ref: xr.Dataset | None,
    var_key: str,
    cdi_threshold: float,
    mode: str,
) -> xr.DataArray | None:
    """Compute a single deterministic score for one variable."""
    fn = _resolve(score_name)
    if fn is None:
        logger.warning("Score '%s' not found in registry.", score_name)
        return None

    try:
        if score_name == "mae_skill":
            ref_col = _find_ref_col(ds_ref, var_key, "p50")
            if ref_col is None:
                return None
            from drought_forecast_eval.scoring.skill import mae_skill
            da = mae_skill(fcst_p50, obs, ds_ref[ref_col], reduce_dims=_REDUCE_DIMS)
        elif score_name == "roc_auc":
            from drought_forecast_eval.scoring.skill import roc_auc_xr
            da = roc_auc_xr(
                obs, fcst_p50,
                threshold=cdi_threshold,
                reduce_dims=_REDUCE_DIMS,
            )
        else:
            # scores library and fallback implementations both accept reduce_dims
            da = fn(fcst_p50, obs, reduce_dims=_REDUCE_DIMS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error computing '%s' for '%s': %s", score_name, var_key, exc)
        return None

    da.attrs.setdefault("long_name", f"{var_key} {score_name}")
    return da


def _compute_quantile_score(
    score_name: str,
    obs: xr.DataArray,
    fcst_p10: xr.DataArray,
    fcst_p50: xr.DataArray,
    fcst_p90: xr.DataArray,
    ds_ref: xr.Dataset | None,
    var_key: str,
) -> xr.DataArray | None:
    """Compute a single quantile score for one variable."""
    try:
        if score_name == "pinball":
            from drought_forecast_eval.scoring.skill import pinball_loss_xr
            # Average pinball over three quantile levels
            pb10 = pinball_loss_xr(obs, fcst_p10, 0.10).mean(dim=_REDUCE_DIMS)
            pb50 = pinball_loss_xr(obs, fcst_p50, 0.50).mean(dim=_REDUCE_DIMS)
            pb90 = pinball_loss_xr(obs, fcst_p90, 0.90).mean(dim=_REDUCE_DIMS)
            da = (pb10 + pb50 + pb90) / 3.0
            da.attrs["long_name"] = f"{var_key} mean pinball loss"
        elif score_name == "interval_score":
            from drought_forecast_eval.scoring.skill import interval_score_xr
            da = interval_score_xr(obs, fcst_p10, fcst_p90).mean(dim=_REDUCE_DIMS)
            da.attrs["long_name"] = f"{var_key} interval score (80%)"
        elif score_name == "rpss":
            ref_p10_col = _find_ref_col(ds_ref, var_key, "p10")
            ref_p50_col = _find_ref_col(ds_ref, var_key, "p50")
            ref_p90_col = _find_ref_col(ds_ref, var_key, "p90")
            if None in (ref_p10_col, ref_p50_col, ref_p90_col):
                # Reference only has p50 (persistence) — use it for all quantiles
                ref_p50_col = _find_ref_col(ds_ref, var_key, "p50")
                if ref_p50_col is None:
                    return None
                ref_p = ds_ref[ref_p50_col]
                from drought_forecast_eval.scoring.skill import rpss
                da = rpss(obs, fcst_p10, fcst_p50, fcst_p90, ref_p, ref_p, ref_p,
                          reduce_dims=_REDUCE_DIMS)
            else:
                from drought_forecast_eval.scoring.skill import rpss
                da = rpss(
                    obs,
                    fcst_p10, fcst_p50, fcst_p90,
                    ds_ref[ref_p10_col], ds_ref[ref_p50_col], ds_ref[ref_p90_col],
                    reduce_dims=_REDUCE_DIMS,
                )
            da.attrs["long_name"] = f"{var_key} RPSS"
        else:
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error computing '%s' for '%s': %s", score_name, var_key, exc)
        return None

    return da


def _find_ref_col(
    ds_ref: xr.Dataset | None,
    var_key: str,
    quantile: str,
) -> str | None:
    """Find the reference forecast column for a variable/quantile combination."""
    if ds_ref is None:
        return None
    candidate = f"{var_key}_ref_{quantile}"
    if candidate in ds_ref:
        return candidate
    # Try without quantile suffix (persistence stores only _ref_p50)
    alt = f"{var_key}_ref_p50"
    if alt in ds_ref:
        return alt
    logger.debug("Reference column '%s' not found in ds_ref.", candidate)
    return None

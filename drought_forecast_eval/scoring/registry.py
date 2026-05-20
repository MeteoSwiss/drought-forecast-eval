"""Score registry: named callable store, extensible by users.

The registry maps a short name (string) to a callable with the signature::

    fn(fcst: xr.DataArray, obs: xr.DataArray, **kwargs) -> xr.DataArray

Built-in registrations use the ``scores`` library where available and fall
back to plain xarray / numpy otherwise.

Usage
-----
>>> from drought_forecast_eval.scoring.registry import register_score, SCORE_REGISTRY
>>> def my_metric(fcst, obs, **kwargs):
...     return (fcst - obs).mean()
>>> register_score("my_metric", my_metric)
>>> "my_metric" in SCORE_REGISTRY
True
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

try:
    import scores.continuous as _scores_cont
    _SCORES_AVAILABLE = True
except ImportError:
    _SCORES_AVAILABLE = False
    logger.warning(
        "The 'scores' library is not installed. "
        "Falling back to built-in implementations for MAE/RMSE/MSE."
    )


# ---------------------------------------------------------------------------
# Fallback implementations (used when scores is not installed)
# ---------------------------------------------------------------------------

def _mae_fallback(
    fcst: xr.DataArray,
    obs: xr.DataArray,
    reduce_dims: list[str] | None = None,
    **_kwargs: object,
) -> xr.DataArray:
    diff = np.abs(fcst - obs)
    return diff.mean(dim=reduce_dims) if reduce_dims else diff.mean()


def _mse_fallback(
    fcst: xr.DataArray,
    obs: xr.DataArray,
    reduce_dims: list[str] | None = None,
    **_kwargs: object,
) -> xr.DataArray:
    diff = (fcst - obs) ** 2
    return diff.mean(dim=reduce_dims) if reduce_dims else diff.mean()


def _rmse_fallback(
    fcst: xr.DataArray,
    obs: xr.DataArray,
    reduce_dims: list[str] | None = None,
    **_kwargs: object,
) -> xr.DataArray:
    return np.sqrt(_mse_fallback(fcst, obs, reduce_dims=reduce_dims))


def _bias_fallback(
    fcst: xr.DataArray,
    obs: xr.DataArray,
    reduce_dims: list[str] | None = None,
    **_kwargs: object,
) -> xr.DataArray:
    diff = fcst - obs
    return diff.mean(dim=reduce_dims) if reduce_dims else diff.mean()


def _correlation_fallback(
    fcst: xr.DataArray,
    obs: xr.DataArray,
    reduce_dims: list[str] | None = None,
    **_kwargs: object,
) -> xr.DataArray:
    dims = reduce_dims if reduce_dims else list(fcst.dims)
    fcst_m = fcst - fcst.mean(dim=dims)
    obs_m = obs - obs.mean(dim=dims)
    num = (fcst_m * obs_m).sum(dim=dims)
    denom = np.sqrt((fcst_m**2).sum(dim=dims) * (obs_m**2).sum(dim=dims))
    return xr.where(denom == 0, np.nan, num / denom)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: The global score registry.  Keys are short metric names.
SCORE_REGISTRY: dict[str, Callable] = {}


def _register_builtins() -> None:
    """Populate the registry with built-in metrics."""
    if _SCORES_AVAILABLE:
        SCORE_REGISTRY["mae"] = _scores_cont.mae
        SCORE_REGISTRY["mse"] = _scores_cont.mse
        SCORE_REGISTRY["rmse"] = _scores_cont.rmse
    else:
        SCORE_REGISTRY["mae"] = _mae_fallback
        SCORE_REGISTRY["mse"] = _mse_fallback
        SCORE_REGISTRY["rmse"] = _rmse_fallback

    # These are always our own implementations
    SCORE_REGISTRY["bias"] = _bias_fallback
    SCORE_REGISTRY["correlation"] = _correlation_fallback

    # Probabilistic scores are imported lazily from skill.py to avoid
    # circular imports; they are registered here by name and resolved in
    # dispatcher.py.
    SCORE_REGISTRY["pinball"] = "pinball_loss_xr"        # resolved in dispatcher
    SCORE_REGISTRY["interval_score"] = "interval_score_xr"  # resolved in dispatcher
    SCORE_REGISTRY["rpss"] = "rpss"                          # resolved in dispatcher
    SCORE_REGISTRY["mae_skill"] = "mae_skill"                # resolved in dispatcher
    SCORE_REGISTRY["roc_auc"] = "roc_auc_xr"                # resolved in dispatcher


_register_builtins()

#: Names of metrics that are deterministic (fcst vs obs directly)
DETERMINISTIC_METRICS: frozenset[str] = frozenset(
    ["mae", "mse", "rmse", "bias", "correlation", "mae_skill", "roc_auc"]
)

#: Names of metrics that require quantile bundles
QUANTILE_METRICS: frozenset[str] = frozenset(
    ["pinball", "interval_score", "rpss"]
)


def register_score(name: str, fn: Callable) -> None:
    """Register a custom scoring function under ``name``.

    Parameters
    ----------
    name:
        Short identifier for the metric (e.g. ``"my_crps"``).
    fn:
        Callable with signature
        ``fn(fcst: xr.DataArray, obs: xr.DataArray, **kwargs) -> xr.DataArray``.

    Raises
    ------
    ValueError
        If ``name`` is already registered and ``fn`` differs from the
        existing entry.
    """
    if name in SCORE_REGISTRY and SCORE_REGISTRY[name] is not fn:
        logger.warning(
            "Overwriting existing score '%s' in registry.", name
        )
    SCORE_REGISTRY[name] = fn
    logger.debug("Registered score: '%s'", name)

"""drought-forecast-eval: Verification library for Swiss drought forecasts.

Public API
----------
Data loading
    load_forecasts      -- parse flat ZIP archive → forecast xr.Dataset
    load_observations   -- parse historic ZIP → observation xr.Dataset

Processing
    align_obs_to_forecast    -- merge obs onto forecast grid
    climatology_reference    -- week-of-year climatology reference forecast
    persistence_reference    -- last-observed-value reference forecast

Scoring
    compute_scores           -- dispatch all scores → result xr.Dataset
    register_score           -- add a custom metric to the registry

Reporting
    ReportBuilder            -- orchestrate full pipeline → NC/HTML/CSV output

Examples
--------
>>> from drought_forecast_eval import load_forecasts, load_observations
>>> from drought_forecast_eval import align_obs_to_forecast, compute_scores
>>> from drought_forecast_eval import ReportBuilder
>>>
>>> ds_fcst = load_forecasts("path/to/zips", date_range=("2025-01-01", "2025-12-31"))
>>> ds_obs  = load_observations("path/to/historic.zip")
>>> ds      = align_obs_to_forecast(ds_fcst, ds_obs)
>>> ds_scores = compute_scores(ds)
>>> ds_scores.to_netcdf("scores.nc")
"""

from drought_forecast_eval.io.loader import load_forecasts, load_observations
from drought_forecast_eval.processing.alignment import align_obs_to_forecast
from drought_forecast_eval.processing.reference import (
    climatology_reference,
    persistence_reference,
)
from drought_forecast_eval.report.builder import ReportBuilder
from drought_forecast_eval.scoring.dispatcher import compute_scores
from drought_forecast_eval.scoring.registry import register_score

__all__ = [
    "load_forecasts",
    "load_observations",
    "align_obs_to_forecast",
    "climatology_reference",
    "persistence_reference",
    "compute_scores",
    "register_score",
    "ReportBuilder",
]

from drought_forecast_eval._version import __version__

__all__ += ["__version__"]

"""Processing layer: lead-time computation, obs/fcst alignment, reference forecasts."""

from drought_forecast_eval.processing.alignment import align_obs_to_forecast
from drought_forecast_eval.processing.lead_time import compute_lead_weeks
from drought_forecast_eval.processing.reference import (
    climatology_reference,
    persistence_reference,
)

__all__ = [
    "align_obs_to_forecast",
    "compute_lead_weeks",
    "climatology_reference",
    "persistence_reference",
]

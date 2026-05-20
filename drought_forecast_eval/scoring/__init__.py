"""Scoring layer: variable map, score registry, dispatcher, skill scores."""

from drought_forecast_eval.scoring.dispatcher import compute_scores
from drought_forecast_eval.scoring.registry import SCORE_REGISTRY, register_score
from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

__all__ = [
    "compute_scores",
    "SCORE_REGISTRY",
    "register_score",
    "VARIABLE_MAP",
]

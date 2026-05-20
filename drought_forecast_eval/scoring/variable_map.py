"""Canonical mapping from observation variables to forecast variable bundles.

Each entry in ``VARIABLE_MAP`` describes one verifiable quantity:

    obs:    name of the observation variable in the aligned dataset (``_obs`` suffix).
    fcst:   list of forecast variable names (one for deterministic, three for quantile).
    mode:   ``"deterministic"`` or ``"quantile"``.

The map is designed to be user-overridable.  To add or modify entries::

    from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP
    VARIABLE_MAP["my_var"] = {
        "obs":  "my_var_obs",
        "fcst": ["my_var_p10", "my_var_p50", "my_var_p90"],
        "mode": "quantile",
    }
"""

from __future__ import annotations

from typing import Literal, TypedDict


class VariableEntry(TypedDict):
    """Type definition for a single VARIABLE_MAP entry."""

    obs: str  # observation column name in the merged dataset
    fcst: list[str]  # forecast column name(s) in the merged dataset
    mode: Literal["deterministic", "quantile"]


#: Full variable map.  Keys are human-readable variable identifiers used
#: throughout the library (e.g. in ``compute_scores`` ``variables`` argument).
VARIABLE_MAP: dict[str, VariableEntry] = {
    # ------------------------------------------------------------------
    # Deterministic variables (only p50 available in forecast)
    # ------------------------------------------------------------------
    "cdi": {
        "obs": "cdi_obs",
        "fcst": ["cdi_p50"],
        "mode": "deterministic",
    },
    "precip_1m_index": {
        "obs": "precip_1m_index_obs",
        "fcst": ["precip_1m_index_p50"],
        "mode": "deterministic",
    },
    "precip_3m_index": {
        "obs": "precip_3m_index_obs",
        "fcst": ["precip_3m_index_p50"],
        "mode": "deterministic",
    },
    "precip_24m_index": {
        "obs": "precip_24m_index_obs",
        "fcst": ["precip_24m_index_p50"],
        "mode": "deterministic",
    },
    "hydro_index": {
        "obs": "hydro_index_obs",
        "fcst": ["hydro_index_p50"],
        "mode": "deterministic",
    },
    "soil_moisture_index": {
        "obs": "soil_moisture_index_obs",
        "fcst": ["soil_moisture_index_p50"],
        "mode": "deterministic",
    },
    # ------------------------------------------------------------------
    # Quantile variables (p10 / p50 / p90 available in forecast)
    # ------------------------------------------------------------------
    "precip_sum_1m": {
        "obs": "precip_sum_1m_obs",
        "fcst": ["precip_sum_1m_p10", "precip_sum_1m_p50", "precip_sum_1m_p90"],
        "mode": "quantile",
    },
    "precip_sum_3m": {
        "obs": "precip_sum_3m_obs",
        "fcst": ["precip_sum_3m_p10", "precip_sum_3m_p50", "precip_sum_3m_p90"],
        "mode": "quantile",
    },
    "precip_sum_6m": {
        "obs": "precip_sum_6m_obs",
        "fcst": ["precip_sum_6m_p10", "precip_sum_6m_p50", "precip_sum_6m_p90"],
        "mode": "quantile",
    },
    "precip_sum_12m": {
        "obs": "precip_sum_12m_obs",
        "fcst": ["precip_sum_12m_p10", "precip_sum_12m_p50", "precip_sum_12m_p90"],
        "mode": "quantile",
    },
    "precip_sum_24m": {
        "obs": "precip_sum_24m_obs",
        "fcst": ["precip_sum_24m_p10", "precip_sum_24m_p50", "precip_sum_24m_p90"],
        "mode": "quantile",
    },
    "spi_1m": {
        "obs": "spi_1m_obs",
        "fcst": ["spi_1m_p10", "spi_1m_p50", "spi_1m_p90"],
        "mode": "quantile",
    },
    "spi_3m": {
        "obs": "spi_3m_obs",
        "fcst": ["spi_3m_p10", "spi_3m_p50", "spi_3m_p90"],
        "mode": "quantile",
    },
    "spi_6m": {
        "obs": "spi_6m_obs",
        "fcst": ["spi_6m_p10", "spi_6m_p50", "spi_6m_p90"],
        "mode": "quantile",
    },
    "spi_12m": {
        "obs": "spi_12m_obs",
        "fcst": ["spi_12m_p10", "spi_12m_p50", "spi_12m_p90"],
        "mode": "quantile",
    },
    "spi_24m": {
        "obs": "spi_24m_obs",
        "fcst": ["spi_24m_p10", "spi_24m_p50", "spi_24m_p90"],
        "mode": "quantile",
    },
    "soil_moisture_ufc": {
        "obs": "soil_moisture_ufc_obs",
        "fcst": ["soil_moisture_ufc_p10", "soil_moisture_ufc_p50", "soil_moisture_ufc_p90"],
        "mode": "quantile",
    },
}

# Convenience groupings for the ``variables`` argument of ``compute_scores``
VARIABLE_GROUPS: dict[str, list[str]] = {
    "precipitation": [
        "precip_sum_1m",
        "precip_sum_3m",
        "precip_sum_6m",
        "precip_sum_12m",
        "precip_sum_24m",
        "spi_1m",
        "spi_3m",
        "spi_6m",
        "spi_12m",
        "spi_24m",
        "precip_1m_index",
        "precip_3m_index",
        "precip_24m_index",
    ],
    "streamflow": ["hydro_index"],
    "soil_moisture": ["soil_moisture_ufc", "soil_moisture_index"],
    "cdi": ["cdi"],
    "all": list(VARIABLE_MAP.keys()),
}

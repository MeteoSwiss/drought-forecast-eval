"""Tests for io.schema: validation, type coercion, error handling."""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

from drought_forecast_eval.io.schema import (
    SchemaError,
    validate_forecast,
    validate_observation,
)


def _minimal_forecast_row() -> dict:
    return {
        "drought_region_id": 31,
        "valid_at": "23.03.2026",
        "cdi_p50": 2.0,
        "precip_1m_index_p50": -0.5,
        "precip_3m_index_p50": -0.3,
        "precip_24m_index_p50": 0.1,
        "hydro_index_p50": -1.0,
        "soil_moisture_index_p50": 0.5,
        "precip_sum_1m_p10": 30.0,
        "precip_sum_1m_p50": 40.0,
        "precip_sum_1m_p90": 50.0,
        "precip_sum_3m_p10": 100.0,
        "precip_sum_3m_p50": 120.0,
        "precip_sum_3m_p90": 140.0,
        "precip_sum_6m_p10": 200.0,
        "precip_sum_6m_p50": 240.0,
        "precip_sum_6m_p90": 280.0,
        "precip_sum_12m_p10": 500.0,
        "precip_sum_12m_p50": 600.0,
        "precip_sum_12m_p90": 700.0,
        "precip_sum_24m_p10": 1100.0,
        "precip_sum_24m_p50": 1200.0,
        "precip_sum_24m_p90": 1300.0,
        "spi_1m_p10": -1.2,
        "spi_1m_p50": -1.0,
        "spi_1m_p90": -0.8,
        "spi_3m_p10": -0.5,
        "spi_3m_p50": -0.3,
        "spi_3m_p90": -0.1,
        "spi_6m_p10": -0.4,
        "spi_6m_p50": -0.2,
        "spi_6m_p90": 0.0,
        "spi_12m_p10": 0.1,
        "spi_12m_p50": 0.2,
        "spi_12m_p90": 0.3,
        "spi_24m_p10": 0.1,
        "spi_24m_p50": 0.15,
        "spi_24m_p90": 0.2,
        "soil_moisture_ufc_p10": 90.0,
        "soil_moisture_ufc_p50": 93.0,
        "soil_moisture_ufc_p90": 97.0,
    }


def _minimal_obs_row() -> dict:
    return {
        "drought_region_id": 31,
        "measured_at": "2026-03-19",
        "cdi": 2.0,
        "precip_1m_index": -0.5,
        "precip_3m_index": -0.3,
        "precip_24m_index": 0.1,
        "hydro_index": -1.0,
        "soil_moisture_index": 0.5,
        "precip_sum_1m": 38.0,
        "precip_sum_3m": 115.0,
        "precip_sum_6m": 235.0,
        "precip_sum_12m": 590.0,
        "precip_sum_24m": 1190.0,
        "spi_1m": -1.0,
        "spi_3m": -0.3,
        "spi_6m": -0.2,
        "spi_12m": 0.15,
        "spi_24m": 0.12,
        "soil_moisture_ufc": 92.5,
        "vhi": 0.65,
    }


class TestValidateForecast:
    def test_valid_row_passes(self):
        df = pd.DataFrame([_minimal_forecast_row()])
        result = validate_forecast(df)
        assert "valid_at" in result.columns
        assert result["valid_at"].dtype == "datetime64[ns]"

    def test_iso_date_format_accepted(self):
        row = _minimal_forecast_row()
        row["valid_at"] = "2026-03-23"
        df = pd.DataFrame([row])
        result = validate_forecast(df)
        assert pd.notna(result["valid_at"].iloc[0])

    def test_missing_required_column_raises(self):
        row = _minimal_forecast_row()
        del row["spi_1m_p50"]
        df = pd.DataFrame([row])
        with pytest.raises(SchemaError, match="Missing required columns"):
            validate_forecast(df)

    def test_extra_column_warns(self):
        row = _minimal_forecast_row()
        row["future_unknown_column"] = 99.9
        df = pd.DataFrame([row])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            validate_forecast(df)
        assert any("Unexpected columns" in str(warning.message) for warning in w)

    def test_region_id_coerced_to_int(self):
        row = _minimal_forecast_row()
        row["drought_region_id"] = "31"
        df = pd.DataFrame([row])
        result = validate_forecast(df)
        assert result["drought_region_id"].dtype == "int64"

    def test_invalid_date_raises(self):
        row = _minimal_forecast_row()
        row["valid_at"] = "not-a-date"
        df = pd.DataFrame([row])
        with pytest.raises(SchemaError, match="unparseable dates"):
            validate_forecast(df)


class TestValidateObservation:
    def test_valid_row_passes(self):
        df = pd.DataFrame([_minimal_obs_row()])
        result = validate_observation(df)
        assert result["measured_at"].dtype == "datetime64[ns]"

    def test_missing_required_column_raises(self):
        row = _minimal_obs_row()
        del row["spi_1m"]
        df = pd.DataFrame([row])
        with pytest.raises(SchemaError, match="Missing required columns"):
            validate_observation(df)

    def test_iso_date_format_accepted(self):
        row = _minimal_obs_row()
        row["measured_at"] = "2026-03-19"
        df = pd.DataFrame([row])
        result = validate_observation(df)
        assert pd.notna(result["measured_at"].iloc[0])

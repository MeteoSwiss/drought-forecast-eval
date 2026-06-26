"""Tests for processing.alignment and processing.lead_time."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from drought_forecast_eval.processing.lead_time import compute_lead_weeks


class TestComputeLeadWeeks:
    def test_week_0_same_monday(self):
        frt = pd.Timestamp("2026-03-24")  # Tuesday
        valid_at = pd.Series([pd.Timestamp("2026-03-23")])  # Monday of same week
        result = compute_lead_weeks(valid_at, frt)
        assert result.iloc[0] == 0

    def test_week_1(self):
        frt = pd.Timestamp("2026-03-24")
        valid_at = pd.Series([pd.Timestamp("2026-03-30")])
        result = compute_lead_weeks(valid_at, frt)
        assert result.iloc[0] == 1

    def test_week_2(self):
        frt = pd.Timestamp("2026-03-24")
        valid_at = pd.Series([pd.Timestamp("2026-04-06")])
        result = compute_lead_weeks(valid_at, frt)
        assert result.iloc[0] == 2

    def test_week_3(self):
        frt = pd.Timestamp("2026-03-24")
        valid_at = pd.Series([pd.Timestamp("2026-04-13")])
        result = compute_lead_weeks(valid_at, frt)
        assert result.iloc[0] == 3

    def test_issued_on_monday(self):
        frt = pd.Timestamp("2026-03-23")  # Monday itself
        valid_at = pd.Series([pd.Timestamp("2026-03-23")])
        result = compute_lead_weeks(valid_at, frt)
        assert result.iloc[0] == 0

    def test_series_length_preserved(self):
        frt = pd.Timestamp("2026-03-24")
        valid_at = pd.Series([
            pd.Timestamp("2026-03-23"),
            pd.Timestamp("2026-03-30"),
            pd.Timestamp("2026-04-06"),
            pd.Timestamp("2026-04-13"),
        ])
        result = compute_lead_weeks(valid_at, frt)
        assert len(result) == 4
        assert result.tolist() == [0, 1, 2, 3]


class TestAlignObsToForecast:
    def test_returns_dataset(self, ds_merged):
        assert isinstance(ds_merged, xr.Dataset)

    def test_obs_columns_appended(self, ds_merged):
        obs_cols = [v for v in ds_merged.data_vars if v.endswith("_obs")]
        assert len(obs_cols) > 0, "No _obs columns found in merged dataset"

    def test_cdi_obs_present(self, ds_merged):
        assert "cdi_obs" in ds_merged

    def test_spi_1m_obs_present(self, ds_merged):
        assert "spi_1m_obs" in ds_merged

    def test_dimensions_unchanged(self, ds_fcst, ds_merged):
        """Merging should not add new dimensions."""
        for dim in ["forecast_reference_time", "drought_region_id", "lead_week"]:
            assert dim in ds_merged.dims

    def test_missing_valid_at_raises(self, ds_fcst, ds_obs_combined):
        from drought_forecast_eval.processing.alignment import align_obs_to_forecast
        # Drop the valid_at coordinate to trigger the error
        ds_no_valid_at = ds_fcst.drop_vars("valid_at")
        with pytest.raises(ValueError, match="valid_at"):
            align_obs_to_forecast(ds_no_valid_at, ds_obs_combined)

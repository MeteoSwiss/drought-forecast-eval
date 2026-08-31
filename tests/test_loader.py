"""Tests for io.loader: load_forecasts() and load_observations()."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ARCHIVE_DIR = FIXTURE_DIR
HISTORIC_ZIP = FIXTURE_DIR / "trockenheitsdaten-numerisch_historic.csv.zip"


class TestLoadForecasts:
    def test_returns_dataset(self, ds_fcst):
        assert isinstance(ds_fcst, xr.Dataset)

    def test_expected_dimensions(self, ds_fcst):
        assert "forecast_reference_time" in ds_fcst.dims
        assert "drought_region_id" in ds_fcst.dims
        assert "lead_week" in ds_fcst.dims

    def test_lead_week_values(self, ds_fcst):
        lead_weeks = ds_fcst["lead_week"].values.tolist()
        assert set(lead_weeks).issubset({-1, 0, 1, 2, 3, 4}), (
            f"Unexpected lead_week values: {lead_weeks}"
        )

    def test_spi_columns_present(self, ds_fcst):
        for col in ["spi_1m_p10", "spi_1m_p50", "spi_1m_p90"]:
            assert col in ds_fcst, f"Expected column '{col}' in forecast dataset"

    def test_cdi_p50_present(self, ds_fcst):
        assert "cdi_p50" in ds_fcst

    def test_valid_at_coordinate(self, ds_fcst):
        assert "valid_at" in ds_fcst.coords

    def test_region_id_dtype(self, ds_fcst):
        assert ds_fcst["drought_region_id"].dtype in (np.dtype("int64"), np.dtype("int32"))

    def test_region_filter(self):
        from drought_forecast_eval.io.loader import load_forecasts

        ds = load_forecasts(ARCHIVE_DIR, region_ids=[1, 5])
        assert set(ds["drought_region_id"].values).issubset({1, 5})

    def test_date_range_filter(self):
        from drought_forecast_eval.io.loader import load_forecasts

        ds = load_forecasts(ARCHIVE_DIR, date_range=("2026-03-17", "2026-03-24"))
        assert len(ds["forecast_reference_time"]) >= 1

    def test_empty_archive_raises(self, tmp_path):
        from drought_forecast_eval.io.loader import load_forecasts

        with pytest.raises(RuntimeError, match="No valid ZIP files found"):
            load_forecasts(tmp_path)

    def test_missing_dir_raises(self):
        from drought_forecast_eval.io.loader import load_forecasts

        with pytest.raises(FileNotFoundError):
            load_forecasts("/path/does/not/exist")


class TestLoadObservations:
    def test_returns_dataset(self, ds_obs):
        assert isinstance(ds_obs, xr.Dataset)

    def test_expected_dimensions(self, ds_obs):
        assert "drought_region_id" in ds_obs.dims
        assert "valid_at" in ds_obs.dims

    def test_spi_columns_present(self, ds_obs):
        for col in ["spi_1m", "spi_6m", "spi_24m"]:
            assert col in ds_obs, f"Expected column '{col}' in observation dataset"

    def test_cdi_present(self, ds_obs):
        assert "cdi" in ds_obs

    def test_vhi_present(self, ds_obs):
        assert "vhi" in ds_obs

    def test_no_all_nan_columns(self, ds_obs):
        for var in ds_obs.data_vars:
            assert not np.all(np.isnan(ds_obs[var].values)), f"Variable '{var}' is entirely NaN"

    def test_missing_file_raises(self):
        from drought_forecast_eval.io.loader import load_observations

        with pytest.raises(FileNotFoundError):
            load_observations("/nonexistent/file.zip")


class TestLoadObservationsCombined:
    def test_returns_dataset(self, ds_obs_combined):
        assert isinstance(ds_obs_combined, xr.Dataset)

    def test_expected_dimensions(self, ds_obs_combined):
        assert "drought_region_id" in ds_obs_combined.dims
        assert "valid_at" in ds_obs_combined.dims

    def test_extends_beyond_historic_cutoff(self, ds_obs_combined, ds_obs):
        """Combined dataset must contain dates that the historic-only dataset lacks."""
        hist_max = ds_obs["valid_at"].values.max()
        combined_max = ds_obs_combined["valid_at"].values.max()
        assert combined_max > hist_max, (
            f"Combined max ({combined_max}) should exceed historic max ({hist_max})"
        )

    def test_historic_rows_preserved(self, ds_obs_combined, ds_obs):
        """All dates present in the historic dataset must still be present."""
        import numpy as np

        hist_dates = set(ds_obs["valid_at"].values.tolist())
        combined_dates = set(ds_obs_combined["valid_at"].values.tolist())
        assert hist_dates.issubset(combined_dates), (
            f"{len(hist_dates - combined_dates)} historic dates missing from combined dataset"
        )

    def test_no_duplicate_dates_per_region(self, ds_obs_combined):
        """After merging, each (region, date) pair must appear exactly once."""
        df = ds_obs_combined.to_dataframe().reset_index()
        dupes = df.duplicated(subset=["drought_region_id", "valid_at"]).sum()
        assert dupes == 0, f"{dupes} duplicate (region, date) pairs found"

    def test_missing_historic_raises(self, tmp_path):
        from drought_forecast_eval.io.loader import load_observations_combined

        with pytest.raises(FileNotFoundError, match="Historic archive not found"):
            load_observations_combined("/nonexistent/historic.zip", tmp_path)

    def test_missing_archive_dir_raises(self):
        from drought_forecast_eval.io.loader import load_observations_combined

        with pytest.raises(FileNotFoundError, match="Archive directory not found"):
            load_observations_combined(HISTORIC_ZIP, "/nonexistent/dir")

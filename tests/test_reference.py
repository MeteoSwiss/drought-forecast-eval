"""Tests for processing.reference: climatology and persistence reference forecasts."""

from __future__ import annotations

import numpy as np
import xarray as xr


class TestClimatologyReference:
    def test_returns_dataset(self, ds_clim_ref):
        assert isinstance(ds_clim_ref, xr.Dataset)

    def test_correct_dimensions(self, ds_clim_ref):
        for dim in ["forecast_reference_time", "drought_region_id", "lead_week"]:
            assert dim in ds_clim_ref.dims

    def test_p10_p50_p90_variables_exist(self, ds_clim_ref):
        for var in ds_clim_ref.data_vars:
            assert any(var.endswith(f"_ref_{q}") for q in ("p10", "p50", "p90")), (
                f"Unexpected variable name: {var}"
            )

    def test_spi_1m_ref_p50_present(self, ds_clim_ref):
        assert "spi_1m_ref_p50" in ds_clim_ref

    def test_p10_le_p50_le_p90(self, ds_clim_ref):
        """p10 ≤ p50 ≤ p90 for all non-NaN cells."""
        for base_var in ["spi_1m", "precip_sum_1m"]:
            p10_key = f"{base_var}_ref_p10"
            p50_key = f"{base_var}_ref_p50"
            p90_key = f"{base_var}_ref_p90"
            if not all(k in ds_clim_ref for k in (p10_key, p50_key, p90_key)):
                continue
            p10 = ds_clim_ref[p10_key].values
            p50 = ds_clim_ref[p50_key].values
            p90 = ds_clim_ref[p90_key].values
            valid = np.isfinite(p10) & np.isfinite(p50) & np.isfinite(p90)
            assert np.all(p10[valid] <= p50[valid] + 1e-6), f"{base_var}: p10 > p50"
            assert np.all(p50[valid] <= p90[valid] + 1e-6), f"{base_var}: p50 > p90"

    def test_reference_type_attr(self, ds_clim_ref):
        assert ds_clim_ref.attrs.get("reference_type") == "climatology"


class TestPersistenceReference:
    def test_returns_dataset(self, ds_pers_ref):
        assert isinstance(ds_pers_ref, xr.Dataset)

    def test_correct_dimensions(self, ds_pers_ref):
        for dim in ["forecast_reference_time", "drought_region_id", "lead_week"]:
            assert dim in ds_pers_ref.dims

    def test_only_p50_variables(self, ds_pers_ref):
        for var in ds_pers_ref.data_vars:
            assert var.endswith("_ref_p50"), f"Expected only _ref_p50 vars, got: {var}"

    def test_flat_across_leads(self, ds_pers_ref):
        """Persistence should be constant across lead_week."""
        for var in list(ds_pers_ref.data_vars)[:3]:
            da = ds_pers_ref[var]
            if "lead_week" not in da.dims or len(da["lead_week"]) < 2:
                continue
            # All lead weeks should have the same value per (frt, region)
            diff = da.diff(dim="lead_week")
            valid = np.isfinite(diff.values)
            assert np.allclose(diff.values[valid], 0, atol=1e-9), (
                f"Persistence reference '{var}' is not flat across lead weeks"
            )

    def test_reference_type_attr(self, ds_pers_ref):
        assert ds_pers_ref.attrs.get("reference_type") == "persistence"

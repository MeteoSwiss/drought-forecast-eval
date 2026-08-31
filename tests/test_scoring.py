"""Tests for scoring layer: variable_map, registry, skill scores, dispatcher."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr


# ---------------------------------------------------------------------------
# Variable map
# ---------------------------------------------------------------------------


class TestVariableMap:
    def test_all_entries_have_required_keys(self):
        from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

        for key, entry in VARIABLE_MAP.items():
            assert "obs" in entry, f"{key}: missing 'obs'"
            assert "fcst" in entry, f"{key}: missing 'fcst'"
            assert "mode" in entry, f"{key}: missing 'mode'"

    def test_mode_values(self):
        from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

        valid_modes = {"deterministic", "quantile"}
        for key, entry in VARIABLE_MAP.items():
            assert entry["mode"] in valid_modes, f"{key}: invalid mode '{entry['mode']}'"

    def test_quantile_mode_has_three_fcst_cols(self):
        from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

        for key, entry in VARIABLE_MAP.items():
            if entry["mode"] == "quantile":
                assert len(entry["fcst"]) == 3, (
                    f"{key}: quantile mode should have 3 forecast columns"
                )

    def test_deterministic_mode_has_one_fcst_col(self):
        from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

        for key, entry in VARIABLE_MAP.items():
            if entry["mode"] == "deterministic":
                assert len(entry["fcst"]) == 1, (
                    f"{key}: deterministic mode should have 1 forecast column"
                )

    def test_cdi_present_and_deterministic(self):
        from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

        assert "cdi" in VARIABLE_MAP
        assert VARIABLE_MAP["cdi"]["mode"] == "deterministic"

    def test_spi_1m_present_and_quantile(self):
        from drought_forecast_eval.scoring.variable_map import VARIABLE_MAP

        assert "spi_1m" in VARIABLE_MAP
        assert VARIABLE_MAP["spi_1m"]["mode"] == "quantile"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_mae_registered(self):
        from drought_forecast_eval.scoring.registry import SCORE_REGISTRY

        assert "mae" in SCORE_REGISTRY

    def test_rmse_registered(self):
        from drought_forecast_eval.scoring.registry import SCORE_REGISTRY

        assert "rmse" in SCORE_REGISTRY

    def test_register_custom_score(self):
        from drought_forecast_eval.scoring.registry import register_score, SCORE_REGISTRY

        def dummy_score(fcst, obs, **kw):
            return (fcst - obs).mean()

        register_score("dummy_test_score", dummy_score)
        assert "dummy_test_score" in SCORE_REGISTRY
        assert SCORE_REGISTRY["dummy_test_score"] is dummy_score


# ---------------------------------------------------------------------------
# Skill score functions
# ---------------------------------------------------------------------------


class TestSkillFunctions:
    def _make_perfect_forecast(self):
        obs = xr.DataArray(
            np.array([[1.0, 2.0, 3.0], [1.5, 2.5, 3.5]]),
            dims=["forecast_reference_time", "drought_region_id"],
        )
        return obs, obs.copy()  # perfect forecast = obs

    def _make_bad_forecast(self):
        obs = xr.DataArray(
            np.array([[1.0, 2.0, 3.0], [1.5, 2.5, 3.5]]),
            dims=["forecast_reference_time", "drought_region_id"],
        )
        fcst = obs + 10  # large constant error
        return obs, fcst

    def test_mae_skill_perfect_forecast(self):
        from drought_forecast_eval.scoring.skill import mae_skill

        obs, perfect = self._make_perfect_forecast()
        ref = obs + 1.0  # reference has constant error = 1
        skill = mae_skill(perfect, obs, ref, reduce_dims=["forecast_reference_time"])
        assert float(skill.mean()) == pytest.approx(1.0, abs=1e-6)

    def test_mae_skill_reference_forecast(self):
        from drought_forecast_eval.scoring.skill import mae_skill

        obs, _ = self._make_perfect_forecast()
        ref = obs + 1.0
        # Forecast equal to reference → skill = 0
        skill = mae_skill(ref, obs, ref, reduce_dims=["forecast_reference_time"])
        assert float(skill.mean()) == pytest.approx(0.0, abs=1e-6)

    def test_pinball_loss_median_zero_for_perfect(self):
        from drought_forecast_eval.scoring.skill import pinball_loss_xr

        obs = xr.DataArray([1.0, 2.0, 3.0])
        loss = pinball_loss_xr(obs, obs, quantile=0.5)
        assert float(loss.sum()) == pytest.approx(0.0, abs=1e-9)

    def test_pinball_loss_positive(self):
        from drought_forecast_eval.scoring.skill import pinball_loss_xr

        obs = xr.DataArray([1.0, 2.0, 3.0])
        fcst = xr.DataArray([0.5, 1.5, 2.5])  # underforecast
        loss = pinball_loss_xr(obs, fcst, quantile=0.5)
        assert float(loss.min()) >= 0.0

    def test_interval_score_positive(self):
        from drought_forecast_eval.scoring.skill import interval_score_xr

        obs = xr.DataArray([1.0, 2.0, 3.0])
        lower = xr.DataArray([0.5, 1.5, 2.5])
        upper = xr.DataArray([1.5, 2.5, 3.5])
        score = interval_score_xr(obs, lower, upper)
        assert float(score.min()) >= 0.0

    def test_interval_score_penalty_for_miss(self):
        from drought_forecast_eval.scoring.skill import interval_score_xr

        obs = xr.DataArray([10.0])  # well outside interval
        lower = xr.DataArray([0.0])
        upper = xr.DataArray([1.0])
        score = interval_score_xr(obs, lower, upper, alpha=0.2)
        # Width=1, penalty = (2/0.2)*(10-1) = 90 → total ≥ 91
        assert float(score.values.flat[0]) > 90.0

    def test_roc_auc_perfect_discrimination(self):
        from drought_forecast_eval.scoring.skill import roc_auc_xr

        obs = xr.DataArray(
            [1.0, 1.0, 3.0, 3.0],
            dims=["forecast_reference_time"],
        )
        fcst_p50 = xr.DataArray(
            [0.5, 0.5, 3.5, 3.5],
            dims=["forecast_reference_time"],
        )
        auc = roc_auc_xr(obs, fcst_p50, threshold=2.0, reduce_dims=["forecast_reference_time"])
        assert float(auc) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TestDispatcher:
    def test_returns_dataset(self, ds_scores):
        assert isinstance(ds_scores, xr.Dataset)

    def test_has_lead_week_dimension(self, ds_scores):
        assert "lead_week" in ds_scores.dims

    def test_has_region_dimension(self, ds_scores):
        assert "drought_region_id" in ds_scores.dims

    def test_mae_variables_present(self, ds_scores):
        mae_vars = [v for v in ds_scores.data_vars if v.endswith("_mae")]
        assert len(mae_vars) > 0, "No MAE variables found in scores dataset"

    def test_no_all_nan_score(self, ds_scores):
        for var in ds_scores.data_vars:
            vals = ds_scores[var].values
            finite = np.isfinite(vals)
            assert finite.any(), f"Score variable '{var}' is entirely NaN"

    def test_cdi_scored(self, ds_scores):
        assert "cdi_mae" in ds_scores, "CDI MAE should be computed"

    def test_spi_1m_scored(self, ds_scores):
        assert "spi_1m_mae" in ds_scores

    def test_custom_variable_map(self, ds_merged, ds_clim_ref):
        from drought_forecast_eval.scoring.dispatcher import compute_scores

        custom_map = {
            "spi_1m": {
                "obs": "spi_1m_obs",
                "fcst": ["spi_1m_p10", "spi_1m_p50", "spi_1m_p90"],
                "mode": "quantile",
            }
        }
        ds = compute_scores(
            ds_merged,
            variables=["spi_1m"],
            scores=["mae"],
            variable_map=custom_map,
        )
        assert "spi_1m_mae" in ds

    def test_netcdf_output(self, ds_merged, ds_clim_ref, tmp_path):
        from drought_forecast_eval.scoring.dispatcher import compute_scores

        out = tmp_path / "scores.nc"
        compute_scores(
            ds_merged,
            variables=["cdi"],
            scores=["mae"],
            output_path=out,
        )
        assert out.exists()
        ds_loaded = xr.open_dataset(out)
        assert "cdi_mae" in ds_loaded

    def test_with_rpss(self, ds_merged, ds_clim_ref):
        from drought_forecast_eval.scoring.dispatcher import compute_scores

        ds = compute_scores(
            ds_merged,
            variables=["spi_1m"],
            scores=["rpss"],
            ds_ref=ds_clim_ref,
        )
        assert "spi_1m_rpss" in ds

    def test_missing_variables_skipped_gracefully(self, ds_merged):
        from drought_forecast_eval.scoring.dispatcher import compute_scores

        # spi_999m does not exist in the dataset
        custom_map = {
            "spi_999m": {
                "obs": "spi_999m_obs",
                "fcst": ["spi_999m_p50"],
                "mode": "deterministic",
            }
        }
        with pytest.raises(ValueError, match="No scores could be computed"):
            compute_scores(ds_merged, variables=["spi_999m"], variable_map=custom_map)

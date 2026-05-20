"""Tests for visualization layer."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest


class TestSkillCurves:
    def test_returns_figure(self, ds_scores):
        from drought_forecast_eval.visualization.skill_curves import plot_skill_vs_lead
        mae_vars = [v.replace("_mae", "") for v in ds_scores.data_vars if v.endswith("_mae")][:3]
        fig = plot_skill_vs_lead(ds_scores, mae_vars, score="mae")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_figure_has_axes(self, ds_scores):
        from drought_forecast_eval.visualization.skill_curves import plot_skill_vs_lead
        mae_vars = [v.replace("_mae", "") for v in ds_scores.data_vars if v.endswith("_mae")][:2]
        fig = plot_skill_vs_lead(ds_scores, mae_vars, score="mae")
        assert len(fig.axes) > 0
        plt.close(fig)

    def test_comparison_mode(self, ds_scores):
        from drought_forecast_eval.visualization.skill_curves import plot_skill_vs_lead
        mae_vars = [v.replace("_mae", "") for v in ds_scores.data_vars if v.endswith("_mae")][:2]
        fig = plot_skill_vs_lead(
            ds_scores, mae_vars, score="mae",
            ds_scores_b=ds_scores,
            label_a="Run A", label_b="Run B",
        )
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_unknown_score_warns_but_does_not_crash(self, ds_scores):
        from drought_forecast_eval.visualization.skill_curves import plot_skill_vs_lead
        fig = plot_skill_vs_lead(ds_scores, ["spi_1m"], score="nonexistent_score_xyz")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)


class TestRegionMapFallback:
    """Test the bar-chart fallback (no shapefile required)."""

    def test_returns_figure_without_shapefile(self, ds_scores):
        from drought_forecast_eval.visualization.region_map import plot_region_map
        first_var = list(ds_scores.data_vars)[0]
        fig = plot_region_map(ds_scores, first_var, shapefile_path=None)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_raises_on_missing_variable(self, ds_scores):
        from drought_forecast_eval.visualization.region_map import plot_region_map
        with pytest.raises(ValueError, match="not found"):
            plot_region_map(ds_scores, "nonexistent_variable_xyz")


class TestExperimentComparison:
    def test_returns_figure(self, ds_scores):
        from drought_forecast_eval.visualization.experiment_comparison import plot_experiment_diff
        mae_vars = [v.replace("_mae", "") for v in ds_scores.data_vars if v.endswith("_mae")][:2]
        fig = plot_experiment_diff(ds_scores, ds_scores, mae_vars, score="mae")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_handles_missing_variable_gracefully(self, ds_scores):
        from drought_forecast_eval.visualization.experiment_comparison import plot_experiment_diff
        fig = plot_experiment_diff(ds_scores, ds_scores, ["nonexistent_var_xyz"], score="mae")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

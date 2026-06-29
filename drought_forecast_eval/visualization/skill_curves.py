"""Skill-score-vs-lead-week plots.

``plot_skill_vs_lead``
    Plots one or more score variables from a scores Dataset on a single axes,
    with lead_week on the x-axis.  Supports:

    * Regional aggregation (mean ± std shading across regions).
    * Multiple variables overlaid on the same axes.
    * Optional reference line at zero skill.
    * Comparison of two experiments (A vs B) via the ``ds_scores_b`` argument.
"""

from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

# Colorblind-friendly palette (Paul Tol's bright)
_PALETTE = [
    "#4477AA",
    "#EE6677",
    "#228833",
    "#CCBB44",
    "#66CCEE",
    "#AA3377",
    "#BBBBBB",
    "#000000",
]

_LEAD_LABELS = {0: "Week 0\n(current)", 1: "Week 1", 2: "Week 2", 3: "Week 3"}


def plot_skill_vs_lead(
    ds_scores: xr.Dataset,
    variables: list[str],
    score: str = "mae",
    ds_scores_b: xr.Dataset | None = None,
    label_a: str = "Forecast",
    label_b: str = "Reference",
    aggregate_regions: bool = True,
    show_shading: bool = True,
    zero_line: bool = True,
    title: str | None = None,
    ax: plt.Axes | None = None,
    figsize: tuple[float, float] = (8, 5),
) -> plt.Figure:
    """Plot score vs. lead week for multiple variables.

    Parameters
    ----------
    ds_scores:
        Scores dataset with dimensions ``(lead_week, drought_region_id)``.
    variables:
        List of variable keys (e.g. ``["spi_1m", "spi_6m"]``).
        The function looks for ``{variable}_{score}`` in the dataset.
    score:
        Metric name suffix (e.g. ``"mae"``, ``"rpss"``).
    ds_scores_b:
        Optional second scores dataset for experiment comparison.
    label_a, label_b:
        Legend labels for the two experiments.
    aggregate_regions:
        If True, average over ``drought_region_id`` before plotting; show
        shading as ±1 std across regions.
    show_shading:
        Show ±1 std shading (only when ``aggregate_regions=True``).
    zero_line:
        Draw a horizontal dashed line at y=0.
    title:
        Figure title.  Auto-generated if ``None``.
    ax:
        Existing axes to draw on.  A new figure is created if ``None``.
    figsize:
        Figure size in inches.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        _fig = ax.get_figure()
        assert isinstance(_fig, plt.Figure)
        fig = _fig

    lead_weeks = ds_scores["lead_week"].values if "lead_week" in ds_scores.coords else np.arange(4)

    for i, var_key in enumerate(variables):
        col = f"{var_key}_{score}"
        color = _PALETTE[i % len(_PALETTE)]

        for ds, label_suffix, linestyle in [
            (ds_scores, label_a, "-"),
            (ds_scores_b, label_b, "--"),
        ]:
            if ds is None:
                continue
            if col not in ds:
                logger.warning("'%s' not found in scores dataset — skipping.", col)
                continue

            da = ds[col]

            if aggregate_regions and "drought_region_id" in da.dims:
                mean = da.mean(dim="drought_region_id")
                std = da.std(dim="drought_region_id")
                y = mean.values
                y_err = std.values
            else:
                y = da.values
                y_err = None

            x = np.arange(len(lead_weeks))
            plot_label = f"{var_key}" if ds_scores_b is None else f"{var_key} ({label_suffix})"
            ls = linestyle if ds_scores_b is not None else "-"
            ax.plot(x, y, marker="o", color=color, linestyle=ls, label=plot_label, linewidth=2)

            if show_shading and y_err is not None and aggregate_regions:
                ax.fill_between(x, y - y_err, y + y_err, color=color, alpha=0.15)

    if zero_line:
        ax.axhline(0, color="black", linestyle=":", linewidth=0.8, alpha=0.6)

    # Axes formatting
    ax.set_xticks(np.arange(len(lead_weeks)))
    ax.set_xticklabels([_LEAD_LABELS.get(int(lw), f"Week {lw}") for lw in lead_weeks])
    ax.set_xlabel("Lead time")
    ax.set_ylabel(score.upper())
    ax.set_title(title or f"{score.upper()} by lead week")
    ax.legend(fontsize=9, framealpha=0.7)
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig


def plot_forecast_plume(
    ds_merged: xr.Dataset,
    ds_ref_clim: xr.Dataset,
    ds_ref_pers: xr.Dataset,
    var: str,
    rid: int,
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, np.ndarray]:
    """Plot forecast plume for a given variable and region.

    Parameters
    ----------
    ds_merged:
        Merged dataset containing forecast and observation data.
    ds_ref_clim:
        Reference climatology dataset.
    ds_ref_pers:
        Reference persistence dataset.
    var:
        Variable name (e.g., "spi_1m").
    rid:
        Drought region ID.
    ax:
        Matplotlib Axes object to plot on. If None, a new figure and axes are
        created.

    Returns
    -------
    tuple[matplotlib.figure.Figure, numpy.ndarray]
        A tuple of (fig, axes) where fig is the matplotlib Figure and axes is
        an array of Axes objects, one per lead week.

    """
    n_lead_weeks = ds_merged.sizes["lead_week"]

    fig, axes = plt.subplots(nrows=4, ncols=1, figsize=(12, 16))
    axes = axes.flatten()

    d_style = "steps-mid"

    for lw in range(n_lead_weeks):
        ax = axes[lw]
        series_p10 = ds_merged.isel(drought_region_id=rid, lead_week=lw)[f"{var}_p10"]
        series_p50 = ds_merged.isel(drought_region_id=rid, lead_week=lw)[f"{var}_p50"]
        series_p90 = ds_merged.isel(drought_region_id=rid, lead_week=lw)[f"{var}_p90"]
        series_obs = ds_merged.isel(drought_region_id=rid, lead_week=lw)[f"{var}_obs"]

        series_ref_clim = ds_ref_clim.isel(drought_region_id=rid, lead_week=lw)[f"{var}_ref_p50"]
        # series_ref_pers = ds_ref_pers.isel(drought_region_id=rid, lead_week=lw)[f"{var}_ref_p50"]

        x = series_p50["forecast_reference_time"].values
        ax.fill_between(  # type: ignore[call-arg]
            x, series_p10.values, series_p90.values, color="red", alpha=0.2, label="p10-p90 plume"
        )
        series_p50.plot(  # type: ignore[call-arg]
            x="forecast_reference_time", ax=ax, color="red", label="p50", drawstyle=d_style
        )
        series_obs.plot(  # type: ignore[call-arg]
            x="forecast_reference_time", ax=ax, color="green", label="obs", drawstyle=d_style
        )
        series_ref_clim.plot(  # type: ignore[call-arg]
            x="forecast_reference_time", ax=ax, color="blue", label="clim", drawstyle=d_style
        )
        ax.legend()
        ax.set_title(f"{var} forecast plume for region {rid}, lead week {lw}")
        ax.set_ylabel(var)

    for lw in range(n_lead_weeks, len(axes)):
        axes[lw].set_visible(False)
    plt.tight_layout()
    plt.show()

    return fig, axes

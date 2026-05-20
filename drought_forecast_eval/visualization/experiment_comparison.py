"""Experiment comparison visualizations.

``plot_experiment_diff``
    Side-by-side or difference plot comparing two score datasets:
    e.g. period A vs period B, or data source A vs data source B.

    Produces a figure with three columns per variable:
    [experiment A | experiment B | B − A difference]
"""

from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

_PALETTE_A = "#4477AA"
_PALETTE_B = "#EE6677"
_PALETTE_DIFF = "#228833"
_LEAD_LABELS = {0: "Wk0", 1: "Wk1", 2: "Wk2", 3: "Wk3"}


def plot_experiment_diff(
    ds_scores_a: xr.Dataset,
    ds_scores_b: xr.Dataset,
    variables: list[str],
    score: str = "mae",
    label_a: str = "Experiment A",
    label_b: str = "Experiment B",
    aggregate_regions: bool = True,
    figsize: tuple[float, float] | None = None,
    title: str | None = None,
) -> plt.Figure:
    """Compare two score datasets side by side with a difference panel.

    Parameters
    ----------
    ds_scores_a:
        First (baseline) scores dataset.
    ds_scores_b:
        Second (comparison) scores dataset.
    variables:
        Variable keys to compare (e.g. ``["spi_1m", "cdi"]``).
    score:
        Score metric name suffix (e.g. ``"mae"``, ``"rpss"``).
    label_a, label_b:
        Legend / axis labels for the two experiments.
    aggregate_regions:
        Average over ``drought_region_id`` before plotting.
    figsize:
        Figure size.  Auto-sized based on number of variables if ``None``.
    title:
        Figure suptitle.

    Returns
    -------
    matplotlib.figure.Figure
    """
    n_vars = len(variables)
    if figsize is None:
        figsize = (14, 3.5 * n_vars)

    fig, axes = plt.subplots(n_vars, 3, figsize=figsize, squeeze=False)

    for row, var_key in enumerate(variables):
        col_name = f"{var_key}_{score}"
        ax_a, ax_b, ax_diff = axes[row]

        for ax, ds, label, color in [
            (ax_a, ds_scores_a, label_a, _PALETTE_A),
            (ax_b, ds_scores_b, label_b, _PALETTE_B),
        ]:
            if col_name not in ds:
                ax.text(0.5, 0.5, f"'{col_name}'\nnot found",
                        ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{var_key}\n{label}")
                continue

            da = ds[col_name]
            _plot_lead_line(ax, da, aggregate_regions, color, label)
            ax.set_title(f"{var_key} — {label}")
            ax.set_xlabel("Lead week")
            ax.set_ylabel(score.upper())
            ax.grid(True, linestyle="--", alpha=0.4)

        # Difference panel (B − A)
        if col_name in ds_scores_a and col_name in ds_scores_b:
            diff = ds_scores_b[col_name] - ds_scores_a[col_name]
            _plot_lead_line(ax_diff, diff, aggregate_regions, _PALETTE_DIFF, f"{label_b} − {label_a}")
            ax_diff.axhline(0, color="black", linestyle=":", linewidth=0.8)
            ax_diff.set_title(f"{var_key} — Difference (B−A)")
            ax_diff.set_xlabel("Lead week")
            ax_diff.set_ylabel(f"Δ {score.upper()}")
            ax_diff.grid(True, linestyle="--", alpha=0.4)
        else:
            ax_diff.text(0.5, 0.5, "Cannot compute\ndifference",
                         ha="center", va="center", transform=ax_diff.transAxes)

    fig.suptitle(
        title or f"Experiment comparison — {score.upper()}",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plot_lead_line(
    ax: plt.Axes,
    da: xr.DataArray,
    aggregate_regions: bool,
    color: str,
    label: str,
) -> None:
    """Plot a lead-time line on ``ax``."""
    if aggregate_regions and "drought_region_id" in da.dims:
        mean = da.mean(dim="drought_region_id").values
        std = da.std(dim="drought_region_id").values
    else:
        mean = da.values
        std = None

    lead_vals = da["lead_week"].values if "lead_week" in da.coords else np.arange(len(mean))
    x = np.arange(len(lead_vals))

    ax.plot(x, mean, marker="o", color=color, label=label, linewidth=2)
    if std is not None and aggregate_regions:
        ax.fill_between(x, mean - std, mean + std, color=color, alpha=0.15)

    ax.set_xticks(x)
    ax.set_xticklabels([_LEAD_LABELS.get(int(lw), str(lw)) for lw in lead_vals])
    ax.legend(fontsize=8)

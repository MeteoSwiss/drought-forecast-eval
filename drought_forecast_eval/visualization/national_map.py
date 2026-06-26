"""National-level score visualization for entire Switzerland.

``plot_national_map``
    Creates a 4-panel figure (one panel per lead week) showing the national
    average score as a simplified representation (using Switzerland's full
    geographic extent if shapefile is available, or a simple bar chart).
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

_LEAD_LABELS = {0: "Week 0 (current)", 1: "Week 1", 2: "Week 2", 3: "Week 3"}


def plot_national_map(
    ds_scores: xr.Dataset,
    score_variable: str,
    shapefile_path: str | Path | None = None,
    lead_weeks: list[int] | None = None,
    cmap: str = "RdYlGn",
    vmin: float | None = None,
    vmax: float | None = None,
    title: str | None = None,
    figsize: tuple[float, float] = (14, 5),
) -> plt.Figure:
    """Plot 4-panel visualization of national-level (averaged) score per lead week.

    Creates one panel per lead week, showing the national average score.
    If a shapefile is available, displays as unified choropleth; otherwise
    uses a bar-chart representation.

    Parameters
    ----------
    ds_scores:
        Scores dataset with dimensions ``(lead_week, drought_region_id)``.
    score_variable:
        Name of the score variable to plot (e.g. ``"spi_1m_mae"``).
    shapefile_path:
        Path to the ``.shp`` / ``.geojson`` file of Switzerland regions.
        If provided and geopandas is available, uses choropleth;
        otherwise falls back to bar chart.
    lead_weeks:
        Subset of lead weeks to plot. Defaults to ``[0, 1, 2, 3]``.
    cmap:
        Matplotlib colormap name.
    vmin, vmax:
        Colour scale limits. If ``None``, derived from the data.
    title:
        Figure suptitle.
    figsize:
        Figure size in inches.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if lead_weeks is None:
        lead_weeks = [0, 1, 2, 3]

    if score_variable not in ds_scores:
        raise ValueError(
            f"'{score_variable}' not found in ds_scores. Available: {list(ds_scores.data_vars)}"
        )

    da = ds_scores[score_variable]

    # Aggregate over regions to get national average
    if "drought_region_id" in da.dims:
        da_national = da.mean(dim="drought_region_id")
    else:
        da_national = da

    # Try geo path for choropleth
    geo_ok = _try_geopandas(shapefile_path)
    if geo_ok:
        return _plot_national_choropleth(
            da_national=da_national,
            shapefile_path=Path(shapefile_path),  # type: ignore[arg-type]
            lead_weeks=lead_weeks,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            title=title or f"{score_variable} (National)",
            figsize=figsize,
        )
    else:
        logger.warning(
            "Falling back to bar chart: shapefile not available or geopandas not installed."
        )
        return _plot_national_bars(
            da_national=da_national,
            lead_weeks=lead_weeks,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            title=title or f"{score_variable} (National)",
            figsize=figsize,
        )


# ---------------------------------------------------------------------------
# Choropleth (geopandas path)
# ---------------------------------------------------------------------------


def _try_geopandas(shapefile_path: str | Path | None) -> bool:
    """Return True if geopandas is available and the shapefile exists."""
    if shapefile_path is None:
        return False
    try:
        import geopandas  # noqa: F401
    except ImportError:
        return False
    return Path(shapefile_path).exists()


def _plot_national_choropleth(
    da_national: xr.DataArray,
    shapefile_path: Path,
    lead_weeks: list[int],
    cmap: str,
    vmin: float | None,
    vmax: float | None,
    title: str,
    figsize: tuple[float, float],
) -> plt.Figure:
    """Plot national average as a unified color across entire Switzerland."""
    import geopandas as gpd

    gdf = gpd.read_file(shapefile_path)

    n_panels = len(lead_weeks)
    ncols = min(n_panels, 4)
    nrows = int(np.ceil(n_panels / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False)

    # Determine colour scale
    if vmin is None or vmax is None:
        all_vals = da_national.values[np.isfinite(da_national.values)]
        _vmin = float(all_vals.min()) if len(all_vals) else 0.0
        _vmax = float(all_vals.max()) if len(all_vals) else 1.0
    else:
        _vmin, _vmax = vmin, vmax

    norm = mcolors.Normalize(vmin=_vmin, vmax=_vmax)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])

    for panel_idx, lw in enumerate(lead_weeks):
        row, col = divmod(panel_idx, ncols)
        ax = axes[row][col]

        if "lead_week" in da_national.dims:
            score_val = float(da_national.sel(lead_week=lw).values)
        else:
            score_val = float(da_national.values)

        # Create a temporary gdf with the national value applied to all regions
        gdf_temp = gdf.copy()
        gdf_temp["national_score"] = score_val

        gdf_temp.plot(
            column="national_score",
            cmap=cmap,
            vmin=_vmin,
            vmax=_vmax,
            ax=ax,
            edgecolor="grey",
            linewidth=0.3,
            legend=False,
        )

        ax.set_title(_LEAD_LABELS.get(lw, f"Week {lw}"), fontsize=11)
        ax.axis("off")

        # Add text annotation showing the value
        ax.text(
            0.5,
            0.05,
            f"{score_val:.3f}",
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=10,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

    # Hide unused subplots
    for panel_idx in range(len(lead_weeks), nrows * ncols):
        row, col = divmod(panel_idx, ncols)
        axes[row][col].set_visible(False)

    fig.colorbar(
        sm, ax=axes.ravel(), shrink=0.8, label=da_national.attrs.get("long_name", "score"), pad=0.02
    )
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Bar chart fallback
# ---------------------------------------------------------------------------


def _plot_national_bars(
    da_national: xr.DataArray,
    lead_weeks: list[int],
    cmap: str,
    vmin: float | None,
    vmax: float | None,
    title: str,
    figsize: tuple[float, float],
) -> plt.Figure:
    """Plot average score per lead week in a bar chart."""
    fig, ax = plt.subplots(figsize=figsize, squeeze=True)

    colormap = plt.get_cmap(cmap)
    all_vals = (
        da_national.values[np.isfinite(da_national.values)]
        if da_national.values.size
        else np.array([0.0, 1.0])
    )
    _vmin = float(all_vals.min()) if vmin is None else vmin
    _vmax = float(all_vals.max()) if vmax is None else vmax

    values = []
    labels = []
    for lw in lead_weeks:
        if "lead_week" in da_national.dims:
            score_val = float(da_national.sel(lead_week=lw).values)
        else:
            score_val = float(da_national.values)
        values.append(score_val)
        labels.append(_LEAD_LABELS.get(lw, f"Week {lw}"))

    norm_vals = np.clip((np.array(values) - _vmin) / (_vmax - _vmin + 1e-12), 0, 1)
    colors = [colormap(v) for v in norm_vals]

    bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.8)

    # Add value labels on bars
    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{val:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_ylabel(da_national.attrs.get("long_name", "score"))
    ax.set_ylim(_vmin, _vmax * 1.1)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    fig.suptitle(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    return fig

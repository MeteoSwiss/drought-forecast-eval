"""Choropleth map of Switzerland drought regions coloured by a score value.

``plot_region_map``
    Creates a 4-panel figure (one panel per lead week) showing each of the
    38 drought regions coloured by the value of a chosen score variable.

    Requires ``geopandas`` and a shapefile / GeoJSON of the regions.
    Falls back to a bar-chart-per-region plot if no shapefile is provided or
    if ``geopandas`` is not installed.

Shapefile note
--------------
The authoritative shapefile is stored in the MeteoSwiss internal GitLab::

    https://service.meteoswiss.ch/git/climateanalysis/pycats/droughtmonitor/
    -/tree/main/droughtmonitor/regions/BAFU_Grossregionen_v3_reproj

Clone that repo and pass the ``.shp`` path as ``shapefile_path``.
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


def plot_region_map(
    ds_scores: xr.Dataset,
    score_variable: str,
    shapefile_path: str | Path | None = None,
    region_id_column: str = "REGION_NR",
    lead_weeks: list[int] | None = None,
    cmap: str = "RdYlGn",
    vmin: float | None = None,
    vmax: float | None = None,
    title: str | None = None,
    figsize: tuple[float, float] = (14, 10),
) -> plt.Figure:
    """Plot a 4-panel choropleth map of score values per drought region.

    Parameters
    ----------
    ds_scores:
        Scores dataset with dimensions ``(lead_week, drought_region_id)``.
    score_variable:
        Name of the score variable to plot (e.g. ``"spi_1m_mae"``).
    shapefile_path:
        Path to the ``.shp`` / ``.geojson`` file of the 38 drought regions.
        If ``None`` or the file does not exist, falls back to a bar chart.
    region_id_column:
        Name of the integer attribute column in the shapefile that holds the
        ``drought_region_id`` (1–38).
    lead_weeks:
        Subset of lead weeks to plot.  Defaults to ``[0, 1, 2, 3]``.
    cmap:
        Matplotlib colormap name.
    vmin, vmax:
        Colour scale limits.  If ``None``, derived from the data.
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

    # Try geo path
    geo_ok = _try_geopandas(shapefile_path)
    if geo_ok:
        return _plot_choropleth(
            da=da,
            shapefile_path=Path(shapefile_path),  # type: ignore[arg-type]
            region_id_column=region_id_column,
            lead_weeks=lead_weeks,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            title=title or score_variable,
            figsize=figsize,
        )
    else:
        logger.warning(
            "Falling back to bar chart: shapefile not available or geopandas not installed."
        )
        return _plot_bar_fallback(
            da=da,
            lead_weeks=lead_weeks,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            title=title or score_variable,
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


def _plot_choropleth(
    da: xr.DataArray,
    shapefile_path: Path,
    region_id_column: str,
    lead_weeks: list[int],
    cmap: str,
    vmin: float | None,
    vmax: float | None,
    title: str,
    figsize: tuple[float, float],
) -> plt.Figure:
    import geopandas as gpd

    gdf = gpd.read_file(shapefile_path)
    if region_id_column not in gdf.columns:
        # Try to find a column that looks like a region ID
        candidates = [c for c in gdf.columns if "region" in c.lower() or "id" in c.lower()]
        if candidates:
            region_id_column = candidates[0]
            logger.warning("Using '%s' as region ID column.", region_id_column)
        else:
            raise ValueError(
                f"Column '{region_id_column}' not found in shapefile. "
                f"Available columns: {gdf.columns.tolist()}"
            )

    n_panels = len(lead_weeks)
    ncols = min(n_panels, 4)
    nrows = int(np.ceil(n_panels / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False)

    # Determine colour scale
    if vmin is None or vmax is None:
        all_vals = da.values[np.isfinite(da.values)]
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

        if "lead_week" in da.dims:
            score_vals = da.sel(lead_week=lw)
        else:
            score_vals = da

        score_df = score_vals.to_dataframe(name="score_value").reset_index()
        merged_gdf = gdf.merge(
            score_df[["drought_region_id", "score_value"]],
            left_on=region_id_column,
            right_on="drought_region_id",
            how="left",
        )
        merged_gdf.plot(
            column="score_value",
            cmap=cmap,
            vmin=_vmin,
            vmax=_vmax,
            ax=ax,
            edgecolor="white",
            linewidth=0.5,
            missing_kwds={"color": "lightgrey", "label": "No data"},
        )
        ax.set_title(_LEAD_LABELS.get(lw, f"Week {lw}"), fontsize=11)
        ax.axis("off")

    # Hide unused subplots
    for panel_idx in range(len(lead_weeks), nrows * ncols):
        row, col = divmod(panel_idx, ncols)
        axes[row][col].set_visible(False)

    cbar_ax = fig.add_axes([0.94, 0.15, 0.02, 0.7])
    fig.colorbar(sm, cax=cbar_ax, label=da.attrs.get("long_name", da.name or "score"))
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 0.94, 1])
    return fig


# ---------------------------------------------------------------------------
# Bar chart fallback
# ---------------------------------------------------------------------------


def _plot_bar_fallback(
    da: xr.DataArray,
    lead_weeks: list[int],
    cmap: str,
    vmin: float | None,
    vmax: float | None,
    title: str,
    figsize: tuple[float, float],
) -> plt.Figure:
    n_panels = len(lead_weeks)
    fig, axes = plt.subplots(1, n_panels, figsize=figsize, sharey=True)
    if n_panels == 1:
        axes = [axes]

    colormap = plt.get_cmap(cmap)
    all_vals = da.values[np.isfinite(da.values)] if da.values.size else np.array([0.0, 1.0])
    _vmin = float(all_vals.min()) if vmin is None else vmin
    _vmax = float(all_vals.max()) if vmax is None else vmax

    for ax, lw in zip(axes, lead_weeks):
        if "lead_week" in da.dims:
            score_vals = da.sel(lead_week=lw)
        else:
            score_vals = da

        regions = score_vals["drought_region_id"].values
        values = score_vals.values
        norm_vals = np.clip((values - _vmin) / (_vmax - _vmin + 1e-12), 0, 1)
        colors = [colormap(v) for v in norm_vals]
        ax.barh(regions, values, color=colors)
        ax.set_title(_LEAD_LABELS.get(lw, f"Week {lw}"), fontsize=10)
        ax.set_xlabel(da.attrs.get("long_name", "score"))
        ax.set_ylabel("Region ID")
        ax.axvline(0, color="black", linewidth=0.8, linestyle=":")

    fig.suptitle(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    return fig

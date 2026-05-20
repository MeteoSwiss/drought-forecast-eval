"""ReportBuilder: single-entry-point orchestrator for the full pipeline.

Usage
-----
>>> builder = ReportBuilder(
...     archive_dir="/data/zips",
...     historic_path="/data/historic.zip",
...     date_range=("2025-01-01", "2025-12-31"),
...     output_dir="./output",
... )
>>> builder.run()                     # → output/scores.nc + output/report.html
>>> ds_scores = builder.compute_scores()   # just scores, no I/O
"""

from __future__ import annotations

import base64
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — safe in report/notebook contexts
import matplotlib.pyplot as plt
import xarray as xr

from drought_forecast_eval._version import __version__
from drought_forecast_eval.config.settings import (
    DEFAULT_CDI_THRESHOLD,
    DEFAULT_SCORES,
    DEFAULT_SHAPEFILE,
    DEFAULT_VARIABLES,
    DEFAULT_WEEK_WINDOW,
    LEAD_WEEKS,
)
from drought_forecast_eval.io.loader import load_forecasts, load_observations
from drought_forecast_eval.processing.alignment import align_obs_to_forecast
from drought_forecast_eval.processing.reference import (
    climatology_reference,
    persistence_reference,
)
from drought_forecast_eval.scoring.dispatcher import compute_scores
from drought_forecast_eval.visualization.region_map import plot_region_map
from drought_forecast_eval.visualization.skill_curves import plot_skill_vs_lead

logger = logging.getLogger(__name__)


class ReportBuilder:
    """Orchestrate the full verification pipeline.

    Parameters
    ----------
    archive_dir:
        Flat directory of daily forecast ZIP archives.
    historic_path:
        Path to the historic observation ZIP (or CSV).
    date_range:
        ``(start, end)`` ISO-date strings for the verification window.
    regions:
        ``"all"`` or a list of integer region IDs.
    variables:
        ``"all"``, a group name, or a list of variable keys.
    scores:
        ``"default"`` or a list of metric names.
    reference:
        Which reference forecast strategy to use: ``"climatology"``,
        ``"persistence"``, or ``"both"``.
    cdi_threshold:
        Binary event threshold for CDI ROC-AUC.
    shapefile_path:
        Path to the drought-region shapefile for map plots.
    output_dir:
        Directory where all output files are written.
    week_window:
        Half-width of the climatology week-of-year window (weeks).
    variable_map:
        Override the global VARIABLE_MAP for custom experiments.
    """

    def __init__(
        self,
        archive_dir: str | Path,
        historic_path: str | Path,
        date_range: tuple[str, str],
        regions: list[int] | Literal["all"] = "all",
        variables: list[str] | Literal["all"] = "all",
        scores: list[str] | Literal["default"] = "default",
        reference: Literal["climatology", "persistence", "both"] = "climatology",
        cdi_threshold: float = DEFAULT_CDI_THRESHOLD,
        shapefile_path: str | Path | None = DEFAULT_SHAPEFILE,
        output_dir: str | Path = "./output",
        week_window: int = DEFAULT_WEEK_WINDOW,
        variable_map: dict | None = None,
    ) -> None:
        self.archive_dir = Path(archive_dir)
        self.historic_path = Path(historic_path)
        self.date_range = date_range
        self.regions = regions
        self.variables = variables
        self.scores = scores
        self.reference = reference
        self.cdi_threshold = cdi_threshold
        self.shapefile_path = Path(shapefile_path) if shapefile_path else None
        self.output_dir = Path(output_dir)
        self.week_window = week_window
        self.variable_map = variable_map

        # Lazy-loaded internal state
        self._ds_fcst: xr.Dataset | None = None
        self._ds_obs: xr.Dataset | None = None
        self._ds_merged: xr.Dataset | None = None
        self._ds_ref: xr.Dataset | None = None
        self._ds_scores: xr.Dataset | None = None

    # ------------------------------------------------------------------
    # Public pipeline methods
    # ------------------------------------------------------------------

    def load_data(self) -> None:
        """Load forecast and observation data from disk."""
        region_ids = None if self.regions == "all" else self.regions
        logger.info("Loading forecasts from %s …", self.archive_dir)
        self._ds_fcst = load_forecasts(
            self.archive_dir,
            date_range=self.date_range,
            region_ids=region_ids,
        )
        logger.info("Loading observations from %s …", self.historic_path)
        self._ds_obs = load_observations(self.historic_path, region_ids=region_ids)

    def build_reference(self) -> None:
        """Construct reference forecast dataset(s)."""
        if self._ds_fcst is None or self._ds_obs is None:
            self.load_data()

        refs: list[xr.Dataset] = []
        if self.reference in ("climatology", "both"):
            logger.info("Building climatology reference (week_window=%d) …", self.week_window)
            clim = climatology_reference(
                self._ds_obs,
                self._ds_fcst,
                week_window=self.week_window,  # type: ignore[arg-type]
            )
            refs.append(clim)
        if self.reference in ("persistence", "both"):
            logger.info("Building persistence reference …")
            pers = persistence_reference(self._ds_obs, self._ds_fcst)  # type: ignore[arg-type]
            refs.append(pers)

        if len(refs) == 1:
            self._ds_ref = refs[0]
        elif len(refs) == 2:
            # Merge: climatology takes precedence for p10/p90, persistence for p50
            self._ds_ref = xr.merge(refs, compat="override")
            self._ds_ref.attrs["reference_type"] = "both"

    def align(self) -> None:
        """Align observations onto the forecast grid."""
        if self._ds_fcst is None or self._ds_obs is None:
            self.load_data()
        logger.info("Aligning observations to forecast grid …")
        self._ds_merged = align_obs_to_forecast(self._ds_fcst, self._ds_obs)  # type: ignore[arg-type]

    def compute_scores(self) -> xr.Dataset:
        """Run the scoring pipeline and return the scores dataset.

        This is idempotent: subsequent calls return the cached result.
        """
        if self._ds_scores is not None:
            return self._ds_scores

        if self._ds_merged is None:
            self.align()
        if self._ds_ref is None:
            self.build_reference()

        logger.info("Computing scores …")
        self._ds_scores = compute_scores(
            self._ds_merged,  # type: ignore[arg-type]
            variables=self.variables,
            scores=self.scores,
            ds_ref=self._ds_ref,
            cdi_threshold=self.cdi_threshold,
            variable_map=self.variable_map,
        )
        return self._ds_scores

    def plot_skill_curves(
        self,
        score: str = "mae",
        variables: list[str] | None = None,
    ) -> plt.Figure:
        """Generate skill-vs-lead-week plot."""
        ds = self.compute_scores()
        var_list = variables or _available_vars_for_score(ds, score)
        return plot_skill_vs_lead(ds, var_list, score=score)

    def plot_region_maps(
        self,
        score_variable: str | None = None,
    ) -> plt.Figure:
        """Generate 4-panel regional map for a score variable."""
        ds = self.compute_scores()
        sv = score_variable or _first_available(ds)
        return plot_region_map(
            ds,
            score_variable=sv,
            shapefile_path=self.shapefile_path,
            lead_weeks=LEAD_WEEKS,
        )

    def export_csv(self, path: str | Path | None = None) -> Path:
        """Export scores summary to CSV (aggregated over regions and lead weeks)."""
        ds = self.compute_scores()
        out = Path(path) if path else self.output_dir / "scores_summary.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        df = ds.mean(dim="drought_region_id").to_dataframe()
        df.to_csv(out)
        logger.info("CSV written to %s", out)
        return out

    def export_netcdf(self, path: str | Path | None = None) -> Path:
        """Write full scores dataset to NetCDF4."""
        ds = self.compute_scores()
        stem = f"scores_{self.date_range[0]}_{self.date_range[1]}".replace("-", "")
        out = Path(path) if path else self.output_dir / f"{stem}.nc"
        out.parent.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(out)
        logger.info("NetCDF written to %s", out)
        return out

    def export_html(self, path: str | Path | None = None) -> Path:
        """Render the verification report to HTML."""
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError as exc:
            raise ImportError(
                "jinja2 is required for HTML export. Install it with: poetry install --with report"
            ) from exc

        ds = self.compute_scores()
        out = Path(path) if path else self.output_dir / "report.html"
        out.parent.mkdir(parents=True, exist_ok=True)

        template_dir = Path(__file__).parent / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        template = env.get_template("report.html.jinja2")

        # Build summary table rows
        summary_table = _build_summary_table(ds)

        # Build embedded plot images (base64)
        plots = _build_plot_images(self, ds)

        n_regions = (
            len(self.regions)
            if isinstance(self.regions, list)
            else int(ds["drought_region_id"].size)
            if "drought_region_id" in ds.coords
            else 38
        )

        html = template.render(
            meta={
                "date_range": self.date_range,
                "n_regions": n_regions,
                "regions": self.regions,
                "reference_type": self._ds_ref.attrs.get("reference_type", "none")
                if self._ds_ref
                else "none",
                "cdi_threshold": self.cdi_threshold,
                "variables": (
                    self.variables if isinstance(self.variables, list) else DEFAULT_VARIABLES
                ),
                "scores": self.scores if isinstance(self.scores, list) else DEFAULT_SCORES,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
                "library_version": __version__,
            },
            summary_table=summary_table,
            lead_weeks=LEAD_WEEKS,
            plots=plots,
        )
        out.write_text(html, encoding="utf-8")
        logger.info("HTML report written to %s", out)
        return out

    def run(self) -> dict[str, Path]:
        """Execute the full pipeline: load → align → score → export.

        Returns
        -------
        dict mapping output type to file path.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.load_data()
        self.build_reference()
        self.align()
        self.compute_scores()

        outputs: dict[str, Path] = {}
        outputs["netcdf"] = self.export_netcdf()
        outputs["csv"] = self.export_csv()

        try:
            outputs["html"] = self.export_html()
        except ImportError:
            logger.warning("jinja2 not installed — skipping HTML report.")

        logger.info("ReportBuilder.run() complete. Outputs: %s", outputs)
        return outputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _available_vars_for_score(ds: xr.Dataset, score: str) -> list[str]:
    """Return variable keys whose '{key}_{score}' column exists in ds."""
    results = []
    for varname in ds.data_vars:
        if varname.endswith(f"_{score}"):
            results.append(varname[: -len(f"_{score}")])
    return results[:8]  # limit to 8 for readability


def _first_available(ds: xr.Dataset) -> str:
    """Return the first data variable name."""
    return list(ds.data_vars)[0]


def _build_summary_table(ds: xr.Dataset) -> list[dict]:
    """Build rows for the HTML summary table."""
    rows = []
    for varname in ds.data_vars:
        # Parse variable key and metric from varname
        parts = varname.rsplit("_", 1)
        if len(parts) < 2:
            continue
        var_key, metric = parts[0], parts[1]
        da = ds[varname]
        if "lead_week" not in da.dims:
            continue
        # Average over regions
        if "drought_region_id" in da.dims:
            da = da.mean(dim="drought_region_id")
        values = []
        for lw in LEAD_WEEKS:
            if lw in da["lead_week"].values:
                v = float(da.sel(lead_week=lw).values)
                values.append(v if not (v != v) else None)  # nan → None
            else:
                values.append(None)
        rows.append({"variable": var_key, "metric": metric, "values": values})
    return rows


def _fig_to_b64(fig: plt.Figure) -> str:
    """Convert a matplotlib Figure to a base64-encoded PNG data URI."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _build_plot_images(builder: ReportBuilder, ds: xr.Dataset) -> dict:
    """Generate all plots and encode them as base64 data URIs for inline HTML."""
    plots: dict = {"skill_curves": [], "region_maps": [], "comparisons": []}

    # Skill curves per metric
    for score in ["mae", "rmse", "rpss"]:
        var_list = _available_vars_for_score(ds, score)
        if not var_list:
            continue
        try:
            fig = plot_skill_vs_lead(ds, var_list, score=score)
            plots["skill_curves"].append(
                {"path": _fig_to_b64(fig), "caption": f"{score.upper()} by lead week"}
            )
        except Exception as exc:
            logger.warning("Could not generate skill curve for '%s': %s", score, exc)

    # Regional maps per first available score variable
    for sv in list(ds.data_vars)[:3]:
        try:
            fig = plot_region_map(
                ds,
                sv,
                shapefile_path=builder.shapefile_path,
                lead_weeks=LEAD_WEEKS,
            )
            plots["region_maps"].append({"path": _fig_to_b64(fig), "caption": sv})
        except Exception as exc:
            logger.warning("Could not generate region map for '%s': %s", sv, exc)

    return plots

"""Run the full verification pipeline against the real BGDI ZIP archive.

Usage
-----
    poetry run drought-eval [OPTIONS]
    # or directly:
    poetry run python scripts/run_verification.py [OPTIONS]

Each daily ZIP already contains ``weekly_current_regions.csv`` with ~52 weeks
of observed values, so no separate historic file is required — observations are
assembled directly from the archive.
"""

from __future__ import annotations

import io
import logging
import sys
import zipfile
from pathlib import Path

import click
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent.parent))

from drought_forecast_eval.io.archive import scan_archive
from drought_forecast_eval.io.loader import load_forecasts
from drought_forecast_eval.io.schema import validate_observation
from drought_forecast_eval.processing.alignment import align_obs_to_forecast
from drought_forecast_eval.processing.reference import (
    climatology_reference,
    persistence_reference,
)
from drought_forecast_eval.scoring.dispatcher import compute_scores

_OBS_CSV = "weekly_current_regions.csv"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Observation assembly
# ---------------------------------------------------------------------------

def _read_obs_csv_from_zip(zf: zipfile.ZipFile) -> pd.DataFrame | None:
    """Read weekly_current_regions.csv from an open ZipFile, stripping # headers."""
    if _OBS_CSV not in zf.namelist():
        return None
    with zf.open(_OBS_CSV) as f:
        raw = f.read().decode("utf-8", errors="replace")
    data_lines = [l for l in raw.splitlines() if not l.startswith("#")]
    if not data_lines:
        return None
    sep = ";" if ";" in data_lines[0] else ","
    df = pd.read_csv(io.StringIO("\n".join(data_lines)), sep=sep, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    return df


def load_observations_from_archive(archive_dir: Path) -> xr.Dataset:
    """Assemble observations by reading ``weekly_current_regions.csv`` from
    every ZIP in the archive and deduplicating on ``(region, date)``."""
    entries = scan_archive(archive_dir)
    frames: list[pd.DataFrame] = []

    logger.info("Assembling observations from %d ZIPs …", len(entries))
    for _frt, path in entries:
        try:
            with zipfile.ZipFile(path, "r") as zf:
                df = _read_obs_csv_from_zip(zf)
        except (zipfile.BadZipFile, KeyError) as exc:
            logger.warning("Skipping obs from %s: %s", path.name, exc)
            continue
        if df is not None and not df.empty:
            frames.append(df)

    if not frames:
        raise RuntimeError("No observation data could be read from the archive.")

    combined = pd.concat(frames, ignore_index=True)

    # Normalise the date column: some files use 'valid_at', others 'measured_at'
    if "measured_at" not in combined.columns and "valid_at" in combined.columns:
        combined = combined.rename(columns={"valid_at": "measured_at"})

    combined["measured_at"] = pd.to_datetime(
        combined["measured_at"], dayfirst=True, errors="coerce"
    )
    combined = (
        combined
        .dropna(subset=["measured_at"])
        .drop_duplicates(subset=["drought_region_id", "measured_at"])
        .sort_values(["drought_region_id", "measured_at"])
        .reset_index(drop=True)
    )

    logger.info(
        "Observations: %d rows, %s → %s, %d regions.",
        len(combined),
        combined["measured_at"].min().date(),
        combined["measured_at"].max().date(),
        combined["drought_region_id"].nunique(),
    )

    combined = validate_observation(combined)
    combined = combined.rename(columns={"measured_at": "valid_at"})
    ds = combined.set_index(["drought_region_id", "valid_at"]).to_xarray()
    ds.attrs["source"] = "drought_forecast_eval (assembled from archive)"
    return ds


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--archive-dir",
    default="data/zipfiles",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Flat directory of daily forecast ZIPs.",
)
@click.option(
    "--historic-path",
    default="data/historic/trockenheitsdaten-numerisch_historic.csv.zip",
    show_default=True,
    type=click.Path(path_type=Path),
    help="Historic observations ZIP. Falls back to assembling obs from the archive if not found.",
)
@click.option(
    "--output-dir",
    default="output",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory for scores .nc and summary .csv.",
)
@click.option(
    "--start",
    default=None,
    metavar="YYYY-MM-DD",
    help="Start date (inclusive). Defaults to the first ZIP in the archive.",
)
@click.option(
    "--end",
    default=None,
    metavar="YYYY-MM-DD",
    help="End date (inclusive). Defaults to the last ZIP in the archive.",
)
@click.option(
    "--reference",
    default="climatology",
    show_default=True,
    type=click.Choice(["climatology", "persistence", "both"], case_sensitive=False),
    help="Reference forecast strategy for skill scores.",
)
@click.option(
    "--variables",
    default="all",
    show_default=True,
    help=(
        "Variables to score: 'all', a group name (cdi / spi / precip), "
        "or a comma-separated list of variable keys."
    ),
)
@click.option(
    "--scores",
    default="default",
    show_default=True,
    help=(
        "Metrics to compute: 'default' or a comma-separated list "
        "(e.g. mae,rmse,rpss)."
    ),
)
@click.option(
    "--shapefile",
    default="shapefiles/BAFU_Grossregionen_v3.shp",
    show_default=True,
    type=click.Path(path_type=Path),
    help="Path to the BAFU drought-region shapefile (.shp).",
)
@click.option(
    "--html",
    is_flag=True,
    help="Render an HTML report to OUTPUT_DIR/report.html (requires poetry install --with report).",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable DEBUG logging.")
def cli(
    archive_dir: Path,
    output_dir: Path,
    historic_path: Path,
    start: str | None,
    end: str | None,
    reference: str,
    variables: str,
    scores: str,
    shapefile: Path,
    html: bool,
    verbose: bool,
) -> None:
    """Run the drought forecast verification pipeline.

    Reads forecasts and observations directly from the ZIP archive — no
    separate historic file is required.  Writes a NetCDF scores file and
    a CSV summary to OUTPUT_DIR.  Pass --html to also render an HTML report.
    """
    _configure_logging(verbose)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Resolve date range ────────────────────────────────────────────────
    entries = scan_archive(archive_dir)
    if not entries:
        raise click.ClickException(f"No ZIP files found in {archive_dir}.")

    start = start or entries[0][0].strftime("%Y-%m-%d")
    end = end or entries[-1][0].strftime("%Y-%m-%d")
    click.echo(f"Verification window : {start} → {end}")
    click.echo(f"Reference strategy  : {reference}")

    # ── Parse list arguments ──────────────────────────────────────────────
    var_list: list[str] | str = (
        [v.strip() for v in variables.split(",")] if "," in variables else variables
    )
    score_list: list[str] | str = (
        [s.strip() for s in scores.split(",")] if scores != "default" and "," in scores else scores
    )

    # ── 1. Load forecasts ─────────────────────────────────────────────────
    with click.progressbar(length=1, label="Loading forecasts    ") as bar:
        ds_fcst = load_forecasts(archive_dir, date_range=(start, end))
        bar.update(1)
    click.echo(
        f"  {ds_fcst.sizes['forecast_reference_time']} FRTs × "
        f"{ds_fcst.sizes['drought_region_id']} regions × "
        f"{ds_fcst.sizes['lead_week']} lead weeks"
    )

    # ── 2. Load observations ──────────────────────────────────────────────
    if historic_path.exists():
        click.echo(f"Loading observations from {historic_path} …")
        from drought_forecast_eval.io.loader import load_observations
        with click.progressbar(length=1, label="Loading obs          ") as bar:
            ds_obs = load_observations(historic_path)
            bar.update(1)
    else:
        click.echo(
            click.style(f"Historic file not found at {historic_path} — assembling obs from archive.", fg="yellow")
        )
        with click.progressbar(length=1, label="Assembling obs       ") as bar:
            ds_obs = load_observations_from_archive(archive_dir)
            bar.update(1)

    # ── 3. Align ──────────────────────────────────────────────────────────
    with click.progressbar(length=1, label="Aligning             ") as bar:
        ds_merged = align_obs_to_forecast(ds_fcst, ds_obs)
        bar.update(1)

    # ── 4. Build reference ────────────────────────────────────────────────
    with click.progressbar(length=1, label="Building reference   ") as bar:
        refs: list[xr.Dataset] = []
        if reference in ("climatology", "both"):
            refs.append(climatology_reference(ds_obs, ds_fcst))
        if reference in ("persistence", "both"):
            refs.append(persistence_reference(ds_obs, ds_fcst))
        ds_ref = refs[0] if len(refs) == 1 else xr.merge(refs, compat="override")
        bar.update(1)

    # ── 5. Compute scores ─────────────────────────────────────────────────
    with click.progressbar(length=1, label="Computing scores     ") as bar:
        ds_scores = compute_scores(
            ds_merged,
            variables=var_list,
            scores=score_list,
            ds_ref=ds_ref,
        )
        bar.update(1)

    # ── 6. Export ─────────────────────────────────────────────────────────
    start_slug = start.replace("-", "")
    end_slug = end.replace("-", "")
    nc_path = output_dir / f"scores_{start_slug}_{end_slug}.nc"
    csv_path = output_dir / "scores_summary.csv"

    ds_scores.to_netcdf(nc_path)
    summary_df = (
        ds_scores
        .mean(dim="drought_region_id")
        .to_dataframe()
        .round(4)
    )
    summary_df.to_csv(csv_path)

    click.echo(f"\nOutputs written to {output_dir}/")
    click.echo(f"  {nc_path.name}")
    click.echo(f"  {csv_path.name}")

    # ── 7. HTML report (optional) ───────────────────────────────────────────
    if html:
        from drought_forecast_eval.report.builder import ReportBuilder
        builder = ReportBuilder(
            archive_dir=archive_dir,
            historic_path=historic_path,
            date_range=(start, end),
            output_dir=output_dir,
            shapefile_path=shapefile if shapefile.exists() else None,
        )
        # Inject already-computed state so the builder skips redundant work
        builder._ds_fcst = ds_fcst
        builder._ds_obs = ds_obs
        builder._ds_merged = ds_merged
        builder._ds_ref = ds_ref
        builder._ds_scores = ds_scores
        with click.progressbar(length=1, label="Rendering HTML       ") as bar:
            html_path = builder.export_html()
            bar.update(1)
        click.echo(f"  {html_path.name}")

    # ── 8. Summary table ─────────────────────────────────────────────────
    click.echo("\n" + "=" * 70)
    click.echo(f"  Score summary (mean across all regions)")
    click.echo("=" * 70)
    click.echo(summary_df.to_string())
    click.echo("=" * 70)


if __name__ == "__main__":
    cli()

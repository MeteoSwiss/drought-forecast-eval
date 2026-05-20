"""High-level loaders: ZIP archives → validated xr.Dataset.

``load_forecasts``
    Iterates every ZIP in the archive, reads ``weekly_forecast_regions.csv``,
    validates against ``FORECAST_SCHEMA``, computes ``lead_week``, and
    concatenates along the ``forecast_reference_time`` dimension.

``load_observations``
    Reads the single historic ZIP (``weekly_historic_regions.csv``), validates
    against ``OBSERVATION_SCHEMA``, and returns an observation dataset indexed
    by ``(drought_region_id, valid_at)``.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from drought_forecast_eval.io.archive import scan_archive
from drought_forecast_eval.io.schema import (
    SchemaError,
    validate_forecast,
    validate_observation,
)
from drought_forecast_eval.processing.lead_time import compute_lead_weeks

logger = logging.getLogger(__name__)

# Name of the forecast CSV inside each rolling ZIP
_FORECAST_CSV = "weekly_forecast_regions.csv"
# Name of the observation CSV inside each rolling ZIP and in the historic ZIP
_HISTORIC_CSV = "weekly_historic_regions.csv"

# Regex to find the header comment line with the update date
_HEADER_DATE_RE = re.compile(r"letzte Aktualisierung[:\s]+(\d{2}\.\d{2}\.\d{4})")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_csv_from_zip(zf: zipfile.ZipFile, csv_name: str) -> tuple[pd.DataFrame, str | None]:
    """Read a named CSV from an open ZipFile, stripping comment lines.

    Returns
    -------
    (DataFrame, header_date_str | None)
        The parsed DataFrame and the raw date string from the header comment,
        if present (format DD.MM.YYYY).
    """
    with zf.open(csv_name) as f:
        raw_bytes = f.read()

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    lines = raw_text.splitlines()

    header_date: str | None = None
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("#"):
            m = _HEADER_DATE_RE.search(line)
            if m:
                header_date = m.group(1)
        else:
            data_lines.append(line)

    csv_blob = "\n".join(data_lines)
    # Real files use ';' as separator; fall back to ',' for test fixtures
    sep = ";" if data_lines and ";" in data_lines[0] else ","
    df = pd.read_csv(io.StringIO(csv_blob), sep=sep, skipinitialspace=True)
    # Strip whitespace from column names (defensive)
    df.columns = df.columns.str.strip()
    return df, header_date


def _find_csv_in_zip(zf: zipfile.ZipFile, target: str) -> str | None:
    """Return the internal ZIP name that matches ``target`` (basename match)."""
    for name in zf.namelist():
        if Path(name).name == target:
            return name
    return None


# ---------------------------------------------------------------------------
# load_forecasts
# ---------------------------------------------------------------------------

def load_forecasts(
    archive_dir: str | Path,
    date_range: tuple[str, str] | None = None,
    region_ids: list[int] | None = None,
) -> xr.Dataset:
    """Load forecast data from a flat directory of ZIP archives.

    Each ZIP is expected to contain ``weekly_forecast_regions.csv``.
    The ``forecast_reference_time`` is parsed from the ZIP filename
    (``YYYYMMDD`` block).

    Parameters
    ----------
    archive_dir:
        Path to the flat directory containing the daily ZIP files.
    date_range:
        Optional ``(start, end)`` ISO-date strings (inclusive).
    region_ids:
        Optional list of ``drought_region_id`` integers to keep.
        ``None`` returns all 38 regions.

    Returns
    -------
    xr.Dataset
        Dimensions: ``(forecast_reference_time, drought_region_id, lead_week)``
        Coordinates: ``forecast_reference_time``, ``drought_region_id``,
                     ``lead_week`` (int 0–3), ``valid_at`` (derived datetime).
        Variables: all forecast columns from ``FORECAST_SCHEMA``.

    Raises
    ------
    FileNotFoundError
        If ``archive_dir`` does not exist.
    SchemaError
        If a CSV is structurally invalid.
    RuntimeError
        If no valid ZIP files are found.
    """
    entries = scan_archive(archive_dir, date_range=date_range)
    if not entries:
        raise RuntimeError(
            f"No valid ZIP files found in '{archive_dir}'"
            + (f" for date range {date_range}" if date_range else "")
        )

    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    for frt, path in entries:
        try:
            df = _load_single_forecast_zip(path, frt)
        except (SchemaError, KeyError, zipfile.BadZipFile, Exception) as exc:
            logger.warning("Skipping %s: %s", path.name, exc)
            errors.append(f"{path.name}: {exc}")
            continue

        if region_ids is not None:
            df = df[df["drought_region_id"].isin(region_ids)]

        frames.append(df)

    if not frames:
        raise RuntimeError(
            f"All ZIP files failed to load. Errors:\n" + "\n".join(errors)
        )

    if errors:
        logger.warning("%d ZIP(s) had errors and were skipped.", len(errors))

    combined = pd.concat(frames, ignore_index=True)
    return _forecast_df_to_xarray(combined)


def _load_single_forecast_zip(path: Path, frt: datetime) -> pd.DataFrame:
    """Load and validate the forecast CSV from a single ZIP file."""
    with zipfile.ZipFile(path, "r") as zf:
        csv_name = _find_csv_in_zip(zf, _FORECAST_CSV)
        if csv_name is None:
            raise KeyError(f"'{_FORECAST_CSV}' not found inside {path.name}")
        df, header_date = _read_csv_from_zip(zf, csv_name)

    # Cross-validate header date vs filename date (warn only — don't fail)
    if header_date is not None:
        try:
            header_frt = datetime.strptime(header_date, "%d.%m.%Y")
            if header_frt.date() != frt.date():
                logger.warning(
                    "%s: filename date (%s) differs from header date (%s); "
                    "using filename date.",
                    path.name,
                    frt.date(),
                    header_frt.date(),
                )
        except ValueError:
            pass

    df = validate_forecast(df)
    df["forecast_reference_time"] = pd.Timestamp(frt)
    df["lead_week"] = compute_lead_weeks(df["valid_at"], frt)
    return df


def _forecast_df_to_xarray(df: pd.DataFrame) -> xr.Dataset:
    """Convert a concatenated forecast DataFrame to an xr.Dataset."""
    index_cols = ["forecast_reference_time", "drought_region_id", "lead_week"]

    # Derive valid_at as a coordinate (keep first occurrence per index)
    df = df.sort_values(index_cols)

    # Store valid_at as a coordinate variable before pivoting
    valid_at_map = (
        df.set_index(index_cols)["valid_at"]
        .to_xarray()
    )

    # Build the dataset from all numeric forecast variables
    value_cols = [
        c for c in df.columns
        if c not in [*index_cols, "valid_at"]
    ]

    ds = (
        df[index_cols + value_cols]
        .set_index(index_cols)
        .to_xarray()
    )
    ds = ds.assign_coords(valid_at=valid_at_map)
    ds["forecast_reference_time"].attrs["long_name"] = "Forecast reference time"
    ds["lead_week"].attrs["long_name"] = "Lead time (weeks)"
    ds["lead_week"].attrs["units"] = "weeks"
    ds.attrs["source"] = "drought_forecast_eval"
    ds.attrs["description"] = "Swiss drought forecast archive"
    return ds


# ---------------------------------------------------------------------------
# load_observations
# ---------------------------------------------------------------------------

def load_observations(
    historic_path: str | Path,
    region_ids: list[int] | None = None,
) -> xr.Dataset:
    """Load the full observation archive from the historic ZIP.

    Parameters
    ----------
    historic_path:
        Path to the historic ZIP file (``weekly_historic_regions.csv.zip``)
        or to an already-extracted CSV.
    region_ids:
        Optional list of ``drought_region_id`` integers to keep.

    Returns
    -------
    xr.Dataset
        Dimensions: ``(drought_region_id, valid_at)``
        Variables: all observation columns from ``OBSERVATION_SCHEMA``.

    Raises
    ------
    FileNotFoundError
        If the path does not exist.
    SchemaError
        If the CSV is structurally invalid.
    """
    historic_path = Path(historic_path)
    if not historic_path.exists():
        raise FileNotFoundError(f"Historic archive not found: {historic_path}")

    if historic_path.suffix == ".zip":
        df = _load_obs_from_zip(historic_path)
    elif historic_path.suffix == ".csv":
        df = _load_obs_from_csv(historic_path)
    else:
        raise ValueError(
            f"Unsupported file type '{historic_path.suffix}'. "
            "Expected .zip or .csv."
        )

    df = validate_observation(df)
    # Rename measured_at → valid_at for a unified time coordinate
    df = df.rename(columns={"measured_at": "valid_at"})

    if region_ids is not None:
        df = df[df["drought_region_id"].isin(region_ids)]

    return _obs_df_to_xarray(df)


def _load_obs_from_zip(path: Path) -> pd.DataFrame:
    """Read the observation CSV from inside a ZIP archive."""
    with zipfile.ZipFile(path, "r") as zf:
        csv_name = _find_csv_in_zip(zf, _HISTORIC_CSV)
        if csv_name is None:
            # Fall back: take the first CSV-like member
            candidates = [n for n in zf.namelist() if n.endswith(".csv")]
            if not candidates:
                raise KeyError(f"No CSV found inside {path.name}")
            csv_name = candidates[0]
            logger.warning(
                "Expected '%s' inside %s; using '%s' as fallback.",
                _HISTORIC_CSV, path.name, csv_name,
            )
        df, _ = _read_csv_from_zip(zf, csv_name)
    return df


def _load_obs_from_csv(path: Path) -> pd.DataFrame:
    """Read the observation CSV from a plain (unzipped) file."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    data_lines = [l for l in lines if not l.startswith("#")]
    csv_blob = "".join(data_lines)
    sep = ";" if data_lines and ";" in data_lines[0] else ","
    df = pd.read_csv(io.StringIO(csv_blob), sep=sep, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    return df


def _obs_df_to_xarray(df: pd.DataFrame) -> xr.Dataset:
    """Convert the observation DataFrame to an xr.Dataset."""
    index_cols = ["drought_region_id", "valid_at"]
    value_cols = [c for c in df.columns if c not in index_cols]

    df = df.sort_values(index_cols)
    ds = df.set_index(index_cols).to_xarray()
    ds.attrs["source"] = "drought_forecast_eval"
    ds.attrs["description"] = "Swiss drought observation archive"
    return ds

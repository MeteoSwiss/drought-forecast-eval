"""Archive scanning: map a flat directory of ZIP files to (datetime, Path) pairs.

Filename convention
-------------------
    trockenheitsdaten-numerisch_current.csv.YYYYMMDDHHII.zip

The 8-digit date block (YYYYMMDD) immediately preceding the 4-digit hour-minute
block encodes the ``forecast_reference_time``.  The time component (HHII) is
ignored for verification purposes; if two ZIPs share the same YYYYMMDD date only
the latest one (lexicographically last) is kept.

Example
-------
>>> from drought_forecast_eval.io.archive import scan_archive
>>> entries = scan_archive("/data/drought_zips", date_range=("2025-07-01","2025-09-30"))
>>> entries[0]
(datetime.datetime(2025, 7, 1, 0, 0), PosixPath('/data/drought_zips/trockenheitsdaten...zip'))
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Matches the YYYYMMDDHHII block at the end of the stem before .zip
_FILENAME_RE = re.compile(r"(\d{8})\d{4}\.zip$")

#: Public BGDI URL pattern for the daily rolling archive
BGDI_ARCHIVE_URL_TEMPLATE = (
    "https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/"
    "trockenheitsdaten-numerisch_current/"
    "trockenheitsdaten-numerisch_current.csv.{date_str}2100.zip"
)

#: Public BGDI URL for the full historic archive
BGDI_HISTORIC_URL = (
    "https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/"
    "trockenheitsdaten-numerisch_historic/"
    "trockenheitsdaten-numerisch_historic.csv.zip"
)


def _parse_frt_from_filename(path: Path) -> datetime | None:
    """Extract forecast_reference_time from a ZIP filename.

    Returns ``None`` if the filename does not match the expected pattern.
    """
    m = _FILENAME_RE.search(path.name)
    if m is None:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return None


def scan_archive(
    archive_dir: str | Path,
    date_range: tuple[str, str] | None = None,
    region_ids: list[int] | None = None,  # kept for API symmetry; filtering is in loader
) -> list[tuple[datetime, Path]]:
    """Scan a flat directory and return sorted (forecast_reference_time, path) pairs.

    Only files matching the expected filename pattern are returned.  If multiple
    ZIPs share the same date (e.g. re-runs), only the lexicographically last one
    is kept (highest HHII suffix → most recent run of that day).

    Parameters
    ----------
    archive_dir:
        Path to the flat directory containing ZIP files.
    date_range:
        Optional ``(start, end)`` ISO-date strings (inclusive on both ends).
        If ``None``, all available ZIPs are returned.
    region_ids:
        Unused at this layer; accepted for API symmetry so callers can pass
        region selection once and forward it unchanged.

    Returns
    -------
    list of (datetime, Path)
        Sorted ascending by forecast_reference_time.

    Raises
    ------
    FileNotFoundError
        If ``archive_dir`` does not exist.
    """
    archive_dir = Path(archive_dir)
    if not archive_dir.exists():
        raise FileNotFoundError(f"Archive directory not found: {archive_dir}")

    # Build {date → latest_path} to deduplicate same-day ZIPs
    date_to_path: dict[datetime, Path] = {}
    skipped = 0
    for path in archive_dir.iterdir():
        if not path.is_file():
            continue
        frt = _parse_frt_from_filename(path)
        if frt is None:
            logger.debug("Skipping unrecognised file: %s", path.name)
            skipped += 1
            continue
        # Keep lexicographically latest for same date (highest HHII)
        if frt not in date_to_path or path.name > date_to_path[frt].name:
            date_to_path[frt] = path

    if skipped:
        logger.debug("Skipped %d non-matching files in %s", skipped, archive_dir)

    # Apply date range filter
    if date_range is not None:
        start = datetime.strptime(date_range[0], "%Y-%m-%d")
        end = datetime.strptime(date_range[1], "%Y-%m-%d")
        date_to_path = {dt: p for dt, p in date_to_path.items() if start <= dt <= end}

    entries = sorted(date_to_path.items())
    logger.info(
        "scan_archive: found %d ZIPs in %s%s",
        len(entries),
        archive_dir,
        f" between {date_range[0]} and {date_range[1]}" if date_range else "",
    )
    return entries

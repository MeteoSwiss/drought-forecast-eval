"""Utilities to download ZIP archives from the BGDI open-data portal.

The functions here are thin wrappers around ``requests`` and replicate what
a cron-triggered ``wget`` script would do, but in pure Python so they can be
called from notebooks or the :class:`~drought_forecast_eval.report.builder.ReportBuilder`.

BGDI URL patterns
-----------------
Rolling daily archive (one per day)::

    https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/
    trockenheitsdaten-numerisch_current/
    trockenheitsdaten-numerisch_current.csv.{YYYYMMDD}2100.zip

Full historic archive (single file, updated weekly)::

    https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/
    trockenheitsdaten-numerisch_historic/
    trockenheitsdaten-numerisch_historic.csv.zip
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from drought_forecast_eval.io.archive import BGDI_ARCHIVE_URL_TEMPLATE, BGDI_HISTORIC_URL

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1 << 16  # 64 KB


def _download_file(url: str, dest: Path, overwrite: bool = False) -> bool:
    """Download ``url`` to ``dest``.

    Returns ``True`` if the file was downloaded, ``False`` if it already
    existed and ``overwrite=False``.

    Raises
    ------
    requests.HTTPError
        On non-2xx HTTP responses.
    """
    if dest.exists() and not overwrite:
        logger.debug("Already exists, skipping: %s", dest.name)
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s → %s", url, dest)

    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
                f.write(chunk)

    logger.info("Downloaded %s (%.1f KB)", dest.name, dest.stat().st_size / 1024)
    return True


def download_archive(
    dest_dir: str | Path,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Download daily rolling archive ZIPs from BGDI.

    Iterates every calendar day in ``[start, end]`` and tries to fetch the
    corresponding ZIP.  Missing days (404s) are silently skipped — not every
    day has a published archive.

    Parameters
    ----------
    dest_dir:
        Local directory where ZIPs will be stored (flat layout).
    start:
        First date to download.  Defaults to yesterday.
    end:
        Last date to download (inclusive).  Defaults to today.
    overwrite:
        Re-download files that already exist locally.

    Returns
    -------
    list of Path
        Paths of successfully downloaded files.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    start_date = _to_date(start) if start is not None else today - timedelta(days=1)
    end_date = _to_date(end) if end is not None else today

    if start_date > end_date:
        raise ValueError(f"start ({start_date}) is after end ({end_date})")

    downloaded: list[Path] = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y%m%d")
        url = BGDI_ARCHIVE_URL_TEMPLATE.format(date_str=date_str)
        filename = f"trockenheitsdaten-numerisch_current.csv.{date_str}2100.zip"
        dest = dest_dir / filename
        try:
            if _download_file(url, dest, overwrite=overwrite):
                downloaded.append(dest)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.debug("No archive for %s (404 — expected for non-publication days)", current)
            else:
                logger.warning("HTTP error for %s: %s", current, exc)
        except requests.RequestException as exc:
            logger.warning("Network error for %s: %s", current, exc)
        current += timedelta(days=1)

    logger.info("Downloaded %d archive file(s) to %s", len(downloaded), dest_dir)
    return downloaded


def download_historic(
    dest_path: str | Path,
    overwrite: bool = False,
) -> Path:
    """Download the full historic observation archive from BGDI.

    Parameters
    ----------
    dest_path:
        Local file path where the ZIP will be saved, e.g.
        ``/data/historic/trockenheitsdaten-numerisch_historic.csv.zip``.
    overwrite:
        Re-download if the file already exists.

    Returns
    -------
    Path
        The path to the downloaded file.
    """
    dest_path = Path(dest_path)
    _download_file(BGDI_HISTORIC_URL, dest_path, overwrite=overwrite)
    return dest_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_date(value: str | date | datetime) -> date:
    """Coerce various date representations to ``datetime.date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    # Try ISO first, then DD.MM.YYYY
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}. Expected YYYY-MM-DD or DD.MM.YYYY.")

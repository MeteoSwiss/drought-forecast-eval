"""Shared pytest fixtures.

All fixtures that create expensive objects (xr.Dataset) are session-scoped
so they are built once per test run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make sure the package is importable when running tests from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ARCHIVE_DIR = FIXTURE_DIR            # ZIPs live directly in fixtures/
HISTORIC_ZIP = FIXTURE_DIR / "trockenheitsdaten-numerisch_historic.csv.zip"


# ---------------------------------------------------------------------------
# Auto-generate fixtures if they don't exist
# ---------------------------------------------------------------------------

def pytest_configure(config):  # noqa: ANN001
    """Generate fixture files if they are missing."""
    fixture_zips = list(FIXTURE_DIR.glob("*.zip"))
    if not fixture_zips:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(FIXTURE_DIR / "make_fixtures.py")],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.exit(f"Failed to generate fixtures:\n{result.stderr}", returncode=1)


# ---------------------------------------------------------------------------
# Session-scoped dataset fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ds_fcst():
    """Load the fixture forecast dataset."""
    from drought_forecast_eval.io.loader import load_forecasts
    return load_forecasts(ARCHIVE_DIR)


@pytest.fixture(scope="session")
def ds_obs():
    """Load the fixture observation dataset (historic only)."""
    from drought_forecast_eval.io.loader import load_observations
    return load_observations(HISTORIC_ZIP)


@pytest.fixture(scope="session")
def ds_obs_combined():
    """Combined observation dataset: historic ZIP merged with latest current ZIP."""
    from drought_forecast_eval.io.loader import load_observations_combined
    return load_observations_combined(HISTORIC_ZIP, ARCHIVE_DIR)


@pytest.fixture(scope="session")
def ds_merged(ds_fcst, ds_obs_combined):
    """Merged forecast+observation dataset (uses combined obs for full coverage)."""
    from drought_forecast_eval.processing.alignment import align_obs_to_forecast
    return align_obs_to_forecast(ds_fcst, ds_obs_combined)


@pytest.fixture(scope="session")
def ds_clim_ref(ds_obs_combined, ds_fcst):
    """Climatology reference dataset."""
    from drought_forecast_eval.processing.reference import climatology_reference
    return climatology_reference(ds_obs_combined, ds_fcst, week_window=2)


@pytest.fixture(scope="session")
def ds_pers_ref(ds_obs_combined, ds_fcst):
    """Persistence reference dataset."""
    from drought_forecast_eval.processing.reference import persistence_reference
    return persistence_reference(ds_obs_combined, ds_fcst)


@pytest.fixture(scope="session")
def ds_scores(ds_merged, ds_clim_ref):
    """Scores dataset (default metrics, climatology reference)."""
    from drought_forecast_eval.scoring.dispatcher import compute_scores
    return compute_scores(ds_merged, variables="all", scores="default", ds_ref=ds_clim_ref)

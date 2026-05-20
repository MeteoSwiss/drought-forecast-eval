"""Global configuration and default values.

All settings can be overridden by passing arguments directly to the
library functions.  This module provides the authoritative defaults so
that values are defined in exactly one place.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# BGDI data URLs (public, no authentication required)
# ---------------------------------------------------------------------------

BGDI_ARCHIVE_URL_TEMPLATE: str = (
    "https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/"
    "trockenheitsdaten-numerisch_current/"
    "trockenheitsdaten-numerisch_current.csv.{date_str}2100.zip"
)

BGDI_HISTORIC_URL: str = (
    "https://data.geo.admin.ch/ch.bafu.trockenheitsdaten-numerisch/"
    "trockenheitsdaten-numerisch_historic/"
    "trockenheitsdaten-numerisch_historic.csv.zip"
)

# ---------------------------------------------------------------------------
# Drought regions
# ---------------------------------------------------------------------------

#: The 38 official drought warning regions (IDs 1–38).
#: Source: http://drought.admin.ch
ALL_REGION_IDS: list[int] = list(range(1, 39))

# ---------------------------------------------------------------------------
# Default variable selection
# ---------------------------------------------------------------------------

#: Variables included when ``variables="all"`` is requested.
#: Mirrors the keys of ``VARIABLE_MAP``.
DEFAULT_VARIABLES: list[str] = [
    # Deterministic
    "cdi",
    "precip_1m_index",
    "precip_3m_index",
    "precip_24m_index",
    "hydro_index",
    "soil_moisture_index",
    # Quantile
    "precip_sum_1m",
    "precip_sum_3m",
    "precip_sum_6m",
    "precip_sum_12m",
    "precip_sum_24m",
    "spi_1m",
    "spi_3m",
    "spi_6m",
    "spi_12m",
    "spi_24m",
    "soil_moisture_ufc",
]

# ---------------------------------------------------------------------------
# Default score selection
# ---------------------------------------------------------------------------

#: Scores applied when ``scores="default"`` is requested.
DEFAULT_SCORES: list[str] = [
    "mae",
    "rmse",
    "bias",
    "correlation",
    "pinball",        # quantile variables only
    "interval_score", # quantile variables only
]

# ---------------------------------------------------------------------------
# Reference forecast settings
# ---------------------------------------------------------------------------

#: Default half-width (in weeks) of the week-of-year window used in
#: climatology_reference.
DEFAULT_WEEK_WINDOW: int = 4

#: Default CDI threshold for binary drought event (ROC-AUC).
DEFAULT_CDI_THRESHOLD: float = 2.0

# ---------------------------------------------------------------------------
# Lead-week range
# ---------------------------------------------------------------------------

#: Expected lead weeks in the forecast archive (0 = current week).
LEAD_WEEKS: list[int] = [0, 1, 2, 3]

# ---------------------------------------------------------------------------
# Shapefile
# ---------------------------------------------------------------------------

#: Path to the bundled BAFU drought-region shapefile (relative to project root).
DEFAULT_SHAPEFILE: str = "shapefiles/BAFU_Grossregionen_v3.shp"

#: Attribute column in the shapefile that holds the integer region ID.
DEFAULT_SHAPEFILE_REGION_COL: str = "REGION_NR"

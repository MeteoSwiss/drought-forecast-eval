"""Schema definitions and validation for forecast and observation CSV files.

Both schemas are defined as dicts mapping column name → expected pandas dtype.
Validation emits warnings on unexpected columns (forward-compatibility) and
raises ``SchemaError`` on missing required columns or unparseable types.
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd


class SchemaError(ValueError):
    """Raised when a DataFrame does not conform to the expected schema."""


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

#: Required columns for ``weekly_forecast_regions.csv`` and their dtypes.
FORECAST_SCHEMA: dict[str, Any] = {
    "drought_region_id": "int64",
    "valid_at": "datetime64[ns]",
    # CDI and index medians (deterministic)
    "cdi_p50": "float64",
    "precip_1m_index_p50": "float64",
    "precip_3m_index_p50": "float64",
    "precip_24m_index_p50": "float64",
    "hydro_index_p50": "float64",
    "soil_moisture_index_p50": "float64",
    # Raw precipitation sums (quantiles)
    "precip_sum_1m_p10": "float64",
    "precip_sum_1m_p50": "float64",
    "precip_sum_1m_p90": "float64",
    "precip_sum_3m_p10": "float64",
    "precip_sum_3m_p50": "float64",
    "precip_sum_3m_p90": "float64",
    "precip_sum_6m_p10": "float64",
    "precip_sum_6m_p50": "float64",
    "precip_sum_6m_p90": "float64",
    "precip_sum_12m_p10": "float64",
    "precip_sum_12m_p50": "float64",
    "precip_sum_12m_p90": "float64",
    "precip_sum_24m_p10": "float64",
    "precip_sum_24m_p50": "float64",
    "precip_sum_24m_p90": "float64",
    # SPI quantiles
    "spi_1m_p10": "float64",
    "spi_1m_p50": "float64",
    "spi_1m_p90": "float64",
    "spi_3m_p10": "float64",
    "spi_3m_p50": "float64",
    "spi_3m_p90": "float64",
    "spi_6m_p10": "float64",
    "spi_6m_p50": "float64",
    "spi_6m_p90": "float64",
    "spi_12m_p10": "float64",
    "spi_12m_p50": "float64",
    "spi_12m_p90": "float64",
    "spi_24m_p10": "float64",
    "spi_24m_p50": "float64",
    "spi_24m_p90": "float64",
    # Soil moisture (quantiles)
    "soil_moisture_ufc_p10": "float64",
    "soil_moisture_ufc_p50": "float64",
    "soil_moisture_ufc_p90": "float64",
}

#: Required columns for ``weekly_historic_regions.csv`` and their dtypes.
OBSERVATION_SCHEMA: dict[str, Any] = {
    "drought_region_id": "int64",
    "measured_at": "datetime64[ns]",
    # CDI and indices
    "cdi": "float64",
    "precip_1m_index": "float64",
    "precip_3m_index": "float64",
    "precip_24m_index": "float64",
    "hydro_index": "float64",
    "soil_moisture_index": "float64",
    # Raw precipitation sums
    "precip_sum_1m": "float64",
    "precip_sum_3m": "float64",
    "precip_sum_6m": "float64",
    "precip_sum_12m": "float64",
    "precip_sum_24m": "float64",
    # SPI
    "spi_1m": "float64",
    "spi_3m": "float64",
    "spi_6m": "float64",
    "spi_12m": "float64",
    "spi_24m": "float64",
    # Soil moisture
    "soil_moisture_ufc": "float64",
    # Vegetation health index (nice to have, not in variable map)
    "vhi": "float64",
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _parse_date_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Parse a date column that may be in DD.MM.YYYY or YYYY-MM-DD format."""
    df = df.copy()
    raw = df[col].astype(str).str.strip()
    # Try ISO first, then European
    parsed = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
    mask_failed = parsed.isna()
    if mask_failed.any():
        parsed[mask_failed] = pd.to_datetime(
            raw[mask_failed], format="%d.%m.%Y", errors="coerce"
        )
    if parsed.isna().any():
        bad = raw[parsed.isna()].unique()[:5].tolist()
        raise SchemaError(
            f"Column '{col}' contains unparseable dates: {bad}. "
            "Expected formats: YYYY-MM-DD or DD.MM.YYYY."
        )
    df[col] = parsed
    return df


def validate_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and coerce a raw forecast DataFrame to the expected schema.

    Parameters
    ----------
    df:
        Raw DataFrame read from ``weekly_forecast_regions.csv``.

    Returns
    -------
    pd.DataFrame
        Validated and type-coerced DataFrame.

    Raises
    ------
    SchemaError
        If required columns are missing or contain unparseable values.
    """
    return _validate(df, FORECAST_SCHEMA, date_col="valid_at", context="forecast")


def validate_observation(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and coerce a raw observation DataFrame to the expected schema.

    Parameters
    ----------
    df:
        Raw DataFrame read from ``weekly_historic_regions.csv``.

    Returns
    -------
    pd.DataFrame
        Validated and type-coerced DataFrame.

    Raises
    ------
    SchemaError
        If required columns are missing or contain unparseable values.
    """
    return _validate(df, OBSERVATION_SCHEMA, date_col="measured_at", context="observation")


def _validate(
    df: pd.DataFrame,
    schema: dict[str, Any],
    date_col: str,
    context: str,
) -> pd.DataFrame:
    """Run internal validation shared by forecast and observation paths."""
    df = df.copy()

    # --- Check for missing required columns ---
    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise SchemaError(
            f"[{context}] Missing required columns: {missing}. "
            f"Got columns: {sorted(df.columns.tolist())}"
        )

    # --- Warn on unexpected columns (forward-compatibility) ---
    extra = [c for c in df.columns if c not in schema]
    if extra:
        warnings.warn(
            f"[{context}] Unexpected columns found (possible CSV format change): {extra}. "
            "These columns will be retained but not validated.",
            UserWarning,
            stacklevel=3,
        )

    # --- Parse date column ---
    df = _parse_date_column(df, date_col)

    # --- Coerce numeric columns ---
    for col, dtype in schema.items():
        if col == date_col:
            continue
        if dtype == "int64":
            try:
                df[col] = pd.to_numeric(df[col], errors="raise").astype("int64")
            except (ValueError, TypeError) as exc:
                raise SchemaError(
                    f"[{context}] Column '{col}' could not be coerced to int64."
                ) from exc
        elif dtype == "float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    return df

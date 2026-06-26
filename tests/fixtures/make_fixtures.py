"""Script to (re-)generate test fixture CSV and ZIP files.

Run once from the repo root:
    python tests/fixtures/make_fixtures.py

Generates:
    tests/fixtures/sample_forecast.zip  – contains weekly_forecast_regions.csv
    tests/fixtures/sample_historic.zip  – contains weekly_historic_regions.csv
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

REGIONS = [31, 35, 50, 68]   # 4 representative regions (real IDs 31–68)
LEAD_WEEKS_OFFSET = [0, 7, 14, 21]  # days → week 0/1/2/3
FIXTURE_DIR = Path(__file__).parent

# Forecast reference time used in the fixture filename
FRT = pd.Timestamp("2026-03-24")  # Tuesday

# The historic fixture ends here; current fixture adds rows beyond this date
_HISTORIC_CUTOFF = pd.Timestamp("2026-03-09")  # last Monday in historic

# ---------------------------------------------------------------------------
# Forecast fixture
# ---------------------------------------------------------------------------

def make_forecast_df() -> pd.DataFrame:
    rows = []
    for region in REGIONS:
        for delta_days in LEAD_WEEKS_OFFSET:
            valid_at = FRT - pd.Timedelta(days=FRT.weekday()) + pd.Timedelta(days=delta_days)
            base = RNG.uniform(-1.5, 1.5)
            rows.append({
                "drought_region_id": region,
                "valid_at": valid_at.strftime("%d.%m.%Y"),
                "cdi_p50": round(RNG.uniform(1, 4), 1),
                "precip_1m_index_p50": round(base, 2),
                "precip_3m_index_p50": round(base + RNG.normal(0, 0.2), 2),
                "precip_24m_index_p50": round(base + RNG.normal(0, 0.3), 2),
                "hydro_index_p50": round(RNG.uniform(-2, 2), 2),
                "soil_moisture_index_p50": round(RNG.uniform(-2, 2), 2),
                # precip sums
                "precip_sum_1m_p10": round(max(0, 30 + RNG.normal(-10, 5)), 1),
                "precip_sum_1m_p50": round(max(0, 40 + RNG.normal(0, 5)), 1),
                "precip_sum_1m_p90": round(max(0, 50 + RNG.normal(10, 5)), 1),
                "precip_sum_3m_p10": round(max(0, 100 + RNG.normal(-15, 10)), 1),
                "precip_sum_3m_p50": round(max(0, 120 + RNG.normal(0, 10)), 1),
                "precip_sum_3m_p90": round(max(0, 140 + RNG.normal(15, 10)), 1),
                "precip_sum_6m_p10": round(max(0, 200 + RNG.normal(-20, 15)), 1),
                "precip_sum_6m_p50": round(max(0, 240 + RNG.normal(0, 15)), 1),
                "precip_sum_6m_p90": round(max(0, 280 + RNG.normal(20, 15)), 1),
                "precip_sum_12m_p10": round(max(0, 500 + RNG.normal(-30, 20)), 1),
                "precip_sum_12m_p50": round(max(0, 600 + RNG.normal(0, 20)), 1),
                "precip_sum_12m_p90": round(max(0, 700 + RNG.normal(30, 20)), 1),
                "precip_sum_24m_p10": round(max(0, 1100 + RNG.normal(-50, 30)), 1),
                "precip_sum_24m_p50": round(max(0, 1200 + RNG.normal(0, 30)), 1),
                "precip_sum_24m_p90": round(max(0, 1300 + RNG.normal(50, 30)), 1),
                # SPI
                "spi_1m_p10": round(base - 0.5, 2),
                "spi_1m_p50": round(base, 2),
                "spi_1m_p90": round(base + 0.5, 2),
                "spi_3m_p10": round(base - 0.4, 2),
                "spi_3m_p50": round(base + 0.1, 2),
                "spi_3m_p90": round(base + 0.4, 2),
                "spi_6m_p10": round(base - 0.3, 2),
                "spi_6m_p50": round(base + 0.05, 2),
                "spi_6m_p90": round(base + 0.3, 2),
                "spi_12m_p10": round(base - 0.6, 2),
                "spi_12m_p50": round(base, 2),
                "spi_12m_p90": round(base + 0.6, 2),
                "spi_24m_p10": round(base - 0.8, 2),
                "spi_24m_p50": round(base, 2),
                "spi_24m_p90": round(base + 0.8, 2),
                # soil moisture
                "soil_moisture_ufc_p10": round(RNG.uniform(85, 90), 1),
                "soil_moisture_ufc_p50": round(RNG.uniform(90, 95), 1),
                "soil_moisture_ufc_p90": round(RNG.uniform(95, 100), 1),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Historic (observation) fixture – 3 years of weekly obs up to _HISTORIC_CUTOFF
# ---------------------------------------------------------------------------

def make_historic_df() -> pd.DataFrame:
    rows = []
    start = pd.Timestamp("2023-01-02")  # first Monday
    end = _HISTORIC_CUTOFF
    monday = start
    while monday <= end:
        for region in REGIONS:
            base = RNG.uniform(-1.5, 1.5)
            rows.append({
                "drought_region_id": region,
                "measured_at": monday.strftime("%Y-%m-%d"),
                "cdi": round(RNG.uniform(1, 4), 1),
                "precip_1m_index": round(base, 2),
                "precip_3m_index": round(base + RNG.normal(0, 0.2), 2),
                "precip_24m_index": round(base + RNG.normal(0, 0.3), 2),
                "hydro_index": round(RNG.uniform(-2, 2), 2),
                "soil_moisture_index": round(RNG.uniform(-2, 2), 2),
                "precip_sum_1m": round(max(0, 40 + RNG.normal(0, 10)), 1),
                "precip_sum_3m": round(max(0, 120 + RNG.normal(0, 20)), 1),
                "precip_sum_6m": round(max(0, 240 + RNG.normal(0, 30)), 1),
                "precip_sum_12m": round(max(0, 600 + RNG.normal(0, 50)), 1),
                "precip_sum_24m": round(max(0, 1200 + RNG.normal(0, 80)), 1),
                "spi_1m": round(base, 2),
                "spi_3m": round(base + RNG.normal(0, 0.2), 2),
                "spi_6m": round(base + RNG.normal(0, 0.3), 2),
                "spi_12m": round(base + RNG.normal(0, 0.4), 2),
                "spi_24m": round(base + RNG.normal(0, 0.5), 2),
                "soil_moisture_ufc": round(RNG.uniform(85, 100), 1),
                "vhi": round(RNG.uniform(0.2, 0.9), 3),
            })
        monday += pd.Timedelta(weeks=1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Current (observation) fixture – 52-week rolling window ending at FRT week
#
# Covers _HISTORIC_CUTOFF − 51 weeks → FRT week, so it overlaps slightly with
# the historic fixture and also extends two weeks beyond it.  This exercises
# both the deduplication (overlap) and the gap-fill (extension) logic.
# ---------------------------------------------------------------------------

def make_current_obs_df() -> pd.DataFrame:
    """Build a weekly_current_regions.csv-style DataFrame.

    Starts 51 weeks before _HISTORIC_CUTOFF so there is deliberate overlap
    with the historic fixture, then continues two more Mondays beyond it.
    """
    rows = []
    start = _HISTORIC_CUTOFF - pd.Timedelta(weeks=51)
    end = _HISTORIC_CUTOFF + pd.Timedelta(weeks=2)  # two weeks beyond historic
    monday = start
    while monday <= end:
        for region in REGIONS:
            base = RNG.uniform(-1.5, 1.5)
            rows.append({
                "drought_region_id": region,
                "measured_at": monday.strftime("%d.%m.%Y"),  # real files use DD.MM.YYYY
                "cdi": round(RNG.uniform(1, 4), 1),
                "precip_1m_index": round(base, 2),
                "precip_3m_index": round(base + RNG.normal(0, 0.2), 2),
                "precip_24m_index": round(base + RNG.normal(0, 0.3), 2),
                "hydro_index": round(RNG.uniform(-2, 2), 2),
                "soil_moisture_index": round(RNG.uniform(-2, 2), 2),
                "precip_sum_1m": round(max(0, 40 + RNG.normal(0, 10)), 1),
                "precip_sum_3m": round(max(0, 120 + RNG.normal(0, 20)), 1),
                "precip_sum_6m": round(max(0, 240 + RNG.normal(0, 30)), 1),
                "precip_sum_12m": round(max(0, 600 + RNG.normal(0, 50)), 1),
                "precip_sum_24m": round(max(0, 1200 + RNG.normal(0, 80)), 1),
                "spi_1m": round(base, 2),
                "spi_3m": round(base + RNG.normal(0, 0.2), 2),
                "spi_6m": round(base + RNG.normal(0, 0.3), 2),
                "spi_12m": round(base + RNG.normal(0, 0.4), 2),
                "spi_24m": round(base + RNG.normal(0, 0.5), 2),
                "soil_moisture_ufc": round(RNG.uniform(85, 100), 1),
                "vhi": round(RNG.uniform(0.2, 0.9), 3),
            })
        monday += pd.Timedelta(weeks=1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Write ZIPs
# ---------------------------------------------------------------------------

def _df_to_csv_bytes(df: pd.DataFrame, header_date: str, extra_header: str = "") -> bytes:
    """Serialize a DataFrame to CSV bytes with the expected comment header."""
    header = (
        f"# letzte Aktualisierung: {header_date}\n"
        "# https://trockenheit.admin.ch\n"
        "# © Bundesbehörden der Schweizerischen Eidgenossenschaft\n"
    )
    if extra_header:
        header += extra_header + "\n"
    csv_str = df.to_csv(index=False)
    return (header + csv_str).encode("utf-8")


def make_fixtures() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    # --- Forecast ZIP (filename encodes the FRT) ---
    frt_str = FRT.strftime("%Y%m%d")
    fcst_zip_path = FIXTURE_DIR / f"trockenheitsdaten-numerisch_current.csv.{frt_str}2100.zip"
    fcst_df = make_forecast_df()
    fcst_bytes = _df_to_csv_bytes(fcst_df, FRT.strftime("%d.%m.%Y"))
    with zipfile.ZipFile(fcst_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("weekly_forecast_regions.csv", fcst_bytes.decode("utf-8"))
    print(f"Written: {fcst_zip_path}")

    # --- A second forecast ZIP one week earlier (for multi-FRT tests) ---
    frt2 = FRT - pd.Timedelta(weeks=1)
    frt2_str = frt2.strftime("%Y%m%d")
    fcst_zip_path2 = FIXTURE_DIR / f"trockenheitsdaten-numerisch_current.csv.{frt2_str}2100.zip"
    fcst_df2 = make_forecast_df()
    # Shift valid_at by -1 week
    fcst_df2["valid_at"] = pd.to_datetime(
        fcst_df["valid_at"], format="%d.%m.%Y"
    ).sub(pd.Timedelta(weeks=1)).dt.strftime("%d.%m.%Y")
    fcst_bytes2 = _df_to_csv_bytes(fcst_df2, frt2.strftime("%d.%m.%Y"))
    with zipfile.ZipFile(fcst_zip_path2, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("weekly_forecast_regions.csv", fcst_bytes2.decode("utf-8"))
    print(f"Written: {fcst_zip_path2}")

    # --- Historic (observation) ZIP ---
    hist_zip_path = FIXTURE_DIR / "trockenheitsdaten-numerisch_historic.csv.zip"
    hist_df = make_historic_df()
    hist_bytes = _df_to_csv_bytes(hist_df, _HISTORIC_CUTOFF.strftime("%d.%m.%Y"))
    with zipfile.ZipFile(hist_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("weekly_historic_regions.csv", hist_bytes.decode("utf-8"))
    print(f"Written: {hist_zip_path}")

    # --- Current (observation) ZIP bundled inside the latest forecast ZIP ---
    # The latest forecast ZIP (FRT) also contains weekly_current_regions.csv.
    # Re-open it and add the current obs CSV alongside the forecast CSV.
    curr_obs_df = make_current_obs_df()
    curr_obs_bytes = _df_to_csv_bytes(curr_obs_df, FRT.strftime("%d.%m.%Y"))
    # Append to the already-written latest forecast ZIP
    with zipfile.ZipFile(fcst_zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("weekly_current_regions.csv", curr_obs_bytes.decode("utf-8"))
    print(f"Updated with current obs: {fcst_zip_path}")

    print("Fixtures generated successfully.")


if __name__ == "__main__":
    make_fixtures()

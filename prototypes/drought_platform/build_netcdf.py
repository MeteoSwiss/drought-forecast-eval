"""Build the NetCDF inputs of the prototype from the raw BGDI ZIP archives.

Run from the repo root:
    poetry run python prototypes/drought_platform/build_netcdf.py \
        --archive data/zipfiles --historic data/historic.csv.zip

Writes data/netcdf/merged.nc and data/netcdf/observations_<today>.nc, the same
files that notebooks/verification_summer2026.ipynb produces.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from drought_forecast_eval import align_obs_to_forecast
from drought_forecast_eval.io.loader import load_forecasts, load_observations_combined


def main() -> None:
    """Load the ZIP archives, align observations to forecasts and write NetCDF."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--archive",
        type=Path,
        default=Path("data/zipfiles"),
        help="folder of daily *_current.csv.YYYYMMDD2100.zip files",
    )
    ap.add_argument(
        "--historic",
        type=Path,
        default=Path("data/historic.csv.zip"),
        help="historic observation archive",
    )
    ap.add_argument("--out", type=Path, default=Path("data/netcdf"), help="output folder")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    args.out.mkdir(parents=True, exist_ok=True)
    ds_fcst = load_forecasts(args.archive)
    ds_obs = load_observations_combined(args.historic, archive_dir=args.archive)
    obs_path = args.out / f"observations_{date.today():%Y-%m-%d}.nc"
    ds_obs.to_netcdf(obs_path)
    align_obs_to_forecast(ds_fcst, ds_obs).to_netcdf(args.out / "merged.nc")
    print(f"wrote {args.out / 'merged.nc'} and {obs_path}")


if __name__ == "__main__":
    main()

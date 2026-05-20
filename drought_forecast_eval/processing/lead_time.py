"""Lead-time utilities.

The drought forecast is issued daily but ``valid_at`` always encodes the
Monday of the target week.  Lead time is therefore expressed as an integer
week offset (0, 1, 2, 3) relative to the Monday of the week in which
``forecast_reference_time`` falls.

Examples
--------
>>> import pandas as pd
>>> from drought_forecast_eval.processing.lead_time import compute_lead_weeks
>>> frt = pd.Timestamp("2026-03-24")          # Tuesday
>>> valid_at = pd.Series([pd.Timestamp("2026-03-23"),   # Monday of the same week → week 0
...                       pd.Timestamp("2026-03-30"),   # next Monday → week 1
...                       pd.Timestamp("2026-04-06")])  # week 2
>>> compute_lead_weeks(valid_at, frt).tolist()
[0, 1, 2]
"""

from __future__ import annotations

import pandas as pd


def _monday_of_week(ts: pd.Timestamp) -> pd.Timestamp:
    """Return the Monday of the ISO week containing ``ts``."""
    return ts - pd.Timedelta(days=ts.weekday())


def compute_lead_weeks(
    valid_at: pd.Series,
    forecast_reference_time: pd.Timestamp | str,
) -> pd.Series:
    """Compute integer lead-week offsets.

    Parameters
    ----------
    valid_at:
        Series of ``datetime64`` values representing the Monday of each
        forecast target week.
    forecast_reference_time:
        The issue datetime of the forecast (any weekday).

    Returns
    -------
    pd.Series of int
        Integer lead weeks (0, 1, 2, 3, …).  Negative values indicate
        that ``valid_at`` precedes the issue week (can occur for the
        "analysis" row in some dumps); these are **retained** so callers
        can decide how to handle them.
    """
    frt = pd.Timestamp(forecast_reference_time)
    frt_monday = _monday_of_week(frt)

    valid_at = pd.to_datetime(valid_at)
    delta_days = (valid_at - frt_monday).dt.days
    lead_weeks = (delta_days / 7).round().astype(int)
    return lead_weeks

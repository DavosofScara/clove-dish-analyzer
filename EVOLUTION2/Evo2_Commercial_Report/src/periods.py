"""
Season and weekly windows for the Evolution2 weekly automation report.

- Week: Monday → Sunday (completed week when the report runs on Monday).
- HIVER: 15 November → 30 April (spans two calendar years).
- ÉTÉ: 1 May → 14 November.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Tuple


@dataclass(frozen=True)
class SeasonPeriod:
    """Inclusive date bounds and a short French label."""

    start: date
    end: date
    label: str


def previous_completed_week(as_of: date) -> Tuple[date, date]:
    """
    Monday–Sunday week ending on the **most recent Sunday on or before** ``as_of``.

    - **Monday** ``as_of``: that Sunday is yesterday → same as “semaine précédente”.
    - **Sunday** ``as_of``: that Sunday is today → KPIs are for **this** Mon–Sun block
      (e.g. 30/03–05/04), not the week before — avoids being one week early when the
      job runs on a Sunday or ``--as-of`` is a Sunday.

    Uses ``(weekday + 1) % 7`` so Sunday (weekday 6) subtracts 0 days, not 7.
    """
    d = as_of.date() if hasattr(as_of, "date") and callable(getattr(as_of, "date")) else as_of

    days_back = (d.weekday() + 1) % 7
    week_end_sunday = d - timedelta(days=days_back)
    week_start_monday = week_end_sunday - timedelta(days=6)
    return week_start_monday, week_end_sunday


def season_containing(d: date) -> SeasonPeriod:
    """
    Season that contains calendar date `d`.

    Examples:
    - 17 Nov 2025 → HIVER 25/26 (15 Nov 2025 – 30 Apr 2026)
    - 3 May 2026 → ÉTÉ 26 (1 May 2026 – 14 Nov 2026)
    """
    m, day = d.month, d.day
    yy = lambda y: str(y)[-2:]

    if (m == 11 and day >= 15) or m == 12:
        start = date(d.year, 11, 15)
        end = date(d.year + 1, 4, 30)
        return SeasonPeriod(start, end, f"HIVER {yy(d.year)}/{yy(d.year + 1)}")
    if m < 5 or (m == 4 and day <= 30):
        start = date(d.year - 1, 11, 15)
        end = date(d.year, 4, 30)
        return SeasonPeriod(start, end, f"HIVER {yy(d.year - 1)}/{yy(d.year)}")
    start = date(d.year, 5, 1)
    end = date(d.year, 11, 14)
    return SeasonPeriod(start, end, f"ÉTÉ {yy(d.year)}")


def next_season_after(current: SeasonPeriod) -> SeasonPeriod:
    """
    Season immediately following `current` (no gap between seasons).

    HIVER 25/26 → ÉTÉ 26; ÉTÉ 26 → HIVER 26/27.
    """
    yy = lambda y: str(y)[-2:]
    if current.label.startswith("HIVER"):
        y = current.end.year
        start = date(y, 5, 1)
        end = date(y, 11, 14)
        return SeasonPeriod(start, end, f"ÉTÉ {yy(y)}")
    y = current.end.year
    start = date(y, 11, 15)
    end = date(y + 1, 4, 30)
    return SeasonPeriod(start, end, f"HIVER {yy(y)}/{yy(y + 1)}")


def previous_season_before(current: SeasonPeriod) -> SeasonPeriod:
    """
    Previous season of the **same type** (YoY): winter vs winter, summer vs summer.

    HIVER 25/26 → HIVER 24/25; ÉTÉ 26 → ÉTÉ 25.
    """
    yy = lambda y: str(y)[-2:]
    if current.label.startswith("HIVER"):
        y0 = current.start.year
        start = date(y0 - 1, 11, 15)
        end = date(y0, 4, 30)
        return SeasonPeriod(start, end, f"HIVER {yy(y0 - 1)}/{yy(y0)}")
    y0 = current.start.year
    start = date(y0 - 1, 5, 1)
    end = date(y0 - 1, 11, 14)
    return SeasonPeriod(start, end, f"ÉTÉ {yy(y0 - 1)}")


def season_window_for_metrics(season: SeasonPeriod, as_of: date) -> Tuple[date, date]:
    """
    Inclusive [start, end] for KPIs: from season start through min(as_of, season end).
    """
    end_cap = min(as_of, season.end)
    if end_cap < season.start:
        return season.start, season.start
    return season.start, end_cap


def date_in_range(d, start: date, end: date) -> bool:
    """True if calendar date of d falls in [start, end] inclusive."""
    import pandas as pd

    if d is None or pd.isna(d):
        return False
    if hasattr(d, "date") and callable(getattr(d, "date")):
        cd = d.date()
    elif isinstance(d, date):
        cd = d
    else:
        return False
    return start <= cd <= end

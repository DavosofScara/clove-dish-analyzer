"""
Season and weekly windows for the Evolution2 weekly automation report.

Fiscal calendar (aligned with Evolution2 fiscal year):
- Week: Monday → Sunday (completed week when the report runs on Monday).
- HIVER: 1 October → 30 April (spans two calendar years).
- ÉTÉ: 1 May → 30 September.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Tuple

# Fiscal season bounds (inclusive)
ETE_START_MONTH, ETE_START_DAY = 5, 1
ETE_END_MONTH, ETE_END_DAY = 9, 30
HIVER_START_MONTH, HIVER_START_DAY = 10, 1
HIVER_END_MONTH, HIVER_END_DAY = 4, 30


@dataclass(frozen=True)
class SeasonPeriod:
    """Inclusive date bounds and a short French label."""

    start: date
    end: date
    label: str


def ete_bounds(year: int) -> tuple[date, date]:
    """ÉTÉ fiscal season for calendar year ``year`` (May 1 – Sep 30)."""
    return date(year, ETE_START_MONTH, ETE_START_DAY), date(year, ETE_END_MONTH, ETE_END_DAY)


def hiver_bounds(start_year: int) -> tuple[date, date]:
    """HIVER fiscal season starting October ``start_year`` (Oct 1 – Apr 30)."""
    return (
        date(start_year, HIVER_START_MONTH, HIVER_START_DAY),
        date(start_year + 1, HIVER_END_MONTH, HIVER_END_DAY),
    )


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
    Fiscal season that contains calendar date ``d``.

    Examples:
    - 17 Nov 2025 → HIVER 25/26 (1 Oct 2025 – 30 Apr 2026)
    - 3 May 2026 → ÉTÉ 26 (1 May 2026 – 30 Sep 2026)
    - 15 Oct 2026 → HIVER 26/27 (1 Oct 2026 – 30 Apr 2027)
    """
    m = d.month
    yy = lambda y: str(y)[-2:]

    if ETE_START_MONTH <= m <= ETE_END_MONTH:
        start, end = ete_bounds(d.year)
        return SeasonPeriod(start, end, f"ÉTÉ {yy(d.year)}")
    if m >= HIVER_START_MONTH:
        start, end = hiver_bounds(d.year)
        return SeasonPeriod(start, end, f"HIVER {yy(d.year)}/{yy(d.year + 1)}")
    start, end = hiver_bounds(d.year - 1)
    return SeasonPeriod(start, end, f"HIVER {yy(d.year - 1)}/{yy(d.year)}")


def next_season_after(current: SeasonPeriod) -> SeasonPeriod:
    """
    Season immediately following ``current``.

    HIVER 25/26 → ÉTÉ 26; ÉTÉ 26 → HIVER 26/27.
    """
    yy = lambda y: str(y)[-2:]
    if current.label.startswith("HIVER"):
        y = current.end.year
        start, end = ete_bounds(y)
        return SeasonPeriod(start, end, f"ÉTÉ {yy(y)}")
    y = current.end.year
    start, end = hiver_bounds(y)
    return SeasonPeriod(start, end, f"HIVER {yy(y)}/{yy(y + 1)}")


def previous_season_before(current: SeasonPeriod) -> SeasonPeriod:
    """
    Previous season of the **same type** (YoY): winter vs winter, summer vs summer.

    HIVER 25/26 → HIVER 24/25; ÉTÉ 26 → ÉTÉ 25.
    """
    yy = lambda y: str(y)[-2:]
    if current.label.startswith("HIVER"):
        y0 = current.start.year
        start, end = hiver_bounds(y0 - 1)
        return SeasonPeriod(start, end, f"HIVER {yy(y0 - 1)}/{yy(y0)}")
    y0 = current.start.year
    start, end = ete_bounds(y0 - 1)
    return SeasonPeriod(start, end, f"ÉTÉ {yy(y0 - 1)}")


def fiscal_year_bounds(start_year: int) -> tuple[date, date]:
    """Fiscal year starting 1 October ``start_year`` through 30 September ``start_year + 1``."""
    return date(start_year, HIVER_START_MONTH, HIVER_START_DAY), date(
        start_year + 1, ETE_END_MONTH, ETE_END_DAY
    )


def fiscal_year_containing(d: date) -> SeasonPeriod:
    """
    Fiscal year (année en cours) containing calendar date ``d`` (1 Oct – 30 Sep).

    Examples:
    - 6 Jul 2026 → Année 25/26 (1 Oct 2025 – 30 Sep 2026)
    - 12 Oct 2026 → Année 26/27 (1 Oct 2026 – 30 Sep 2027)
    """
    yy = lambda y: str(y)[-2:]
    if d.month >= HIVER_START_MONTH:
        start, end = fiscal_year_bounds(d.year)
        return SeasonPeriod(start, end, f"Année {yy(d.year)}/{yy(d.year + 1)}")
    start, end = fiscal_year_bounds(d.year - 1)
    return SeasonPeriod(start, end, f"Année {yy(d.year - 1)}/{yy(d.year)}")


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

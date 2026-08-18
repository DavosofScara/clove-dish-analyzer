#!/usr/bin/env python3
"""
MUMMA Trend Diagnostic Report

An on-demand deep dive to run when the weekly report flags a downtrend. Where the
weekly report answers "what happened", this answers "why": it splits a revenue
movement into a traffic component and a spend component per location, then
localises it by daypart, category and product.

Reads the same processed files as the weekly report:
- revenue_ledger.csv (transaction level)

Genuine closures are excluded from like-for-like comparisons rather than being
allowed to masquerade as demand loss. Pass closure dates with --closure.

Example:
    python3 mumma_trend_diagnostic.py --closure 2026-08-12:Mumma
"""
from __future__ import annotations

import argparse
import base64
import difflib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Load environment variables from .env.local if it exists
try:
    from dotenv import load_dotenv

    ENV_FILE = Path(__file__).resolve().parent / ".env.local"
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

import pandas as pd
import plotly.graph_objects as go  # type: ignore
import plotly.io as pio  # type: ignore
from plotly.subplots import make_subplots  # type: ignore

try:
    import resend
    from resend import Emails

    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    resend = None
    Emails = None

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "mumma" / "processed"
REPORTS_DIR = REPO_ROOT / "reports" / "mumma"

LEDGER_PATH = DATA_DIR / "revenue_ledger.csv"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Kaleido drives a headless browser and logs every navigation at INFO.
for _noisy in ("kaleido", "choreographer", "logistro"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

pio.templates.default = "plotly_dark"

# Shared palette with the weekly report.
CLOVE_GREEN = "#16A34A"
PRIOR_GREY = "#808080"
NEGATIVE_RED = "#DC2626"
CHART_BG = "#F5F5F5"
CHART_FG = "#000000"

# Card-safe text colours for deltas on the dark background.
UP_TEXT = "#4ADE80"
DOWN_TEXT = "#F87171"
MUTED_TEXT = "#9CA3AF"

LEDGER_COLUMNS = [
    "row_uid",
    "transaction_datetime",
    "transaction_date",
    "sku",
    "item_name",
    "category",
    "stat_group",
    "quantity",
    "unit_price",
    "net_revenue",
    "tax_rate",
    "tax_name",
    "discount_amount",
    "comp_amount",
    "profile",
    "account",
    "location",
]

MAPPED_FIELDS = ["stat_group", "profile", "discount_amount", "comp_amount"]


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class Closure:
    day: date
    location: Optional[str]  # None means the whole business


@dataclass
class DiagnosticContext:
    period_start: date
    period_end: date  # inclusive
    current_year: int
    comparison_years: List[int]
    closures: List[Closure] = field(default_factory=list)

    @property
    def prior_year(self) -> int:
        return self.comparison_years[0]

    @property
    def label(self) -> str:
        return f"{self.period_start:%Y%m%d}_{self.period_end:%Y%m%d}"

    @property
    def period_caption(self) -> str:
        if self.period_start.month == self.period_end.month:
            return f"{self.period_start.day}\u2013{self.period_end.day} {self.period_end:%B %Y}"
        return f"{self.period_start:%-d %b} \u2013 {self.period_end:%-d %b %Y}"

    def window_for_year(self, year: int) -> Tuple[date, date]:
        return (
            date(year, self.period_start.month, self.period_start.day),
            date(year, self.period_end.month, self.period_end.day),
        )


def parse_closure(raw: str) -> Closure:
    """Parse a --closure value of the form YYYY-MM-DD or YYYY-MM-DD:Location."""
    if ":" in raw:
        day_part, location = raw.split(":", 1)
        location = location.strip() or None
    else:
        day_part, location = raw, None
    return Closure(day=datetime.strptime(day_part.strip(), "%Y-%m-%d").date(), location=location)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def load_ledger() -> pd.DataFrame:
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"Ledger not found at {LEDGER_PATH}")
    df = pd.read_csv(
        LEDGER_PATH,
        usecols=lambda c: c in LEDGER_COLUMNS,
        parse_dates=["transaction_datetime"],
        low_memory=False,
    )
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["day_of_month"] = df["transaction_date"].dt.day
    df["hour"] = df["transaction_datetime"].dt.hour
    # A ticket is one open account on one trading day.
    df["ticket_id"] = df["transaction_date"].dt.strftime("%Y%m%d") + "|" + df["account"].astype(str)
    return df


def determine_context(
    ledger: pd.DataFrame,
    start_arg: Optional[str],
    end_arg: Optional[str],
    years_back: int,
    closures: Sequence[Closure],
) -> DiagnosticContext:
    latest = ledger["transaction_date"].max().date()
    period_end = datetime.strptime(end_arg, "%Y-%m-%d").date() if end_arg else latest
    period_start = (
        datetime.strptime(start_arg, "%Y-%m-%d").date() if start_arg else period_end.replace(day=1)
    )
    current_year = period_end.year
    return DiagnosticContext(
        period_start=period_start,
        period_end=period_end,
        current_year=current_year,
        comparison_years=[current_year - offset for offset in range(1, years_back + 1)],
        closures=list(closures),
    )


def slice_year(df: pd.DataFrame, ctx: DiagnosticContext, year: int) -> pd.DataFrame:
    start, end = ctx.window_for_year(year)
    mask = (df["transaction_date"] >= pd.Timestamp(start)) & (
        df["transaction_date"] <= pd.Timestamp(end)
    )
    return df.loc[mask]


def apply_closure_mask(period: pd.DataFrame, ctx: DiagnosticContext) -> pd.DataFrame:
    """Drop rows matching a declared closure, in whichever year they appear.

    Masking is per location rather than per day so that a closure at one site does
    not discard the other site's genuine trade on the same date.
    """
    if not ctx.closures or period.empty:
        return period
    drop = pd.Series(False, index=period.index)
    for closure in ctx.closures:
        same_day = period["day_of_month"] == closure.day.day
        if closure.location is None:
            drop |= same_day
        else:
            drop |= same_day & (period["location"] == closure.location)
    return period[~drop]


def comparable_frame(
    df: pd.DataFrame, ctx: DiagnosticContext, year: int, location: Optional[str] = None
) -> pd.DataFrame:
    """Year slice with declared closures removed from both sides of the comparison."""
    period = slice_year(df, ctx, year)
    if location is not None:
        period = period[period["location"] == location]
    return apply_closure_mask(period, ctx)


def clean_label(value: str) -> str:
    """Lightspeed group names carry a numeric id, e.g. 'Cuisine(185052960915502)'."""
    return re.sub(r"\s*\(\d+\)\s*$", "", str(value)).strip() or "Uncategorised"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def metrics(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return dict.fromkeys(
            ["revenue", "tickets", "items", "avg_ticket", "items_per_ticket", "trading_days"], 0.0
        )
    revenue = float(df["net_revenue"].sum())
    tickets = int(df["ticket_id"].nunique())
    items = float(pd.to_numeric(df["quantity"], errors="coerce").fillna(0).sum())
    return {
        "revenue": revenue,
        "tickets": tickets,
        "items": items,
        "avg_ticket": revenue / tickets if tickets else 0.0,
        "items_per_ticket": items / tickets if tickets else 0.0,
        "trading_days": int(df["transaction_date"].nunique()),
    }


@dataclass
class Comparison:
    """One row of the analysis: a segment measured in both years."""

    name: str
    current: Dict[str, float]
    prior: Dict[str, float]

    def change(self, metric: str) -> float:
        return pct_change(self.current[metric], self.prior[metric])

    @property
    def traffic_effect(self) -> float:
        return (self.current["tickets"] - self.prior["tickets"]) * self.prior["avg_ticket"]

    @property
    def spend_effect(self) -> float:
        return (self.current["revenue"] - self.prior["revenue"]) - self.traffic_effect


@dataclass
class Analysis:
    total: Comparison
    locations: List[Comparison]
    older_revenue: Optional[float]
    older_year: Optional[int]


def build_analysis(df: pd.DataFrame, ctx: DiagnosticContext) -> Analysis:
    total = Comparison(
        name="Total",
        current=metrics(comparable_frame(df, ctx, ctx.current_year)),
        prior=metrics(comparable_frame(df, ctx, ctx.prior_year)),
    )
    locations = []
    for location in sorted(df["location"].dropna().unique()):
        current = metrics(comparable_frame(df, ctx, ctx.current_year, location))
        prior = metrics(comparable_frame(df, ctx, ctx.prior_year, location))
        if current["revenue"] or prior["revenue"]:
            locations.append(Comparison(name=location, current=current, prior=prior))

    older_revenue = older_year = None
    if len(ctx.comparison_years) > 1:
        older_year = ctx.comparison_years[1]
        value = metrics(comparable_frame(df, ctx, older_year))["revenue"]
        older_revenue = value or None
    return Analysis(total=total, locations=locations, older_revenue=older_revenue, older_year=older_year)


def pct_change(current: float, prior: float) -> float:
    return ((current - prior) / prior * 100) if prior else float("nan")


def fmt_eur(value: float) -> str:
    return f"\u20ac{value:,.0f}"


def fmt_pct(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value:+.1f}%"


# ---------------------------------------------------------------------------
# HTML building blocks
# ---------------------------------------------------------------------------


def _bold(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text or "")


def render_bullets(lines: List[str]) -> str:
    if not lines:
        return ""
    return "<ul>" + "".join(f"<li>{_bold(line)}</li>" for line in lines) + "</ul>"


def delta(value: float, invert: bool = False) -> str:
    """A signed percentage coloured by direction."""
    if pd.isna(value):
        return f'<span style="color:{MUTED_TEXT};">n/a</span>'
    good = value < 0 if invert else value > 0
    colour = UP_TEXT if good else DOWN_TEXT
    return f'<span style="color:{colour};">{value:+.1f}%</span>'


def render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    emphasise_last: bool = False,
    col_widths: Optional[Sequence[str]] = None,
) -> str:
    """Render a table. col_widths fixes the layout so stacked tables line up."""
    colgroup = ""
    layout = ""
    if col_widths:
        colgroup = "<colgroup>" + "".join(f'<col style="width:{w};" />' for w in col_widths) + "</colgroup>"
        layout = "table-layout:fixed;"
    head = "".join(
        f'<th style="text-align:{"left" if i == 0 else "right"};">{h}</th>'
        for i, h in enumerate(headers)
    )
    body = []
    for index, row in enumerate(rows):
        last = emphasise_last and index == len(rows) - 1
        style = ' style="border-top:1px solid #374151;font-weight:600;"' if last else ""
        cells = "".join(
            f'<td style="text-align:{"left" if i == 0 else "right"};">{cell}</td>'
            for i, cell in enumerate(row)
        )
        body.append(f"<tr{style}>{cells}</tr>")
    return (
        f'<div class="table-wrapper"><table style="{layout}">{colgroup}'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
        "</table></div>"
    )


def embed_chart(path: Optional[Path]) -> str:
    """Inline a chart as a data URI so the HTML file is self-contained."""
    if path is None or not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        '<div style="margin-top:16px;">'
        f'<img src="data:image/png;base64,{encoded}" alt="" '
        'style="max-width:100%;height:auto;border-radius:8px;" />'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Section content
# ---------------------------------------------------------------------------


def headline_section(analysis: Analysis, ctx: DiagnosticContext) -> Tuple[List[str], str]:
    total = analysis.total
    lines = [
        f"Revenue **{fmt_eur(total.current['revenue'])}** vs {fmt_eur(total.prior['revenue'])} "
        f"in {ctx.prior_year} \u2014 **{fmt_pct(total.change('revenue'))}**."
    ]
    if analysis.older_revenue:
        lines.append(
            f"Against {analysis.older_year}: **{fmt_pct(pct_change(total.current['revenue'], analysis.older_revenue))}** "
            f"({fmt_eur(analysis.older_revenue)})."
        )
    return lines, ""


def integrity_section(df: pd.DataFrame, ctx: DiagnosticContext) -> Tuple[List[str], str]:
    lines: List[str] = []
    period = slice_year(df, ctx, ctx.current_year)

    if ctx.closures:
        described = ", ".join(
            f"{c.day:%-d %b}" + (f" ({c.location})" if c.location else "") for c in ctx.closures
        )
        lines.append(f"Closures excluded from both years: **{described}**.")

    declared = {(c.day, c.location) for c in ctx.closures}
    dark: List[str] = []
    if not period.empty:
        for location in sorted(period["location"].dropna().unique()):
            traded = set(period.loc[period["location"] == location, "transaction_date"].dt.date)
            for day in pd.date_range(*ctx.window_for_year(ctx.current_year), freq="D").date:
                if day not in traded and (day, location) not in declared and (day, None) not in declared:
                    dark.append(f"{day:%-d %b} ({location})")
    if dark:
        lines.append(f"**Unexplained non-trading days**: {', '.join(dark)}. Confirm before circulating.")

    if not period.empty:
        missing = [f for f in MAPPED_FIELDS if f in period.columns and period[f].isna().mean() > 0.9]
        if missing:
            lines.append(f"Unavailable (export headers unmapped): **{', '.join(missing)}**.")
        zero_rate = (period["net_revenue"].fillna(0) == 0).mean() * 100
        lines.append(f"Lines parsed to zero revenue: **{zero_rate:.1f}%**.")
    if not dark and not any("Unexplained" in line for line in lines):
        lines.append("No missing trading days detected.")
    return lines, ""


def traffic_spend_section(analysis: Analysis, ctx: DiagnosticContext, chart: Optional[Path]) -> Tuple[List[str], str]:
    total = analysis.total
    driver = "footfall" if abs(total.traffic_effect) > abs(total.spend_effect) else "spend per ticket"
    lines = [
        f"Revenue is tickets \u00d7 average ticket. Of the {fmt_eur(abs(total.current['revenue'] - total.prior['revenue']))} "
        f"movement, **{fmt_eur(total.traffic_effect)}** came from ticket volume and "
        f"**{fmt_eur(total.spend_effect)}** from ticket value \u2014 so this is a **{driver}** story.",
    ]

    avg_moves = [(c.name, c.change("avg_ticket")) for c in analysis.locations]
    if len({value > 0 for _, value in avg_moves}) > 1:
        lines.append(
            "The sites move in **opposite directions** on ticket value, so the blended average "
            "is misleading. Read the per-location rows."
        )

    rows = []
    for comparison in [*analysis.locations, total]:
        rows.append(
            [
                comparison.name,
                fmt_eur(comparison.current["revenue"]),
                delta(comparison.change("revenue")),
                f"{comparison.current['tickets']:,.0f}",
                delta(comparison.change("tickets")),
                f"\u20ac{comparison.current['avg_ticket']:,.2f}",
                delta(comparison.change("avg_ticket")),
                f"{comparison.current['items_per_ticket']:.2f}",
                delta(comparison.change("items_per_ticket")),
            ]
        )
    table = render_table(
        ["", "Revenue", "vs LY", "Tickets", "vs LY", "Avg ticket", "vs LY", "Items/ticket", "vs LY"],
        rows,
        emphasise_last=True,
    )
    return lines, table + embed_chart(chart)


def location_section(analysis: Analysis, ctx: DiagnosticContext, chart: Optional[Path]) -> Tuple[List[str], str]:
    lines = []
    for comparison in analysis.locations:
        lines.append(
            f"**{comparison.name}**: volume effect {fmt_eur(comparison.traffic_effect)}, "
            f"value effect {fmt_eur(comparison.spend_effect)}."
        )
    rows = [
        [
            comparison.name,
            fmt_eur(comparison.current["revenue"]),
            fmt_eur(comparison.prior["revenue"]),
            delta(comparison.change("revenue")),
            fmt_eur(comparison.traffic_effect),
            fmt_eur(comparison.spend_effect),
            f"{comparison.current['trading_days']:.0f}",
        ]
        for comparison in analysis.locations
    ]
    table = render_table(
        ["", f"{ctx.current_year}", f"{ctx.prior_year}", "vs LY", "Volume effect", "Value effect", "Days"],
        rows,
    )
    return lines, table + embed_chart(chart)


def daypart_section(df: pd.DataFrame, ctx: DiagnosticContext, chart: Optional[Path]) -> Tuple[List[str], str]:
    cur = comparable_frame(df, ctx, ctx.current_year)
    pri = comparable_frame(df, ctx, ctx.prior_year)
    if cur.empty or pri.empty:
        return [], ""

    bands = [(0, 12, "Morning"), (12, 17, "Afternoon"), (17, 24, "Evening")]
    rows = []
    for start, end, name in bands:
        cur_rev = float(cur.loc[cur["hour"].between(start, end - 1), "net_revenue"].sum())
        pri_rev = float(pri.loc[pri["hour"].between(start, end - 1), "net_revenue"].sum())
        rows.append([name, fmt_eur(cur_rev), fmt_eur(pri_rev), delta(pct_change(cur_rev, pri_rev))])

    # A fixed calendar window holds different weekday counts year to year, so
    # weekdays are compared on average takings per occurrence.
    def per_weekday(frame: pd.DataFrame) -> pd.Series:
        by_day = frame.groupby(frame["transaction_date"].dt.normalize())["net_revenue"].sum()
        return by_day.groupby(by_day.index.day_name()).mean()

    cur_dow, pri_dow = per_weekday(cur), per_weekday(pri)
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow_rows = []
    for day in order:
        if day in cur_dow.index and day in pri_dow.index:
            dow_rows.append(
                [day, fmt_eur(cur_dow[day]), fmt_eur(pri_dow[day]), delta(pct_change(cur_dow[day], pri_dow[day]))]
            )

    lines = ["Weekdays compared on average takings per occurrence, since the window holds different weekday counts each year."]
    # Both tables share a fixed column layout so the year and vs LY columns line
    # up when the two are stacked, despite the different label lengths.
    widths = ["34%", "22%", "22%", "22%"]
    body = render_table(
        ["Daypart", f"{ctx.current_year}", f"{ctx.prior_year}", "vs LY"], rows, col_widths=widths
    )
    if dow_rows:
        body += render_table(
            ["Weekday (avg/day)", f"{ctx.current_year}", f"{ctx.prior_year}", "vs LY"],
            dow_rows,
            col_widths=widths,
        )
    return lines, body + embed_chart(chart)


def category_section(df: pd.DataFrame, ctx: DiagnosticContext) -> Tuple[List[str], str]:
    cur = comparable_frame(df, ctx, ctx.current_year)
    pri = comparable_frame(df, ctx, ctx.prior_year)
    if cur.empty or pri.empty:
        return [], ""

    def tax_split(frame: pd.DataFrame) -> Dict[str, float]:
        rate = pd.to_numeric(frame["tax_rate"], errors="coerce")
        name = frame["tax_name"].astype(str)
        is_drink = (rate.round(2) == 1.20) | name.str.contains("20")
        return {
            "Food (TVA 10%)": float(frame.loc[~is_drink, "net_revenue"].sum()),
            "Drink (TVA 20%)": float(frame.loc[is_drink, "net_revenue"].sum()),
        }

    cur_split, pri_split = tax_split(cur), tax_split(pri)
    rows = [
        [key, fmt_eur(cur_split[key]), fmt_eur(pri_split[key]), delta(pct_change(cur_split[key], pri_split[key]))]
        for key in cur_split
    ]

    cur_cat = cur.assign(l=cur["category"].map(clean_label)).groupby("l")["net_revenue"].sum()
    pri_cat = pri.assign(l=pri["category"].map(clean_label)).groupby("l")["net_revenue"].sum()
    combined = pd.concat([cur_cat.rename("cur"), pri_cat.rename("pri")], axis=1).fillna(0.0)
    combined["delta"] = combined["cur"] - combined["pri"]
    for name, row in combined.nsmallest(4, "delta").iterrows():
        rows.append([name, fmt_eur(row["cur"]), fmt_eur(row["pri"]), delta(pct_change(row["cur"], row["pri"]))])

    return [], render_table(["", f"{ctx.current_year}", f"{ctx.prior_year}", "vs LY"], rows)


def product_section(
    df: pd.DataFrame, ctx: DiagnosticContext, rank_by: str, top: int = 8
) -> Tuple[List[str], str, Dict[str, object]]:
    """Top sellers side by side, so a change at the top of the menu is obvious."""
    cur = comparable_frame(df, ctx, ctx.current_year)
    pri = comparable_frame(df, ctx, ctx.prior_year)
    if cur.empty or pri.empty:
        return [], "", {}

    # Duplicate POS entries are merged before anything is ranked. Left split, an
    # item renamed mid-year reads as a huge faller and a huge riser at once,
    # which would put phantom entries at the top of the swings table.
    raw_totals = pd.concat([cur, pri]).groupby("item_name")["net_revenue"].sum()
    cur_totals = cur.groupby("item_name")["net_revenue"].sum()
    duplicate_groups = find_duplicate_entries(raw_totals)
    canonical: Dict[str, str] = {}
    for group in duplicate_groups:
        # Prefer the spelling still in use this year, falling back to the bigger seller.
        label = max(
            group,
            key=lambda name: (float(cur_totals.get(name, 0.0)), float(raw_totals.get(name, 0.0))),
        )
        for name in group:
            canonical[name] = label

    def rank(frame: pd.DataFrame) -> pd.DataFrame:
        grouped = frame.assign(
            _units=pd.to_numeric(frame["quantity"], errors="coerce").fillna(0),
            _item=frame["item_name"].map(lambda name: canonical.get(name, name)),
        ).groupby("_item").agg(revenue=("net_revenue", "sum"), units=("_units", "sum"))
        grouped.index.name = "item_name"
        return grouped.sort_values(rank_by, ascending=False)

    cur_rank, pri_rank = rank(cur), rank(pri)
    cur_top, pri_top = cur_rank.head(top), pri_rank.head(top)

    rows = []
    for position in range(top):
        pri_row = pri_top.iloc[position] if position < len(pri_top) else None
        cur_row = cur_top.iloc[position] if position < len(cur_top) else None
        highlight = position == 0

        def cell(text: str) -> str:
            return f"<strong>{text}</strong>" if highlight else text

        rows.append(
            [
                cell(str(position + 1)),
                cell(pri_top.index[position]) if pri_row is not None else "\u2014",
                cell(fmt_eur(pri_row["revenue"])) if pri_row is not None else "",
                cell(f"{pri_row['units']:,.0f}") if pri_row is not None else "",
                cell(cur_top.index[position]) if cur_row is not None else "\u2014",
                cell(fmt_eur(cur_row["revenue"])) if cur_row is not None else "",
                cell(f"{cur_row['units']:,.0f}") if cur_row is not None else "",
            ]
        )
    rows.append(
        [
            f"Top {top}",
            "",
            fmt_eur(pri_top["revenue"].sum()),
            f"{pri_top['units'].sum():,.0f}",
            "",
            fmt_eur(cur_top["revenue"].sum()),
            f"{cur_top['units'].sum():,.0f}",
        ]
    )

    table = render_table(
        ["#", f"{ctx.prior_year} top seller", "Revenue", "Units", f"{ctx.current_year} top seller", "Revenue", "Units"],
        rows,
        emphasise_last=True,
    )

    pri_share = pri_top["revenue"].sum() / pri["net_revenue"].sum() * 100
    cur_share = cur_top["revenue"].sum() / cur["net_revenue"].sum() * 100
    lines = [
        f"Ranked by {rank_by}. Top {top} carried **{cur_share:.0f}%** of revenue this period "
        f"vs {pri_share:.0f}% last year.",
    ]

    # Revenue and units side by side: a product can hold revenue on fewer covers, or
    # sell the same volume for less. The pair distinguishes the two.
    swings = pd.DataFrame(
        {
            "cur_revenue": cur_rank["revenue"],
            "pri_revenue": pri_rank["revenue"],
            "cur_units": cur_rank["units"],
            "pri_units": pri_rank["units"],
        }
    ).fillna(0.0)
    swings["revenue_delta"] = swings["cur_revenue"] - swings["pri_revenue"]
    swings["units_delta"] = swings["cur_units"] - swings["pri_units"]
    movers = pd.concat([swings.nsmallest(6, "revenue_delta"), swings.nlargest(6, "revenue_delta")])
    swing_rows = [
        [
            name,
            fmt_eur(row["pri_revenue"]),
            fmt_eur(row["cur_revenue"]),
            f'<span style="color:{UP_TEXT if row["revenue_delta"] > 0 else DOWN_TEXT};">{fmt_eur(row["revenue_delta"])}</span>',
            f"{row['pri_units']:,.0f}",
            f"{row['cur_units']:,.0f}",
            f'<span style="color:{UP_TEXT if row["units_delta"] > 0 else DOWN_TEXT};">{row["units_delta"]:+,.0f}</span>',
        ]
        for name, row in movers.iterrows()
    ]
    swing_table = render_table(
        [
            "Biggest swings",
            f"Rev {ctx.prior_year}",
            f"Rev {ctx.current_year}",
            "\u0394 revenue",
            f"Units {ctx.prior_year}",
            f"Units {ctx.current_year}",
            "\u0394 units",
        ],
        swing_rows,
    )

    # Menu churn: renames and duplicate entries make product comparison unreliable.
    combined = pd.concat([cur_rank["revenue"].rename("cur"), pri_rank["revenue"].rename("pri")], axis=1).fillna(0.0)
    disappeared = combined[(combined["pri"] > 500) & (combined["cur"] == 0)]
    arrived = combined[(combined["cur"] > 500) & (combined["pri"] == 0)]
    renames, lost = classify_renames(disappeared, arrived)
    churn: List[str] = []
    if duplicate_groups:
        churn.append(f"**{len(duplicate_groups)}** product(s) split across duplicate menu entries")
    if renames:
        churn.append(f"**{len(renames)}** renamed")
    if lost:
        churn.append(f"**{len(lost)}** sold last year with no match this year")
    if churn:
        lines.append("Menu churn: " + ", ".join(churn) + ".")

    duplicate_table = ""
    if duplicate_groups:
        duplicate_rows = []
        for group in sorted(duplicate_groups, key=lambda g: -float(raw_totals[g].sum())):
            label = canonical[group[0]]
            variants = " + ".join(f"<code>{name}</code>" for name in group)
            duplicate_rows.append(
                [
                    variants,
                    fmt_eur(float(pri_rank["revenue"].get(label, 0.0))),
                    fmt_eur(float(cur_rank["revenue"].get(label, 0.0))),
                ]
            )
        duplicate_table = (
            '<h3 style="margin-top:22px;">Duplicate POS entries to fix</h3>'
            '<div class="caption">Same product entered twice under different '
            "capitalisation or punctuation. These are merged in every table above, but they "
            "should be consolidated in Lightspeed \u2014 left split they corrupt product "
            "rankings and stock reporting. Revenue shown is the merged figure.</div>"
            + render_table(
                ["Entries found", f"Merged rev {ctx.prior_year}", f"Merged rev {ctx.current_year}"],
                duplicate_rows,
                col_widths=["52%", "24%", "24%"],
            )
        )

    biggest_faller = movers.nsmallest(1, "revenue_delta")
    biggest_riser = movers.nlargest(1, "revenue_delta")
    facts = {
        "prior_leader": pri_top.index[0] if len(pri_top) else None,
        "prior_leader_revenue": float(pri_top.iloc[0]["revenue"]) if len(pri_top) else 0.0,
        "prior_leader_units": float(pri_top.iloc[0]["units"]) if len(pri_top) else 0.0,
        "current_leader": cur_top.index[0] if len(cur_top) else None,
        "current_leader_revenue": float(cur_top.iloc[0]["revenue"]) if len(cur_top) else 0.0,
        "current_leader_units": float(cur_top.iloc[0]["units"]) if len(cur_top) else 0.0,
        "faller": biggest_faller.index[0] if len(biggest_faller) else None,
        "faller_revenue_delta": float(biggest_faller.iloc[0]["revenue_delta"]) if len(biggest_faller) else 0.0,
        "faller_units_delta": float(biggest_faller.iloc[0]["units_delta"]) if len(biggest_faller) else 0.0,
        "riser": biggest_riser.index[0] if len(biggest_riser) else None,
        "riser_revenue_delta": float(biggest_riser.iloc[0]["revenue_delta"]) if len(biggest_riser) else 0.0,
        "riser_units_delta": float(biggest_riser.iloc[0]["units_delta"]) if len(biggest_riser) else 0.0,
        "renames": renames,
        "duplicates": duplicate_groups,
    }
    return lines, table + swing_table + duplicate_table, facts


def find_duplicate_entries(totals: pd.Series, threshold: float = 250.0) -> List[List[str]]:
    """Item names differing only by case or punctuation, e.g. 'IPA 50cl' / 'IPA. 50cl'.

    Takes combined revenue by raw item name across both periods; the threshold
    keeps one-off keying mistakes out of the report.
    """
    active = totals[totals > threshold]
    groups: Dict[str, List[str]] = {}
    for name in active.index:
        groups.setdefault(re.sub(r"[^a-z0-9]", "", str(name).lower()), []).append(str(name))
    return [sorted(names) for names in groups.values() if len(names) > 1]


def classify_renames(
    disappeared: pd.DataFrame, arrived: pd.DataFrame
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Separate likely renames from genuinely discontinued products."""

    def normalise(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(name).lower())

    normalised_arrived = {normalise(name): name for name in arrived.index}
    renames: List[Tuple[str, str]] = []
    lost: List[str] = []
    available = set(arrived.index)

    for old_name in disappeared.sort_values("pri", ascending=False).index:
        key = normalise(old_name)
        match = normalised_arrived.get(key)
        if match is None:
            candidates = difflib.get_close_matches(
                key, [normalise(n) for n in available], n=1, cutoff=0.75
            )
            if candidates:
                match = normalised_arrived.get(candidates[0])
        if match and match in available:
            renames.append((old_name, match))
            available.discard(match)
        else:
            lost.append(old_name)
    return renames, lost


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def _style(fig: go.Figure, title: str, xaxis_title: str = "", yaxis_title: str = "") -> None:
    fig.update_layout(
        plot_bgcolor=CHART_BG,
        paper_bgcolor=CHART_BG,
        font=dict(color=CHART_FG, size=13, family="Arial, sans-serif"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.26,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color=CHART_FG),
            bgcolor="rgba(245, 245, 245, 0.9)",
            bordercolor=CHART_FG,
            borderwidth=1,
        ),
        title=dict(
            text=title,
            font=dict(size=17, color=CHART_FG, family="Arial, sans-serif"),
            x=0.5,
            xanchor="center",
        ),
        hovermode="x unified",
    )
    axis = dict(
        title_font=dict(size=13, color=CHART_FG),
        tickfont=dict(size=11, color=CHART_FG),
        gridcolor="rgba(0, 0, 0, 0.2)",
        gridwidth=1,
    )
    fig.update_xaxes(title_text=xaxis_title, **axis)
    fig.update_yaxes(title_text=yaxis_title, **axis)


def _save(fig: go.Figure, out_dir: Path, filename: str, height: int = 480) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    fig.write_image(str(path), scale=2, width=1000, height=height)
    return path


def _gradient_area(fig: go.Figure, x, y, row: int = 1, col: int = 1, bands: int = 50) -> None:
    """Approximate a gradient fill under a line, matching the weekly report."""
    for i in range(bands):
        t = (i + 1) / bands
        r = int(255 - (255 - 22) * t)
        g = int(255 - (255 - 163) * t)
        b = int(255 - (255 - 74) * t)
        fig.add_trace(
            go.Scatter(
                x=x,
                y=[value * t for value in y],
                fill="tonexty" if i > 0 else "tozeroy",
                fillcolor=f"rgba({r}, {g}, {b}, {0.1 + 0.2 * t:.3f})",
                line=dict(width=0),
                mode="lines",
                showlegend=False,
                hoverinfo="skip",
            ),
            row=row,
            col=col,
        )


def chart_daily_revenue(df: pd.DataFrame, ctx: DiagnosticContext, out_dir: Path) -> Optional[Path]:
    cur = slice_year(df, ctx, ctx.current_year)
    pri = slice_year(df, ctx, ctx.prior_year)
    if cur.empty and pri.empty:
        return None
    cur_daily = cur.groupby("day_of_month")["net_revenue"].sum().sort_index()
    pri_daily = pri.groupby("day_of_month")["net_revenue"].sum().sort_index()

    fig = make_subplots(rows=1, cols=1)
    if not pri_daily.empty:
        _gradient_area(fig, list(pri_daily.index), list(pri_daily.values))
        fig.add_trace(
            go.Scatter(
                x=pri_daily.index,
                y=pri_daily.values,
                name=str(ctx.prior_year),
                line=dict(color=PRIOR_GREY, width=1),
                mode="lines",
            )
        )
    if not cur_daily.empty:
        fig.add_trace(
            go.Scatter(
                x=cur_daily.index,
                y=cur_daily.values,
                name=str(ctx.current_year),
                line=dict(color=CLOVE_GREEN, width=3),
                mode="lines",
            )
        )
    for closure in ctx.closures:
        fig.add_vline(
            x=closure.day.day,
            line=dict(color=NEGATIVE_RED, width=1, dash="dot"),
            annotation_text="closed",
            annotation_font=dict(size=10, color=NEGATIVE_RED),
        )
    _style(fig, f"Daily Revenue: {ctx.current_year} vs {ctx.prior_year}", "Day of Month", "Revenue (\u20ac)")
    return _save(fig, out_dir, "diag_daily_revenue.png")


def chart_ticket_slope(analysis: Analysis, ctx: DiagnosticContext, out_dir: Path) -> Optional[Path]:
    """Dumbbells indexed to last year = 100, one row per location and metric.

    Indexing solves the scale problem that made the previous slope panels
    unreadable: covers, euros and item counts share no natural axis, but their
    percentage movement does, so all six rows sit on one comparable scale and
    the longest bar is the biggest mover. Absolute values are printed at each
    end so the chart still stands alone.
    """
    if not analysis.locations:
        return None
    metrics = [
        ("tickets", "Tickets", ",.0f", ""),
        ("avg_ticket", "Avg ticket", ",.2f", "\u20ac"),
        ("items_per_ticket", "Items per ticket", ",.2f", ""),
    ]

    labels: List[str] = []
    entries: List[tuple] = []
    for comparison in analysis.locations:
        for metric, metric_label, number_format, prefix in metrics:
            start, end = comparison.prior[metric], comparison.current[metric]
            if start <= 0:
                continue
            labels.append(f"{comparison.name} \u00b7 {metric_label}")
            entries.append(
                (
                    labels[-1],
                    start,
                    end,
                    100.0 * end / start,
                    f"{prefix}{start:{number_format}}",
                    f"{prefix}{end:{number_format}}",
                )
            )
    if not entries:
        return None

    # Plotly stacks categories from the bottom up; reverse so the first location
    # reads at the top of the chart.
    order = list(reversed(labels))
    fig = go.Figure()
    indices = [entry[3] for entry in entries]
    span = max(max(indices) - 100.0, 100.0 - min(indices), 5.0)
    axis_lo, axis_hi = 100.0 - span * 1.9, 100.0 + span * 1.9

    for label, _, _, index, start_text, end_text in entries:
        rising = index >= 100.0
        colour = CLOVE_GREEN if rising else NEGATIVE_RED
        fig.add_trace(
            go.Scatter(
                x=[100.0, index],
                y=[label, label],
                mode="lines",
                line=dict(color=colour, width=4),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[100.0],
                y=[label],
                mode="markers+text",
                marker=dict(size=10, color=PRIOR_GREY, line=dict(color=CHART_BG, width=1)),
                text=[start_text],
                textposition="middle left" if rising else "middle right",
                textfont=dict(size=11, color=PRIOR_GREY),
                showlegend=False,
                cliponaxis=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[index],
                y=[label],
                mode="markers+text",
                marker=dict(size=13, color=colour),
                text=[f"<b>{end_text}</b>  ({fmt_pct(index - 100.0)})"],
                textposition="middle right" if rising else "middle left",
                textfont=dict(size=11, color=CHART_FG),
                showlegend=False,
                cliponaxis=False,
                hoverinfo="skip",
            )
        )

    fig.add_vline(x=100.0, line=dict(color=PRIOR_GREY, width=1, dash="dot"))
    # Separator between location groups keeps the two sites visually distinct.
    for boundary in range(len(metrics), len(order), len(metrics)):
        fig.add_hline(y=boundary - 0.5, line=dict(color="#374151", width=1))

    _style(
        fig,
        f"Movement vs {ctx.prior_year} (indexed, {ctx.prior_year} = 100)",
        xaxis_title=f"Index ({ctx.prior_year} = 100)",
    )
    fig.update_layout(margin=dict(l=200, r=60, t=90, b=60))
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=order,
        tickfont=dict(size=12, color=CHART_FG),
        showgrid=False,
    )
    fig.update_xaxes(range=[axis_lo, axis_hi], tickfont=dict(size=11, color=CHART_FG))
    return _save(fig, out_dir, "diag_ticket_slope.png", height=130 + 52 * len(order))


def chart_location_daily(df: pd.DataFrame, ctx: DiagnosticContext, out_dir: Path) -> Optional[Path]:
    """Daily revenue per location so divergence between sites is visible over time."""
    locations = sorted(df["location"].dropna().unique())
    if not locations:
        return None
    fig = make_subplots(rows=1, cols=len(locations), subplot_titles=locations, shared_yaxes=True)

    for col, location in enumerate(locations, start=1):
        cur = slice_year(df, ctx, ctx.current_year)
        pri = slice_year(df, ctx, ctx.prior_year)
        cur_daily = cur[cur["location"] == location].groupby("day_of_month")["net_revenue"].sum().sort_index()
        pri_daily = pri[pri["location"] == location].groupby("day_of_month")["net_revenue"].sum().sort_index()
        if not pri_daily.empty:
            _gradient_area(fig, list(pri_daily.index), list(pri_daily.values), row=1, col=col)
            fig.add_trace(
                go.Scatter(
                    x=pri_daily.index,
                    y=pri_daily.values,
                    name=str(ctx.prior_year),
                    line=dict(color=PRIOR_GREY, width=1),
                    mode="lines",
                    showlegend=col == 1,
                ),
                row=1,
                col=col,
            )
        if not cur_daily.empty:
            fig.add_trace(
                go.Scatter(
                    x=cur_daily.index,
                    y=cur_daily.values,
                    name=str(ctx.current_year),
                    line=dict(color=CLOVE_GREEN, width=3),
                    mode="lines",
                    showlegend=col == 1,
                ),
                row=1,
                col=col,
            )
    _style(fig, f"Daily Revenue by Location: {ctx.current_year} vs {ctx.prior_year}", "Day of Month", "")
    # Shared scale keeps the sites comparable, but both panels are labelled so the
    # right-hand chart can be read without referring back to the left.
    fig.update_yaxes(title_text="Revenue (\u20ac)", showticklabels=True, tickformat=",.0f")
    for annotation in fig.layout.annotations[: len(locations)]:
        annotation.font = dict(size=12, color=CHART_FG)
    return _save(fig, out_dir, "diag_location_daily.png", height=420)


def chart_hourly(df: pd.DataFrame, ctx: DiagnosticContext, out_dir: Path) -> Optional[Path]:
    """Revenue by hour, one panel per location.

    Service patterns differ by site, so a combined chart averages away the thing
    worth seeing: which sitting actually lost trade.
    """
    cur = comparable_frame(df, ctx, ctx.current_year)
    pri = comparable_frame(df, ctx, ctx.prior_year)
    if cur.empty or pri.empty:
        return None
    locations = sorted(set(cur["location"].dropna()) | set(pri["location"].dropna()))
    if not locations:
        return None

    fig = make_subplots(
        rows=len(locations),
        cols=1,
        subplot_titles=locations,
        shared_xaxes=True,
        vertical_spacing=0.13,
    )
    hours = sorted(set(cur["hour"].dropna()) | set(pri["hour"].dropna()))

    for row, location in enumerate(locations, start=1):
        cur_h = cur[cur["location"] == location].groupby("hour")["net_revenue"].sum()
        pri_h = pri[pri["location"] == location].groupby("hour")["net_revenue"].sum()
        for name, series, colour in (
            (str(ctx.prior_year), pri_h, PRIOR_GREY),
            (str(ctx.current_year), cur_h, CLOVE_GREEN),
        ):
            fig.add_trace(
                go.Bar(
                    x=hours,
                    y=[float(series.get(hour, 0.0)) for hour in hours],
                    name=name,
                    marker_color=colour,
                    showlegend=row == 1,
                ),
                row=row,
                col=1,
            )

    _style(fig, f"Revenue by Hour and Location: {ctx.current_year} vs {ctx.prior_year}")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
    fig.update_yaxes(title_text="Revenue (\u20ac)", tickformat=",.0f")
    fig.update_xaxes(dtick=1, tickfont=dict(size=11, color=CHART_FG))
    # Only the bottom panel is labelled; a title on the upper axis would collide
    # with the subplot heading beneath it.
    fig.update_xaxes(title_text="Hour of Day", row=len(locations), col=1)
    for annotation in fig.layout.annotations[: len(locations)]:
        annotation.font = dict(size=12, color=CHART_FG)
    return _save(fig, out_dir, "diag_hourly.png", height=180 + 200 * len(locations))


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


def key_insights(
    df: pd.DataFrame,
    ctx: DiagnosticContext,
    analysis: Analysis,
    product_facts: Dict[str, object],
) -> List[str]:
    """One takeaway per section, ordered by how much it should change a decision."""
    total = analysis.total
    lines: List[str] = []

    lines.append(
        f"Revenue is **{fmt_pct(total.change('revenue'))}** on {ctx.prior_year} "
        f"({fmt_eur(total.current['revenue'] - total.prior['revenue'])}), driven by "
        f"**{fmt_pct(total.change('tickets'))} fewer tickets** rather than lower spend per ticket."
    )

    if analysis.older_revenue:
        older_change = pct_change(total.current["revenue"], analysis.older_revenue)
        verdict = (
            f"broadly flat on {analysis.older_year}, so {ctx.prior_year} looks like an exceptional year "
            f"rather than the new normal"
            if abs(older_change) < 5
            else f"also {fmt_pct(older_change)} on {analysis.older_year}, so this is a sustained trend"
        )
        lines.append(f"On a two-year view it is {verdict}.")

    worst = min(analysis.locations, key=lambda c: c.change("revenue"), default=None)
    if worst is not None:
        lines.append(
            f"**{worst.name}** is the problem site at {fmt_pct(worst.change('revenue'))}, "
            f"with tickets {fmt_pct(worst.change('tickets'))} and average ticket "
            f"{fmt_pct(worst.change('avg_ticket'))}."
        )
    gainers = [c for c in analysis.locations if c.change("avg_ticket") > 0]
    if gainers and worst is not None and any(c.name != worst.name for c in gainers):
        other = next(c for c in gainers if c.name != worst.name)
        lines.append(
            f"**{other.name}** is only holding revenue "
            f"({fmt_pct(other.change('revenue'))}) because each ticket is worth "
            f"{fmt_pct(other.change('avg_ticket'))} more, not because trade improved \u2014 "
            f"covers are still {fmt_pct(other.change('tickets'))}. Price is doing the work, "
            f"so if covers keep falling the price rises have to get bigger every year just "
            f"to stand still."
        )

    if total.change("items_per_ticket") < -2:
        lines.append(
            f"Guests are also ordering less per visit: items per ticket "
            f"**{fmt_pct(total.change('items_per_ticket'))}**, which points at fewer "
            f"add-ons \u2014 sides, extra drinks, dessert \u2014 rather than pricing."
        )

    prior_leader = product_facts.get("prior_leader")
    current_leader = product_facts.get("current_leader")
    if prior_leader and current_leader and prior_leader != current_leader:
        lines.append(
            f"The top seller changed: **{prior_leader}** "
            f"({fmt_eur(float(product_facts['prior_leader_revenue']))} from "
            f"{float(product_facts['prior_leader_units']):,.0f} units) led last year, "
            f"**{current_leader}** "
            f"({fmt_eur(float(product_facts['current_leader_revenue']))} from "
            f"{float(product_facts['current_leader_units']):,.0f} units) leads now."
        )
    if product_facts.get("faller"):
        lines.append(
            f"Biggest product loss is **{product_facts['faller']}** at "
            f"{fmt_eur(float(product_facts['faller_revenue_delta']))} on "
            f"{float(product_facts['faller_units_delta']):+,.0f} units, "
            f"against a best gain of **{product_facts['riser']}** at "
            f"{fmt_eur(float(product_facts['riser_revenue_delta']))} on "
            f"{float(product_facts['riser_units_delta']):+,.0f} units."
        )
    duplicates = product_facts.get("duplicates") or []
    if duplicates:
        listed = "; ".join(" / ".join(group) for group in duplicates)
        lines.append(
            f"Housekeeping: **{len(duplicates)} products are entered twice** in the POS under "
            f"different capitalisation or punctuation \u2014 {listed}. They are merged in this "
            f"report, but consolidate them in Lightspeed or product rankings and stock "
            f"reporting stay wrong."
        )
    return lines


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def build_html(ctx: DiagnosticContext, sections: List[Tuple[str, List[str], str]]) -> str:
    cards = []
    for title, bullets, body in sections:
        if not bullets and not body:
            continue
        cards.append(
            f"""
      <div class="card">
        <div class="card-header"><h2>{title}</h2></div>
        {render_bullets(bullets)}
        {body}
      </div>"""
        )
    return f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>MUMMA Trend Diagnostic</title>
      <style>
        body {{
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background-color: #050816 !important;
          color: #FFFFFF !important;
          padding: 24px;
        }}
        h1, h2, h3 {{ color: #FFFFFF !important; }}
        .card {{
          background: #0B1220 !important;
          border-radius: 12px;
          padding: 16px 20px;
          margin-bottom: 20px;
          border: 1px solid #1F2937 !important;
        }}
        .card-header {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }}
        .card-header h2 {{ margin: 0; }}
        .caption {{
          margin-bottom: 12px;
          padding: 8px 10px;
          background-color: #1F2937;
          color: #D1D5DB;
          font-size: 13px;
          line-height: 1.45;
          border-radius: 6px;
        }}
        .table-wrapper {{
          width: 100%;
          overflow-x: auto;
          -webkit-overflow-scrolling: touch;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          margin-top: 8px;
          margin-bottom: 8px;
          font-size: 13px;
        }}
        th, td {{ padding: 6px 8px; color: #FFFFFF !important; }}
        th {{
          text-align: left;
          border-bottom: 1px solid #374151 !important;
          color: #D1D5DB !important;
          font-weight: 500;
          white-space: nowrap;
        }}
        ul {{ color: #FFFFFF !important; list-style-type: none; padding-left: 0; margin: 0 0 4px 0; }}
        li {{ color: #FFFFFF !important; margin-bottom: 6px; line-height: 1.5; }}
        .insights li {{ margin-bottom: 10px; }}
      </style>
    </head>
    <body>
      <h1 style="margin:0 0 16px 0;">MUMMA Trend Diagnostic</h1>
      <p class="caption">
        {ctx.period_caption} vs the same dates in {", ".join(str(y) for y in ctx.comparison_years)}.
        Generated {datetime.now():%d %b %Y %H:%M}.
      </p>
      {"".join(cards)}
    </body>
    </html>
    """


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def to_email_html(html: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Swap inline data URIs for CID attachments.

    The file on disk embeds charts as data URIs so it can be moved around as a
    single self-contained document, but Gmail and Outlook strip data: images.
    Referencing the same bytes as CID attachments is what makes them render in
    an email client.
    """
    attachments: List[Dict[str, Any]] = []

    def replace(match: "re.Match[str]") -> str:
        cid = f"diag_chart_{len(attachments) + 1}"
        attachments.append(
            {"filename": f"{cid}.png", "content": match.group(1), "content_id": cid}
        )
        return f'src="cid:{cid}"'

    return re.sub(r'src="data:image/png;base64,([^"]+)"', replace, html), attachments


def send_report_email(
    ctx: DiagnosticContext, html: str, report_path: Path, recipients: Sequence[str]
) -> None:
    """Send the diagnostic via Resend, the same transport as the weekly report."""
    if not RESEND_AVAILABLE:
        raise RuntimeError("Resend package not installed. Install with: pip install resend")

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY environment variable not set")
    resend.api_key = api_key

    body, attachments = to_email_html(html)
    # The standalone file rides along too, so the full-resolution charts and the
    # dark styling survive whatever the mail client decides to do to the body.
    attachments.append(
        {
            "filename": report_path.name,
            "content": base64.b64encode(report_path.read_bytes()).decode("ascii"),
        }
    )

    params: Dict[str, Any] = {
        "from": os.getenv("RESEND_FROM_EMAIL", "noreply@clove.solutions"),
        "to": list(recipients),
        "subject": f"MUMMA Trend Diagnostic \u2014 {ctx.period_caption}",
        "html": body,
        "attachments": attachments,
    }

    logging.info("Sending diagnostic via Resend to %s...", ", ".join(recipients))
    response = Emails.send(params)
    identifier = getattr(response, "id", None) or (
        response.get("id") if isinstance(response, dict) else None
    )
    if identifier:
        logging.info("Email sent. Resend ID: %s", identifier)
    else:
        logging.warning("Resend returned an unexpected response: %s", response)


def main() -> int:
    parser = argparse.ArgumentParser(description="MUMMA trend diagnostic report")
    parser.add_argument("--start", help="Period start, YYYY-MM-DD (default: first of the latest month)")
    parser.add_argument("--end", help="Period end inclusive, YYYY-MM-DD (default: latest ledger date)")
    parser.add_argument("--years-back", type=int, default=2, help="How many prior years to compare against")
    parser.add_argument(
        "--closure",
        action="append",
        default=[],
        metavar="YYYY-MM-DD[:Location]",
        help="A genuine closure to exclude from like-for-like comparison. Repeatable.",
    )
    parser.add_argument(
        "--rank-products-by",
        choices=["revenue", "units"],
        default="revenue",
        help="Whether the top-seller table ranks by revenue or units sold",
    )
    parser.add_argument("--output", type=Path, help="Destination HTML path")
    parser.add_argument(
        "--email",
        nargs="?",
        const="",
        metavar="ADDRESS[,ADDRESS]",
        help="Email the report. Defaults to MUMMA_DIAGNOSTIC_EMAIL_RECIPIENT, "
        "then MUMMA_EMAIL_RECIPIENT.",
    )
    args = parser.parse_args()

    logging.info("Loading ledger...")
    ledger = load_ledger()
    ctx = determine_context(
        ledger, args.start, args.end, args.years_back, [parse_closure(c) for c in args.closure]
    )
    logging.info("Period %s to %s vs %s", ctx.period_start, ctx.period_end, ctx.comparison_years)

    analysis = build_analysis(ledger, ctx)
    chart_dir = REPORTS_DIR / "charts" / f"diagnostic_{ctx.label}"

    logging.info("Rendering charts...")
    daily_chart = chart_daily_revenue(ledger, ctx, chart_dir)
    slope_chart = chart_ticket_slope(analysis, ctx, chart_dir)
    location_chart = chart_location_daily(ledger, ctx, chart_dir)
    hourly_chart = chart_hourly(ledger, ctx, chart_dir)

    logging.info("Building sections...")
    product_lines, product_body, product_facts = product_section(ledger, ctx, args.rank_products_by)

    headline_lines, _ = headline_section(analysis, ctx)
    integrity_lines, _ = integrity_section(ledger, ctx)
    traffic_lines, traffic_body = traffic_spend_section(analysis, ctx, slope_chart)
    location_lines, location_body = location_section(analysis, ctx, location_chart)
    daypart_lines, daypart_body = daypart_section(ledger, ctx, hourly_chart)
    category_lines, category_body = category_section(ledger, ctx)

    sections = [
        ("Headline", headline_lines, embed_chart(daily_chart)),
        ("Data Integrity", integrity_lines, ""),
        ("Traffic vs Spend", traffic_lines, traffic_body),
        ("By Location", location_lines, location_body),
        ("Daypart and Weekday", daypart_lines, daypart_body),
        ("Category", category_lines, category_body),
        ("Top Sellers", product_lines, product_body),
        (
            "Insights",
            [],
            '<ul class="insights">'
            + "".join(f"<li>{_bold(line)}</li>" for line in key_insights(ledger, ctx, analysis, product_facts))
            + "</ul>",
        ),
    ]

    output = args.output or REPORTS_DIR / f"mumma_trend_diagnostic_{ctx.label}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    html = build_html(ctx, sections)
    output.write_text(html, encoding="utf-8")
    logging.info("Wrote %s", output)

    if args.email is not None:
        raw = args.email or os.getenv("MUMMA_DIAGNOSTIC_EMAIL_RECIPIENT") or os.getenv(
            "MUMMA_EMAIL_RECIPIENT", ""
        )
        recipients = [address.strip() for address in raw.split(",") if address.strip()]
        if not recipients:
            logging.error("No recipient given and no recipient set in the environment.")
            return 1
        send_report_email(ctx, html, output, recipients)

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

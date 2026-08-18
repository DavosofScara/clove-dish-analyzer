#!/usr/bin/env python3
"""
MUMMA Weekly Insights Report

Generates a weekly PDF + email summary using:
- revenue_ledger.csv (transaction level)
- daily_sales_summary.xlsx (daily totals by location)
- product_insights_detailed.csv (product-period trends)

This script is designed to be run once per week (e.g. via cron/launchd)
after the Lightspeed cleaner has produced the latest processed files.
"""
from __future__ import annotations

import argparse
import base64
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Load environment variables from .env.local if it exists
try:
    from dotenv import load_dotenv
    SCRIPT_DIR = Path(__file__).resolve().parent
    ENV_FILE = SCRIPT_DIR / ".env.local"
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

import pandas as pd
import plotly.express as px  # type: ignore
import plotly.graph_objects as go  # type: ignore
import plotly.io as pio  # type: ignore

try:
    import resend
    from resend import Emails
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    resend = None
    Emails = None

try:
    from weasyprint import HTML  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    HTML = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "mumma" / "processed"
REPORTS_DIR = REPO_ROOT / "reports" / "mumma"

LEDGER_PATH = DATA_DIR / "revenue_ledger.csv"
DAILY_SALES_XLSX = DATA_DIR / "daily_sales_summary.xlsx"
PRODUCT_INSIGHTS_DETAILED = DATA_DIR / "product_insights_detailed.csv"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Plotly – dark theme similar to Clove aesthetics
pio.templates.default = "plotly_dark"


@dataclass
class WeeklyContext:
    week_start: date  # Monday of the target week
    prev_week_start: date
    report_date: date
    label: str


def _monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _normalize_report_end_date(d: date) -> date:
    """Weekly reports end Sunday; Monday (incl. early-morning) belongs to the next week."""
    if d.weekday() == 0:
        return d - timedelta(days=1)
    return d


def determine_week_context(ledger: pd.DataFrame, week_arg: Optional[str]) -> WeeklyContext:
    """Determine the current and previous week windows."""
    if week_arg:
        # Expect ISO date string YYYY-MM-DD
        ref_date = datetime.strptime(week_arg, "%Y-%m-%d").date()
    else:
        # Use max transaction_date in ledger as reference
        ref_date = pd.to_datetime(ledger["transaction_date"]).dt.date.max()

    report_date = _normalize_report_end_date(ref_date)
    week_start = _monday_of_week(report_date)
    prev_week_start = week_start - timedelta(days=7)
    label = week_start.strftime("%Y-%m-%d")
    return WeeklyContext(week_start=week_start, prev_week_start=prev_week_start, report_date=report_date, label=label)


def load_ledger() -> pd.DataFrame:
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"Ledger not found at {LEDGER_PATH}")
    df = pd.read_csv(LEDGER_PATH, parse_dates=["transaction_datetime"])
    if "transaction_date" in df.columns:
        df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.date
    return df


def load_daily_summary() -> pd.DataFrame:
    if not DAILY_SALES_XLSX.exists():
        logging.warning("Daily sales summary not found; some charts will be skipped.")
        return pd.DataFrame()
    df = pd.read_excel(DAILY_SALES_XLSX)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
    return df


def load_product_insights_detailed() -> pd.DataFrame:
    if not PRODUCT_INSIGHTS_DETAILED.exists():
        logging.warning("Detailed product insights not found; insights section will be limited.")
        return pd.DataFrame()
    df = pd.read_csv(PRODUCT_INSIGHTS_DETAILED, parse_dates=["period_start_date"])
    df["period_start_date"] = df["period_start_date"].dt.date
    return df


def filter_week(df: pd.DataFrame, ctx: WeeklyContext, date_col: str) -> pd.DataFrame:
    start = ctx.week_start
    end = ctx.week_start + timedelta(days=7)
    mask = (df[date_col] >= start) & (df[date_col] < end)
    return df.loc[mask].copy()


def summarize_week(ledger: pd.DataFrame, ctx: WeeklyContext) -> dict:
    """Compute headline KPIs for the week and previous week."""
    this_week = filter_week(ledger, ctx, "transaction_date")
    prev_week = ledger[
        (ledger["transaction_date"] >= ctx.prev_week_start)
        & (ledger["transaction_date"] < ctx.week_start)
    ]

    def _summary(df: pd.DataFrame) -> dict:
        if df.empty:
            return {
                "revenue": 0.0,
                "best_day": None,
                "best_day_revenue": 0.0,
                "top_products_units": [],
                "top_products_revenue": [],
                "by_location": {},
            }
        revenue = df["net_revenue"].sum()
        by_day = df.groupby("transaction_date")["net_revenue"].sum()
        best_day = by_day.idxmax()
        best_day_revenue = by_day.max()
        top_units = (
            df.groupby(["sku", "item_name"])["quantity"]
            .sum()
            .sort_values(ascending=False)
            .head(3)
            .reset_index()
            .to_dict(orient="records")
        )
        top_rev = (
            df.groupby(["sku", "item_name"])["net_revenue"]
            .sum()
            .sort_values(ascending=False)
            .head(3)
            .reset_index()
            .to_dict(orient="records")
        )
        by_loc = df.groupby("location")["net_revenue"].sum().to_dict()
        return {
            "revenue": float(revenue),
            "best_day": best_day,
            "best_day_revenue": float(best_day_revenue),
            "top_products_units": top_units,
            "top_products_revenue": top_rev,
            "by_location": by_loc,
        }

    return {
        "this": _summary(this_week),
        "prev": _summary(prev_week),
    }


def analyze_day_of_week_trends(daily: pd.DataFrame) -> List[str]:
    """Analyze sales patterns by day of week to identify trends."""
    if daily.empty or "Date" not in daily.columns or "Total Sales" not in daily.columns:
        return []
    
    df = daily.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df["DayOfWeek"] = df["Date"].dt.day_name()
    df["DayOfWeekNum"] = df["Date"].dt.dayofweek  # 0=Monday, 6=Sunday
    
    # Calculate average sales by day of week
    day_avg = df.groupby("DayOfWeek")["Total Sales"].mean().sort_values(ascending=False)
    
    if day_avg.empty:
        return []
    
    insights: List[str] = []
    
    # Find strongest and weakest days
    strongest_day = day_avg.index[0]
    strongest_avg = day_avg.iloc[0]
    weakest_day = day_avg.index[-1]
    weakest_avg = day_avg.iloc[-1]
    
    # Calculate percentage difference
    overall_avg = day_avg.mean()
    strongest_pct = ((strongest_avg - overall_avg) / overall_avg) * 100
    weakest_pct = ((weakest_avg - overall_avg) / overall_avg) * 100
    
    if strongest_pct > 10:  # Only mention if significantly above average
        insights.append(
            f"**{strongest_day}** is the strongest sales day, averaging €{strongest_avg:,.0f} ({strongest_pct:.0f}% above average)."
        )
    
    if weakest_pct < -10:  # Only mention if significantly below average
        insights.append(
            f"**{weakest_day}** is the weakest sales day, averaging €{weakest_avg:,.0f} ({abs(weakest_pct):.0f}% below average)."
        )
    
    # Weekend vs weekday analysis
    df["IsWeekend"] = df["DayOfWeekNum"].isin([5, 6])  # Saturday, Sunday
    weekend_avg = df[df["IsWeekend"]]["Total Sales"].mean() if df["IsWeekend"].any() else 0
    weekday_avg = df[~df["IsWeekend"]]["Total Sales"].mean() if (~df["IsWeekend"]).any() else 0
    
    if weekend_avg > 0 and weekday_avg > 0:
        weekend_pct = ((weekend_avg - weekday_avg) / weekday_avg) * 100
        if abs(weekend_pct) > 15:  # Only mention if significant difference
            if weekend_pct > 0:
                insights.append(
                    f"Weekend sales are {weekend_pct:.0f}% higher than weekdays (€{weekend_avg:,.0f} vs €{weekday_avg:,.0f})."
                )
            else:
                insights.append(
                    f"Weekday sales are {abs(weekend_pct):.0f}% higher than weekends (€{weekday_avg:,.0f} vs €{weekend_avg:,.0f})."
                )
    
    return insights


def generate_actionable_insights(prod: pd.DataFrame, daily: pd.DataFrame, ctx: WeeklyContext, limit: int = 9) -> List[str]:
    """Turn product_insights_detailed rows and daily sales into human-readable insights."""
    insights: List[str] = []
    suggestion_line: Optional[str] = None
    
    # Add day-of-week trend analysis first - only the strongest day (position 1)
    day_trends = analyze_day_of_week_trends(daily)
    # Only take the first day-of-week insight (strongest day)
    if day_trends:
        insights.append(day_trends[0])
    
    if prod.empty:
        if not insights:
            return ["No product insight data available for this week."]
        return insights

    # Try exact match first, then look for dates within the week (week_start to week_start + 6 days)
    current = prod[prod["period_start_date"] == ctx.week_start]
    if current.empty:
        # Try to find data for any date in the current week
        week_end = ctx.week_start + timedelta(days=6)
        current = prod[
            (prod["period_start_date"] >= ctx.week_start) & 
            (prod["period_start_date"] <= week_end)
        ]
    if current.empty:
        # Try to find the most recent data before or on this week
        current = prod[prod["period_start_date"] <= ctx.week_start]
        if not current.empty:
            # Get the most recent period
            most_recent_date = current["period_start_date"].max()
            current = current[current["period_start_date"] == most_recent_date]
    
    if current.empty:
        if not insights:
            return ["No product-period rows for this week in product_insights_detailed.csv."]
        return insights

    # Collect positive insights (rising products) - positions 2-4
    # Lower revenue threshold (€50) for positives since large % changes often come from smaller bases
    positive_insights: List[str] = []
    if "revenue_change_pct" in current.columns and "total_revenue" in current.columns:
        rising = current[
            (current["revenue_change_pct"] >= 0.10) & 
            (current["total_revenue"] > 50.0) &  # Lower threshold for positives (€50)
            (current["revenue_last_period"].fillna(0) > 0)  # Must have had revenue last week
        ].sort_values("revenue_change_pct", ascending=False).head(3)
        
        for _, row in rising.iterrows():
            pct = int(round(row["revenue_change_pct"] * 100))
            curr_rev = float(row.get("total_revenue", 0.0) or 0.0)
            prev_rev = float(row.get("revenue_last_period", 0.0) or 0.0)
            positive_insights.append(
                f"**{row['item_name']}** up {pct}% vs last week at {row['location']} "
                f"(€{prev_rev:,.0f} → €{curr_rev:,.0f})."
            )
    else:
        # Fallback to old logic if columns not available
        rising = current[current["is_rising"]].sort_values("units_change_pct", ascending=False).head(3)
        for _, row in rising.iterrows():
            pct = int(round(row["units_change_pct"] * 100))
            curr_rev = float(row.get("total_revenue", 0.0) or 0.0)
            prev_rev = float(row.get("revenue_last_period", 0.0) or 0.0)
            positive_insights.append(
                f"**{row['item_name']}** up {pct}% vs last week at {row['location']} "
                f"(€{prev_rev:,.0f} → €{curr_rev:,.0f})."
            )

    # Collect negative insights (declining products) - positions 5-7
    negative_insights: List[str] = []
    if "revenue_change_pct" in current.columns and "total_revenue" in current.columns:
        declining = current[
            (current["revenue_change_pct"] <= -0.10) & 
            (current["total_revenue"] > 200.0) &
            (current["revenue_last_period"].fillna(0) > 0)  # Must have had revenue last week
        ].sort_values("revenue_change_pct", ascending=True).head(3)
        
        for _, row in declining.iterrows():
            pct = int(round(abs(row["revenue_change_pct"] * 100)))
            curr_rev = float(row.get("total_revenue", 0.0) or 0.0)
            prev_rev = float(row.get("revenue_last_period", 0.0) or 0.0)
            negative_insights.append(
                f"**{row['item_name']}** down {pct}% vs last week at {row['location']} "
                f"(€{prev_rev:,.0f} → €{curr_rev:,.0f})."
            )
    else:
        # Fallback to old logic if columns not available
        declining = current[current["is_declining"]].sort_values("units_change_pct").head(3)
        for _, row in declining.iterrows():
            pct = int(round(abs(row["units_change_pct"] * 100)))
            curr_rev = float(row.get("total_revenue", 0.0) or 0.0)
            prev_rev = float(row.get("revenue_last_period", 0.0) or 0.0)
            negative_insights.append(
                f"**{row['item_name']}** down {pct}% vs last week at {row['location']} "
                f"(€{prev_rev:,.0f} → €{curr_rev:,.0f})."
            )

    # Add positives first (positions 2-4), then negatives (positions 5-7)
    insights.extend(positive_insights)
    insights.extend(negative_insights)

    # Collect one seasonal insight (position 8) - only if it's a seasonal peak with metric
    seasonal_insight: Optional[str] = None
    if "is_seasonal_peak" in current.columns and "season_mean_revenue" in current.columns and "total_revenue" in current.columns:
        seasonal_peaks = current[
            (current["is_seasonal_peak"] == True) &
            (current["total_revenue"] > 200.0) &  # Only show if significant revenue
            (current["season_mean_revenue"].notna()) &  # Must have seasonal average data
            (current["season_mean_revenue"] > 0)  # Avoid division by zero
        ].sort_values("total_revenue", ascending=False).head(1)  # Just one seasonal insight
        
        if not seasonal_peaks.empty:
            row = seasonal_peaks.iloc[0]
            curr_rev = float(row.get("total_revenue", 0.0) or 0.0)
            season_avg = float(row.get("season_mean_revenue", 0.0) or 0.0)
            season = str(row.get("season", "")).lower()
            pct_above = ((curr_rev - season_avg) / season_avg * 100) if season_avg > 0 else 0
            
            seasonal_insight = (
                f"**{row['item_name']}** is a strong {season} performer at {row['location']} "
                f"(€{curr_rev:,.0f} this week vs €{season_avg:,.0f} {season} average, "
                f"{pct_above:+.0f}% vs seasonal norm)."
            )

    # Cross-check top product with day-of-week and add one suggestion-style insight
    try:
        # Determine a "top product" by units this period
        if not current.empty:
            top_row = current.sort_values("total_units", ascending=False).iloc[0]
            top_name = str(top_row.get("item_name", "")).strip()
            top_location = str(top_row.get("location", "")).strip()

            # Re-compute day-of-week strengths on daily data
            if not daily.empty and "Date" in daily.columns and "Total Sales" in daily.columns:
                df_day = daily.copy()
                df_day["Date"] = pd.to_datetime(df_day["Date"])
                df_day["DayOfWeek"] = df_day["Date"].dt.day_name()
                df_day["DayOfWeekNum"] = df_day["Date"].dt.dayofweek
                day_avg = df_day.groupby("DayOfWeek")["Total Sales"].mean()

                if not day_avg.empty and top_name:
                    strongest_day = day_avg.sort_values(ascending=False).index[0]
                    weakest_day = day_avg.sort_values(ascending=True).index[0]

                    # Prefer suggesting action on the weakest day, if it is meaningfully below average
                    overall_avg = day_avg.mean()
                    weakest_avg = day_avg.loc[weakest_day]
                    weakest_pct = ((weakest_avg - overall_avg) / overall_avg * 100) if overall_avg else 0

                    if weakest_pct < -10:
                        suggestion_line = (
                            f"Consider promoting **{top_name}** at {top_location} on **{weakest_day}**, "
                            f"where sales are currently {abs(weakest_pct):.0f}% below the weekly average."
                        )
                    else:
                        suggestion_line = (
                            f"Consider featuring **{top_name}** at {top_location} more heavily on **{strongest_day}** "
                            "to maximise performance on your busiest trading day."
                        )
    except Exception:
        # Never let suggestion generation break the report
        pass

    # Deduplicate and trim
    deduped: List[str] = []
    seen = set()
    # First add all insights (positions 1-7: day trend, positives, negatives)
    for line in insights:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
        if len(deduped) >= (limit - 2):  # Reserve space for seasonal (8) and suggestion (9)
            break

    # Add seasonal insight at position 8
    if seasonal_insight and seasonal_insight not in deduped:
        deduped.append(seasonal_insight)

    # Force the suggestion line to be present as position 9 when we have one
    if suggestion_line:
        # Remove it if it's already in the list, we'll re-add it at the end
        deduped = [l for l in deduped if l != suggestion_line]
        # If we're at the limit, drop the last non-suggestion insight to make room
        if limit and len(deduped) >= limit:
            deduped = deduped[: limit - 1]
        # Append suggestion as the final insight (position 9)
        deduped.append(suggestion_line)
    if not deduped:
        deduped.append("No significant week-on-week changes detected.")
    return deduped


def business_year_periods(report_date: date) -> Tuple[date, date, date, date]:
    """Return (current_start, current_end, prev_start, prev_end) for the business year (Dec 1 – Nov 30)."""
    if report_date.month >= 12:
        current_start = date(report_date.year, 12, 1)
        prev_start = date(report_date.year - 1, 12, 1)
    else:
        current_start = date(report_date.year - 1, 12, 1)
        prev_start = date(report_date.year - 2, 12, 1)

    current_end = report_date
    prev_end = date(report_date.year - 1, report_date.month, report_date.day)
    if report_date.month == 2 and report_date.day == 29:
        prev_end = date(report_date.year - 1, 2, 28)

    return current_start, current_end, prev_start, prev_end


def format_yearly_period_caption(report_date: date) -> str:
    """Human-readable date range for the Yearly section (DD/MM)."""
    current_start, current_end, prev_start, prev_end = business_year_periods(report_date)

    def fmt(d: date) -> str:
        return d.strftime("%d/%m/%Y")

    return (
        f"Based on sales from {fmt(current_start)} to {fmt(current_end)}, "
        f"compared with {fmt(prev_start)} to {fmt(prev_end)}"
    )


def calculate_business_year_to_date_pct_change(ledger: pd.DataFrame, ctx: WeeklyContext) -> float:
    """Calculate business year-to-date percentage change (Dec 1 to current date vs Dec 1 last year to same date last year)."""
    current_by_start, current_by_end, prev_by_start, prev_by_end = business_year_periods(ctx.report_date)
    
    current_period = ledger[
        (ledger["transaction_date"] >= current_by_start) &
        (ledger["transaction_date"] <= current_by_end)
    ]
    prev_period = ledger[
        (ledger["transaction_date"] >= prev_by_start) &
        (ledger["transaction_date"] <= prev_by_end)
    ]
    
    # Calculate total revenue for each period
    current_total = current_period["net_revenue"].sum()
    prev_total = prev_period["net_revenue"].sum()
    
    # Calculate percentage change
    if prev_total > 0:
        pct_change = ((current_total - prev_total) / prev_total) * 100.0
    else:
        pct_change = 0.0
    
    return pct_change


def generate_yearly_insights(ledger: pd.DataFrame, ctx: WeeklyContext) -> List[str]:
    """Generate insights for Yearly section showing business year-to-date % changes with revenue amounts."""
    insights: List[str] = []
    business_year_start, current_date, prev_business_year_start, prev_year_date = business_year_periods(
        ctx.report_date
    )

    current_period = ledger[
        (ledger["transaction_date"] >= business_year_start) &
        (ledger["transaction_date"] <= current_date)
    ]
    prev_period = ledger[
        (ledger["transaction_date"] >= prev_business_year_start) &
        (ledger["transaction_date"] <= prev_year_date)
    ]
    
    # Calculate totals
    current_total_rev = current_period["net_revenue"].sum() if not current_period.empty else 0.0
    prev_total_rev = prev_period["net_revenue"].sum() if not prev_period.empty else 0.0
    total_pct_change = ((current_total_rev - prev_total_rev) / prev_total_rev * 100) if prev_total_rev > 0 else 0.0
    
    # Helper function to format revenue in K format
    def format_rev_k(amount: float) -> str:
        if amount >= 1000:
            return f"{amount/1000:.0f}K"
        return f"{amount:.0f}"
    
    # Calculate by location (Mumma and Shack)
    if "location" in current_period.columns:
        current_by_loc = current_period.groupby("location")["net_revenue"].sum()
        prev_by_loc = prev_period.groupby("location")["net_revenue"].sum()
        
        # Mumma
        current_mumma = current_by_loc.get("Mumma", 0.0)
        prev_mumma = prev_by_loc.get("Mumma", 0.0)
        mumma_pct_change = ((current_mumma - prev_mumma) / prev_mumma * 100) if prev_mumma > 0 else 0.0
        insights.append(f"**Mumma**: {mumma_pct_change:+.1f}% ({format_rev_k(current_mumma)} v {format_rev_k(prev_mumma)})")
        
        # Shack
        current_shack = current_by_loc.get("Shack", 0.0)
        prev_shack = prev_by_loc.get("Shack", 0.0)
        shack_pct_change = ((current_shack - prev_shack) / prev_shack * 100) if prev_shack > 0 else 0.0
        insights.append(f"**Shack**: {shack_pct_change:+.1f}% ({format_rev_k(current_shack)} v {format_rev_k(prev_shack)})")
    
    # Total (changed from YoY)
    insights.append(f"**Total**: {total_pct_change:+.1f}% ({format_rev_k(current_total_rev)} v {format_rev_k(prev_total_rev)})")
    
    return insights


def generate_weekly_summary_insights(daily: pd.DataFrame, ctx: WeeklyContext, weekly_kpis: dict) -> List[str]:
    """Generate insights for Weekly Summary section."""
    insights: List[str] = []
    this_week = weekly_kpis.get("this", {})
    prev_week = weekly_kpis.get("prev", {})
    
    # Best day for revenue
    best_day = this_week.get("best_day")
    best_day_rev = this_week.get("best_day_revenue", 0.0)
    if best_day:
        day_name = best_day.strftime("%A")
        insights.append(f"Best day for revenue: **{day_name}** (€{best_day_rev:,.0f})")
    
    # Worst day for revenue (excluding closed days - days with no sales)
    if "Date" in daily.columns and "Total Sales" in daily.columns:
        df = daily.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        week_start = pd.Timestamp(ctx.week_start)
        week_end = week_start + timedelta(days=6)
        week_data = df[(df["Date"] >= week_start) & (df["Date"] <= week_end)]
        
        if not week_data.empty:
            # Group by date and sum total sales (across all locations)
            by_date = week_data.groupby("Date")["Total Sales"].sum()
            # Only consider days with sales > 0 (exclude closed days)
            by_date_with_sales = by_date[by_date > 0]
            if not by_date_with_sales.empty:
                worst_day_date = by_date_with_sales.idxmin()
                worst_day_rev = by_date_with_sales.min()
                worst_day_name = worst_day_date.strftime("%A")
                insights.append(f"Worst day for revenue: **{worst_day_name}** (€{worst_day_rev:,.0f})")
    
    # Revenue by Location with +/- change vs previous week
    this_by_loc = this_week.get("by_location", {})
    prev_by_loc = prev_week.get("by_location", {})
    for loc, this_rev in this_by_loc.items():
        prev_rev = prev_by_loc.get(loc, 0.0)
        if prev_rev > 0:
            change_pct = ((this_rev - prev_rev) / prev_rev) * 100
            change_str = f"{change_pct:+.1f}%" if change_pct != 0 else "0%"
            insights.append(f"**{loc}**: €{this_rev:,.0f} ({change_str} vs previous week)")
        else:
            insights.append(f"**{loc}**: €{this_rev:,.0f}")
    
    return insights


def generate_monthly_progress_insights(daily: pd.DataFrame, ctx: WeeklyContext) -> List[str]:
    """Generate insights for Monthly Progress section."""
    insights: List[str] = []
    
    if "Date" in daily.columns and "Total Sales" in daily.columns:
        df = daily.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        current_date = df["Date"].max()
        current_month = current_date.month
        current_year = current_date.year
        
        # Filter to current month
        month_data = df[(df["Date"].dt.month == current_month) & (df["Date"].dt.year == current_year)]
        
        if not month_data.empty:
            # Group by date and sum total sales (across all locations)
            by_date = month_data.groupby("Date")["Total Sales"].sum()
            # Only consider days with sales > 0 (exclude closed days)
            by_date_with_sales = by_date[by_date > 0]
            if not by_date_with_sales.empty:
                best_day_date = by_date_with_sales.idxmax()
                best_day_rev = by_date_with_sales.max()
                best_day_name = best_day_date.strftime("%A, %B %d")
                insights.append(f"Best day of month: **{best_day_name}** (€{best_day_rev:,.0f})")
                
                worst_day_date = by_date_with_sales.idxmin()
                worst_day_rev = by_date_with_sales.min()
                worst_day_name = worst_day_date.strftime("%A, %B %d")
                insights.append(f"Worst day of month: **{worst_day_name}** (€{worst_day_rev:,.0f})")
    
    return insights


def generate_product_insights(ledger: pd.DataFrame, ctx: WeeklyContext) -> List[str]:
    """Generate insights for Product Section."""
    insights: List[str] = []
    
    # Filter to current week
    week = filter_week(ledger, ctx, "transaction_date")
    if week.empty:
        return insights
    
    # Top product by revenue
    by_rev = week.groupby("item_name")["net_revenue"].sum().sort_values(ascending=False)
    if not by_rev.empty:
        top_product_rev = by_rev.index[0]
        top_product_rev_amount = by_rev.iloc[0]
        insights.append(f"Top product by revenue: **{top_product_rev}** (€{top_product_rev_amount:,.0f})")
    
    # Top product by items sold
    by_qty = week.groupby("item_name")["quantity"].sum().sort_values(ascending=False)
    if not by_qty.empty:
        top_product_qty = by_qty.index[0]
        top_product_qty_amount = by_qty.iloc[0]
        insights.append(f"Top Product by items sold: **{top_product_qty}** ({int(top_product_qty_amount):,} items)")
    
    # Top drinks (20% tax rate) by revenue and items sold - use MONTHLY data
    if "tax_rate" in ledger.columns:
        current_month_start = date(ctx.week_start.year, ctx.week_start.month, 1)
        current_month_end = (current_month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        month_data = ledger[
            (ledger["transaction_date"] >= current_month_start) &
            (ledger["transaction_date"] <= current_month_end)
        ]
        drinks = month_data[month_data["tax_rate"].round(1) == 20.0]
        if not drinks.empty:
            by_drink_rev = drinks.groupby("item_name")["net_revenue"].sum().sort_values(ascending=False)
            if not by_drink_rev.empty:
                top_drink_rev = by_drink_rev.index[0]
                top_drink_rev_amount = by_drink_rev.iloc[0]
                insights.append(f"Top Drink (20%) by revenue: **{top_drink_rev}** (€{top_drink_rev_amount:,.0f})")
            
            by_drink_qty = drinks.groupby("item_name")["quantity"].sum().sort_values(ascending=False)
            if not by_drink_qty.empty:
                top_drink_qty = by_drink_qty.index[0]
                top_drink_qty_amount = by_drink_qty.iloc[0]
                insights.append(f"Top Drink (20%) by item sold: **{top_drink_qty}** ({int(top_drink_qty_amount):,} items)")
    
    return insights


def calculate_price_increase_scenarios(ledger: pd.DataFrame, ctx: WeeklyContext) -> List[str]:
    """Calculate price increase scenarios for Action section."""
    actions: List[str] = []
    
    # Filter to current week
    week = filter_week(ledger, ctx, "transaction_date")
    if week.empty:
        return actions
    
    # Product with highest revenue
    by_rev = week.groupby("item_name")["net_revenue"].sum().sort_values(ascending=False)
    if not by_rev.empty:
        top_product_rev = by_rev.index[0]
        top_rev_amount = by_rev.iloc[0]
        # 5% price increase scenario
        additional_rev_5pct = top_rev_amount * 0.05
        actions.append(f"A 5% price increase on **{top_product_rev}** would have produced €{additional_rev_5pct:,.0f} more revenue.")
    
    # Product with most items sold
    by_qty = week.groupby("item_name")["quantity"].sum().sort_values(ascending=False)
    if not by_qty.empty:
        top_product_qty = by_qty.index[0]
        top_qty = by_qty.iloc[0]
        # Get revenue for this product to calculate 10% increase
        product_rev = week[week["item_name"] == top_product_qty]["net_revenue"].sum()
        # 10% price increase scenario
        additional_rev_10pct = product_rev * 0.10
        actions.append(f"A 10% price increase on **{top_product_qty}** would have produced €{additional_rev_10pct:,.0f} more revenue.")
    
    return actions


def _format_insight_line(line: str) -> str:
    """Convert markdown-style **bold** markers in an insight line to HTML <strong> tags."""
    if not line:
        return line
    # Replace all **text** segments with <strong>text</strong>
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)


def make_monthly_sales_chart(daily: pd.DataFrame, ctx: WeeklyContext, out_dir: Path) -> Optional[Path]:
    """Monthly cumulative sales chart: current year vs last year, Clove green with gradient fill."""
    if daily.empty:
        return None
    df = daily.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    
    # Get current month and same month last year
    current_date = ctx.report_date
    current_year = current_date.year
    current_month_num = current_date.month
    last_year = current_year - 1
    
    # Filter to current month and same month last year
    current_month_data = df[
        (df["Date"].dt.year == current_year) & 
        (df["Date"].dt.month == current_month_num)
    ]
    last_year_month_data = df[
        (df["Date"].dt.year == last_year) & 
        (df["Date"].dt.month == current_month_num)
    ]
    
    if current_month_data.empty and last_year_month_data.empty:
        return None
    
    # Get month name for display
    month_name = current_date.strftime("%B")
    
    # Aggregate by date (sum across all locations) and calculate cumulative
    current_by_date = current_month_data.groupby("Date")["Total Sales"].sum().sort_index()
    last_year_by_date = last_year_month_data.groupby("Date")["Total Sales"].sum().sort_index()
    current_cumulative = current_by_date.cumsum()
    last_year_cumulative = last_year_by_date.cumsum()
    
    # Prepare cumulative data
    current_cum_data = [{"Day": date_val.day, "Cumulative": cum_sales} for date_val, cum_sales in current_cumulative.items()]
    last_year_cum_data = [{"Day": date_val.day, "Cumulative": cum_sales} for date_val, cum_sales in last_year_cumulative.items()]
    
    # Clove green
    CLOVE_GREEN = "#16A34A"
    
    fig = go.Figure()
    
    if last_year_cum_data:
        last_year_cum_df = pd.DataFrame(last_year_cum_data)
        # Gradient fill under last year's line: green at line, smooth fade to white at x-axis
        # Plotly has no native gradient; many bands approximate a smooth gradient (like Lightspeed app)
        n_bands = 80
        for i in range(n_bands):
            y_band = last_year_cum_df["Cumulative"] * (i + 1) / n_bands
            # t: 0 at bottom -> 1 at top (at the line)
            t = (i + 1) / n_bands
            # Interpolate from white (bottom) to green #16A34A (22,163,74) at top
            r = int(255 - (255 - 22) * t)
            g = int(255 - (255 - 163) * t)
            b = int(255 - (255 - 74) * t)
            opacity = 0.1 + 0.25 * t  # subtle at bottom, stronger at top
            fillcolor = f"rgba({r}, {g}, {b}, {opacity:.3f})"
            fig.add_trace(go.Scatter(
                x=last_year_cum_df["Day"],
                y=y_band,
                fill="tonexty" if i > 0 else "tozeroy",
                fillcolor=fillcolor,
                line=dict(width=0),
                showlegend=False,
            ))
        # Last year line (grey, thin)
        fig.add_trace(go.Scatter(
            x=last_year_cum_df["Day"],
            y=last_year_cum_df["Cumulative"],
            name=f"{last_year}",
            line=dict(color="#808080", width=1),
            mode="lines",
        ))
    
    # Current year cumulative line (no markers, no fill)
    if current_cum_data:
        current_cum_df = pd.DataFrame(current_cum_data)
        fig.add_trace(go.Scatter(
            x=current_cum_df["Day"],
            y=current_cum_df["Cumulative"],
            name=f"{current_year}",
            line=dict(color=CLOVE_GREEN, width=3),
            mode="lines",
        ))
    
    fig.update_layout(
        plot_bgcolor="#F5F5F5",
        paper_bgcolor="#F5F5F5",
        font=dict(color="#000000", size=13, family="Arial, sans-serif"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color="#000000"),
            bgcolor="rgba(245, 245, 245, 0.9)",
            bordercolor="#000000",
            borderwidth=1,
        ),
        xaxis=dict(
            title="Day of Month",
            title_font=dict(size=14, color="#000000"),
            tickfont=dict(size=12, color="#000000"),
            gridcolor="rgba(0, 0, 0, 0.2)",
            gridwidth=1,
            dtick=5,
            tickmode="linear",
        ),
        yaxis=dict(
            title="Cumulative Sales (€)",
            title_font=dict(size=14, color="#000000"),
            tickfont=dict(size=12, color="#000000"),
            gridcolor="rgba(0, 0, 0, 0.2)",
            gridwidth=1,
        ),
        title=dict(
            text=f"{month_name} Cumulative Sales: {current_year} vs {last_year}",
            font=dict(size=18, color="#000000", family="Arial, sans-serif"),
            x=0.5,
            xanchor="center",
        ),
        hovermode="x unified",
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    chart_path = out_dir / "monthly_sales_comparison.png"
    fig.write_image(str(chart_path), scale=2)
    return chart_path


def make_weekly_sales_chart(daily: pd.DataFrame, ctx: WeeklyContext, out_dir: Path) -> Optional[Path]:
    """Weekly bar chart comparing current week vs same week last year."""
    if daily.empty:
        return None
    df = daily.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    
    # Get current week dates
    week_start = pd.Timestamp(ctx.week_start)
    week_end = week_start + timedelta(days=6)
    
    # Get same week last year
    last_year_week_start = week_start - timedelta(days=365)
    last_year_week_end = last_year_week_start + timedelta(days=6)
    
    # Filter to current week and last year's same week
    current_week = df[(df["Date"] >= week_start) & (df["Date"] <= week_end)]
    last_year_week = df[(df["Date"] >= last_year_week_start) & (df["Date"] <= last_year_week_end)]
    
    if current_week.empty and last_year_week.empty:
        return None
    
    # Aggregate by week and location
    comparison_data = []
    locations = df["Location"].unique() if "Location" in df.columns else [None]
    
    # Calculate totals for combined "Total" bar
    current_total_sales = current_week["Total Sales"].sum() if not current_week.empty else 0
    last_year_total_sales = last_year_week["Total Sales"].sum() if not last_year_week.empty else 0
    
    week_label = f"Week {week_start.strftime('%Y-%m-%d')}"
    last_year_label = f"Week {last_year_week_start.strftime('%Y-%m-%d')}"
    
    # Add combined Total bar
    comparison_data.append({
        "Period": week_label,
        "Sales": current_total_sales,
        "Location": "Total"
    })
    comparison_data.append({
        "Period": last_year_label,
        "Sales": last_year_total_sales,
        "Location": "Total"
    })
    
    # Add individual location bars
    for location in locations:
        if location:  # Skip None locations
            curr_loc = current_week[current_week["Location"] == location]
            last_loc = last_year_week[last_year_week["Location"] == location]
            
            current_sales = curr_loc["Total Sales"].sum() if not curr_loc.empty else 0
            last_year_sales = last_loc["Total Sales"].sum() if not last_loc.empty else 0
            
            comparison_data.append({
                "Period": week_label,
                "Sales": current_sales,
                "Location": location
            })
            comparison_data.append({
                "Period": last_year_label,
                "Sales": last_year_sales,
                "Location": location
            })
    
    if not comparison_data:
        return None
    
    comp_df = pd.DataFrame(comparison_data)
    
    # Create bar chart with enhanced styling
    if "Location" in comp_df.columns and len(comp_df["Location"].unique()) > 1:
        fig = px.bar(
            comp_df,
            x="Period",
            y="Sales",
            color="Location",
            barmode="group",
            title=f"Weekly Sales Comparison (Current Week vs Same Week Last Year)",
            color_discrete_sequence=["#EBFB71", "#000000", "#F5F5F5"],  # Brand colors
        )
    else:
        # Get unique period labels for color mapping using brand colors
        periods = comp_df["Period"].unique()
        color_map = {periods[0]: "#EBFB71", periods[1]: "#F5F5F5"} if len(periods) >= 2 else {periods[0]: "#EBFB71"}
        fig = px.bar(
            comp_df,
            x="Period",
            y="Sales",
            color="Period",
            title=f"Weekly Sales Comparison (Current Week vs Same Week Last Year)",
            color_discrete_map=color_map,
        )
    
    # Enhanced styling for weekly chart with brand colors
    fig.update_layout(
        plot_bgcolor="#F5F5F5",  # Brand light gray background
        paper_bgcolor="#F5F5F5",  # Brand light gray background
        font=dict(color="#000000", size=13, family="Arial, sans-serif"),  # Brand black text
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color="#000000"),  # Brand black text
            bgcolor="rgba(245, 245, 245, 0.9)",  # Brand light gray
            bordercolor="#000000",  # Brand black border
            borderwidth=1,
        ),
        xaxis=dict(
            title="Week",
            title_font=dict(size=14, color="#000000"),  # Brand black
            tickfont=dict(size=12, color="#000000"),  # Brand black
            gridcolor="rgba(0, 0, 0, 0.2)",  # Light black grid for subtle lines
            gridwidth=1,
        ),
        yaxis=dict(
            title="Total Sales (€)",
            title_font=dict(size=14, color="#000000"),  # Brand black
            tickfont=dict(size=12, color="#000000"),  # Brand black
            gridcolor="rgba(0, 0, 0, 0.2)",  # Light black grid for subtle lines
            gridwidth=1,
        ),
        title=dict(
            text="Weekly Sales Comparison (Current Week vs Same Week Last Year)",
            font=dict(size=18, color="#000000", family="Arial, sans-serif"),  # Brand black
            x=0.5,
            xanchor="center",
        ),
        showlegend=True,
        bargap=0.3,
        bargroupgap=0.1,
    )
    fig.update_traces(
        marker=dict(
            line=dict(width=2, color="#000000"),  # Brand black borders
            opacity=0.9,
        ),
        texttemplate="€%{y:,.0f}",
        textposition="outside",
        textfont=dict(color="#000000", size=11, family="Arial, sans-serif"),  # Brand black text
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    chart_path = out_dir / "weekly_sales_comparison.png"
    fig.write_image(str(chart_path), scale=2)
    return chart_path


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _relative_luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)

    def _linear(channel: int) -> float:
        c = channel / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def _interpolate_scale_color(t: float, scale: list[str]) -> str:
    t = max(0.0, min(1.0, t))
    if len(scale) == 1:
        return scale[0]
    segments = len(scale) - 1
    pos = t * segments
    idx = min(int(pos), segments - 1)
    frac = pos - idx
    c0, c1 = _hex_to_rgb(scale[idx]), _hex_to_rgb(scale[idx + 1])
    rgb = tuple(int(round(a + (b - a) * frac)) for a, b in zip(c0, c1))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _text_color_for_bar_fill(fill_hex: str, threshold: float = 0.75) -> str:
    """White text on dark/grey fills; black only on very pale or bright colours."""
    return "#FFFFFF" if _relative_luminance(fill_hex) < threshold else "#000000"


def _bar_label_colors(values: pd.Series, scale: list[str]) -> list[str]:
    vmin, vmax = float(values.min()), float(values.max())
    colors: list[str] = []
    for value in values:
        t = (float(value) - vmin) / (vmax - vmin) if vmax > vmin else 0.0
        colors.append(_text_color_for_bar_fill(_interpolate_scale_color(t, scale)))
    return colors


def make_top_products_chart(ledger: pd.DataFrame, ctx: WeeklyContext, out_dir: Path) -> Optional[Path]:
    week = filter_week(ledger, ctx, "transaction_date")
    if week.empty:
        return None

    # Current week revenue by product
    current_rev = (
        week.groupby("item_name")["net_revenue"]
        .sum()
        .reset_index(name="net_revenue")
    )

    # Previous week revenue by product for % change calculation
    prev_week = ledger[
        (ledger["transaction_date"] >= ctx.prev_week_start)
        & (ledger["transaction_date"] < ctx.week_start)
    ]
    prev_rev = (
        prev_week.groupby("item_name")["net_revenue"]
        .sum()
        .reset_index(name="prev_net_revenue")
        if not prev_week.empty
        else pd.DataFrame(columns=["item_name", "prev_net_revenue"])
    )

    # Merge and compute percentage change vs last week
    top = (
        current_rev.merge(prev_rev, on="item_name", how="left")
        .sort_values("net_revenue", ascending=False)
        .head(10)
    )
    top["prev_net_revenue"] = top["prev_net_revenue"].fillna(0.0)
    top["pct_change"] = top.apply(
        lambda row: ((row["net_revenue"] - row["prev_net_revenue"]) / row["prev_net_revenue"] * 100.0)
        if row["prev_net_revenue"] > 0
        else None,
        axis=1,
    )
    # Label for display inside the bar
    def _fmt_pct(p):
        if p is None:
            return "n/a"
        if abs(p) < 0.5:
            return "0%"
        return f"{p:+.0f}%"

    top["pct_label"] = top["pct_change"].map(_fmt_pct)

    # Enhanced bar chart with gradient colors
    fig = px.bar(
        top,
        x="net_revenue",
        y="item_name",
        orientation="h",
        title="Top 10 Products by Revenue (This Week)",
        color="net_revenue",
        color_continuous_scale=["#EBFB71", "#F5F5F5", "#000000"],  # Brand color gradient: yellow to gray to black
    )
    # Enhanced styling for top products chart with brand colors
    fig.update_layout(
        plot_bgcolor="#F5F5F5",  # Brand light gray background
        paper_bgcolor="#F5F5F5",  # Brand light gray background
        font=dict(color="#000000", size=13, family="Arial, sans-serif"),  # Brand black text
        yaxis=dict(
            autorange="reversed",
            title="",
            tickfont=dict(size=11, color="#000000"),  # Brand black
            gridcolor="rgba(0, 0, 0, 0.2)",  # Light black grid for subtle lines
            gridwidth=1,
        ),
        xaxis=dict(
            title="Revenue (€)",
            title_font=dict(size=14, color="#000000"),  # Brand black
            tickfont=dict(size=12, color="#000000"),  # Brand black
            gridcolor="rgba(0, 0, 0, 0.2)",  # Light black grid for subtle lines
            gridwidth=1,
            range=[0, top["net_revenue"].max() * 1.15],  # Add 15% padding to right for text labels
        ),
        title=dict(
            text="Top 10 Products by Revenue (This Week)",
            font=dict(size=18, color="#000000", family="Arial, sans-serif"),  # Brand black
            x=0.5,
            xanchor="center",
        ),
        showlegend=False,
        bargap=0.2,
        margin=dict(r=80, l=10, t=60, b=40),  # Extra right margin for text labels
    )
    # White on grey/black bars; black only on very pale / yellow fills
    revenue_color_scale = ["#EBFB71", "#F5F5F5", "#000000"]
    text_colors = _bar_label_colors(top["net_revenue"], revenue_color_scale)

    fig.update_traces(
        marker=dict(
            line=dict(width=2, color="#000000"),  # Brand black borders
            opacity=0.95,
        ),
        # Show percentage change vs last week inside each bar
        text=top["pct_label"],
        textposition="inside",
        textfont=dict(size=11, family="Arial, sans-serif"),  # Size/family fixed
        textfont_color=text_colors,
        hovertemplate=" %{y}<br>Revenue: €%{x:,.0f}<br>Change vs last week: %{text}<extra></extra>",
        cliponaxis=False,
    )

    chart_path = out_dir / "top_products.png"
    fig.write_image(str(chart_path), scale=2)
    return chart_path


def make_top_products_by_items_chart(ledger: pd.DataFrame, ctx: WeeklyContext, out_dir: Path) -> Optional[Path]:
    """Generate Top 10 Products by Items Sold chart."""
    week = filter_week(ledger, ctx, "transaction_date")
    if week.empty:
        return None
    
    # Current week quantity by product
    current_qty = (
        week.groupby("item_name")["quantity"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
    )
    
    if current_qty.empty:
        return None
    
    # Create bar chart with black to gray to orange color scale
    fig = px.bar(
        current_qty,
        x="quantity",
        y="item_name",
        orientation="h",
        title="Top 10 Products by Items Sold (This Week)",
        color="quantity",
        color_continuous_scale=["#000000", "#F5F5F5", "#FF6B35"],  # Black to gray to orange
    )
    
    # Enhanced styling for top products by items chart
    fig.update_layout(
        plot_bgcolor="#F5F5F5",  # Brand light gray background
        paper_bgcolor="#F5F5F5",  # Brand light gray background
        font=dict(color="#000000", size=13, family="Arial, sans-serif"),  # Brand black text
        yaxis=dict(
            autorange="reversed",
            title="",
            tickfont=dict(size=11, color="#000000"),  # Brand black
            gridcolor="rgba(0, 0, 0, 0.2)",  # Light black grid
            gridwidth=1,
        ),
        xaxis=dict(
            title="Items Sold",
            title_font=dict(size=14, color="#000000"),  # Brand black
            tickfont=dict(size=12, color="#000000"),  # Brand black
            gridcolor="rgba(0, 0, 0, 0.2)",  # Light black grid
            gridwidth=1,
            range=[0, current_qty["quantity"].max() * 1.15],  # Add padding for text labels
        ),
        title=dict(
            text="Top 10 Products by Items Sold (This Week)",
            font=dict(size=18, color="#000000", family="Arial, sans-serif"),  # Brand black
            x=0.5,
            xanchor="center",
        ),
        showlegend=False,
        bargap=0.2,
        margin=dict(r=80, l=10, t=60, b=40),  # Extra right margin for text labels
    )
    
    # Label colour follows each bar's fill (white on dark grey/black, black on pale/orange)
    items_color_scale = ["#000000", "#F5F5F5", "#FF6B35"]
    text_colors = _bar_label_colors(current_qty["quantity"], items_color_scale)

    fig.update_traces(
        marker=dict(
            line=dict(width=2, color="#000000"),  # Brand black borders
            opacity=0.95
        ),
        texttemplate="%{x:,}",
        textposition="inside",
        textfont=dict(size=11, family="Arial, sans-serif"),  # Size/family fixed
        textfont_color=text_colors,
        hovertemplate="%{y}<br>Items Sold: %{x:,}<extra></extra>",
        cliponaxis=False,
    )
    
    chart_path = out_dir / "top_products_by_items.png"
    fig.write_image(str(chart_path), scale=2)
    return chart_path


def make_category_chart(ledger: pd.DataFrame, ctx: WeeklyContext, out_dir: Path) -> Optional[Path]:
    week = filter_week(ledger, ctx, "transaction_date")
    if week.empty or "category" not in week.columns:
        return None
    
    # Clean category names by removing reference numbers
    week_clean = week.copy()
    week_clean["category_clean"] = week_clean["category"].astype(str).str.replace(
        r'\s*[-–—]\s*\d+.*$',  # Remove "- 12345" or "— 12345" patterns
        '',
        regex=True
    ).str.replace(
        r'\s*\(\d+.*?\)\s*$',  # Remove "(12345)" patterns
        '',
        regex=True
    ).str.replace(
        r'\s+\d+$',  # Remove trailing numbers with space
        '',
        regex=True
    ).str.strip()
    
    by_cat = (
        week_clean.groupby("category_clean")["net_revenue"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"category_clean": "category"})
    )

    # Enhanced pie chart with vibrant colors
    fig = px.pie(
        by_cat,
        values="net_revenue",
        names="category",
        title="Category Revenue Breakdown (This Week)",
        hole=0.5,
        color_discrete_sequence=["#EBFB71", "#000000", "#F5F5F5", "#D4D4D4", "#808080"],  # Brand colors + grayscale variations
    )
    # Enhanced styling for category pie chart
    fig.update_traces(
        textposition="outside",
        textinfo="percent+label",
        textfont=dict(color="#000000", size=12, family="Arial, sans-serif"),  # Brand black text
        marker=dict(
            line=dict(width=3, color="#000000"),  # Brand black borders for visibility on light background
        ),
        pull=[0.05] * len(by_cat),  # Slight pull effect for visual interest
        opacity=0.95,  # Opacity goes at trace level, not marker level for pie charts
    )
    fig.update_layout(
        plot_bgcolor="#F5F5F5",  # Brand light gray background
        paper_bgcolor="#F5F5F5",  # Brand light gray background
        font=dict(color="#000000", size=13, family="Arial, sans-serif"),  # Brand black text
        title=dict(
            text="Category Revenue Breakdown (This Week)",
            font=dict(size=18, color="#000000", family="Arial, sans-serif"),  # Brand black
            x=0.5,
            xanchor="center",
        ),
        legend=dict(
            font=dict(size=12, family="Arial, sans-serif", color="#000000"),  # Brand black text
            bgcolor="rgba(245, 245, 245, 0.9)",  # Brand light gray
            bordercolor="#000000",  # Brand black border
            borderwidth=1,
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.05,
        ),
    )

    chart_path = out_dir / "category_breakdown.png"
    fig.write_image(str(chart_path), scale=2)
    return chart_path


def build_html_report(
    ctx: WeeklyContext,
    yearly_insights: List[str],
    weekly_summary_insights: List[str],
    monthly_progress_insights: List[str],
    product_insights: List[str],
    price_increase_actions: List[str],
    weekly_kpis: dict,
    chart_paths: Iterable[Path],
) -> Tuple[str, Dict[Path, str]]:
    """Return HTML string for the weekly report with new structure."""
    
    # Helper function to render insights as HTML list items
    def render_insights_list(insights_list: List[str]) -> str:
        html_parts: List[str] = []
        for line in insights_list:
            formatted = _format_insight_line(line)
            html_parts.append(
                f"<li><img src='cid:clove_bullet_icon' alt='' "
                f"style='width:10px;height:10px;margin-right:6px;vertical-align:middle;' />{formatted}</li>"
            )
        return "".join(html_parts)

    # Format all insights
    yearly_insights_html = render_insights_list(yearly_insights)
    weekly_summary_insights_html = render_insights_list(weekly_summary_insights)
    monthly_progress_insights_html = render_insights_list(monthly_progress_insights)
    product_insights_html = render_insights_list(product_insights)
    price_increase_actions_html = render_insights_list(price_increase_actions)

    # Organize charts by section
    chart_cids = {}
    weekly_charts_html = []
    monthly_charts_html = []
    product_charts_html = []
    category_charts_html = []
    # Optional: Dropbox link for "Open Mumma Master" button
    master_link = os.getenv("MUMMA_MASTER_LINK")
    if master_link:
        open_master_button_html = (
            f'<a href="{master_link}" '
            f'style="display:inline-block;padding:8px 14px;'
            f'border-radius:999px;border:1px solid #16A34A;'
            f'color:#000000;text-decoration:none;font-size:13px;'
            f'background-color:#FFFFFF;">'
            f'Open Mumma Master</a>'
        )
    else:
        open_master_button_html = ""
    
    # Map chart filenames to friendly names, sections, and generate CIDs
    chart_names = {
        "weekly_sales_comparison.png": ("Weekly Sales Comparison", "weekly"),
        "monthly_sales_comparison.png": ("Monthly Cumulative Sales", "monthly"),
        "top_products.png": ("Top 10 Products by Revenue", "product"),
        "top_products_by_items.png": ("Top 10 Products by Items Sold", "product"),
        "category_breakdown.png": ("Category Revenue Breakdown", "category"),
    }
    
    for path in chart_paths:
        if path.exists():
            filename = path.name
            if filename in chart_names:
                title, section = chart_names[filename]
                # Make CID unique per chart by using filename stem (without extension)
                filename_stem = Path(filename).stem
                cid = f"{filename_stem}_{ctx.label.replace('-', '_')}"
                chart_cids[path] = cid
                # For category chart, don't add h3 title since chart already has title and section has h2
                if section == "category":
                    chart_html = (
                        f'<div style="margin-bottom: 24px;">'
                        f'<img src="cid:{cid}" alt="{title}" style="max-width: 100%; height: auto; border-radius: 8px;" />'
                        f'</div>'
                    )
                else:
                    chart_html = (
                        f'<div style="margin-bottom: 24px;">'
                        f'<h3 style="margin-bottom: 8px; color: #FFFFFF !important;">{title}</h3>'
                        f'<img src="cid:{cid}" alt="{title}" style="max-width: 100%; height: auto; border-radius: 8px;" />'
                        f'</div>'
                    )
                if section == "weekly":
                    weekly_charts_html.append(chart_html)
                elif section == "monthly":
                    monthly_charts_html.append(chart_html)
                elif section == "product":
                    product_charts_html.append(chart_html)
                elif section == "category":
                    category_charts_html.append(chart_html)
    
    weekly_charts_html_str = "".join(weekly_charts_html) if weekly_charts_html else ""
    monthly_charts_html_str = "".join(monthly_charts_html) if monthly_charts_html else ""
    product_charts_html_str = "".join(product_charts_html) if product_charts_html else ""
    category_charts_html_str = "".join(category_charts_html) if category_charts_html else ""
    yearly_period_caption = format_yearly_period_caption(ctx.report_date)

    html = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>MUMMA Weekly Insights Report</title>
      <style>
        /* Dark theme with white text for Gmail compatibility */
        body {{
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background-color: #050816 !important;
          color: #FFFFFF !important;
          padding: 24px;
        }}
        h1, h2, h3 {{
          color: #FFFFFF !important;
        }}
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
        .card-header h2 {{
          margin: 0;
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
        }}
        th, td {{
          padding: 6px 8px;
          color: #FFFFFF !important;
        }}
        th {{
          text-align: left;
          border-bottom: 1px solid #374151 !important;
          color: #FFFFFF !important;
        }}
        .pill {{
          display: inline-block;
          padding: 2px 8px;
          border-radius: 999px;
          background: #16A34A22;
          color: #BBF7D0;
          font-size: 11px;
        }}
        ul {{
          color: #FFFFFF !important;
          list-style-type: none;
          padding-left: 0;
          margin-left: 0;
        }}
        li {{
          color: #FFFFFF !important;
          margin-bottom: 8px;
        }}
      </style>
    </head>
    <body>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h1 style="margin:0;">MUMMA Weekly Report</h1>
        {open_master_button_html}
      </div>

      <!-- Yearly Section -->
      <div class="card">
        <div class="card-header">
          <h2>Yearly</h2>
        </div>
        <p style="margin-bottom: 12px; padding: 8px 10px; background-color: #1F2937; color: #D1D5DB; font-size: 13px; line-height: 1.45; border-radius: 6px;">{yearly_period_caption}</p>
        <ul>
          {yearly_insights_html}
        </ul>
      </div>

      <!-- Weekly Summary Section -->
      <div class="card">
        <div class="card-header">
          <h2>Weekly Summary</h2>
        </div>
        <ul>
          {weekly_summary_insights_html}
        </ul>
        {weekly_charts_html_str}
      </div>

      <!-- Monthly Progress Section -->
      <div class="card">
        <div class="card-header">
          <h2>Monthly Progress</h2>
        </div>
        <ul>
          {monthly_progress_insights_html}
        </ul>
        {monthly_charts_html_str}
      </div>

      <!-- Product Section -->
      <div class="card">
        <div class="card-header">
          <h2>Product Section</h2>
        </div>
        <ul>
          {product_insights_html}
        </ul>
        {product_charts_html_str}
        <h3 style="margin-top:16px;">Action</h3>
        <ul>
          {price_increase_actions_html}
        </ul>
      </div>

      <!-- Category Breakdown Section -->
      <div class="card">
        <div class="card-header">
          <h2>Category Breakdown</h2>
        </div>
        {category_charts_html_str}
      </div>
    </body>
    </html>
    """
    return html, chart_cids


def html_for_browser_preview(
    html: str,
    chart_paths: Iterable[Path],
    chart_cids: Dict[Path, str],
    reports_dir: Path,
) -> str:
    """Replace email Content-ID image refs with relative paths for local HTML preview."""
    preview = html
    for path in chart_paths:
        if path.exists() and path in chart_cids:
            rel = path.relative_to(reports_dir).as_posix()
            preview = preview.replace(f"cid:{chart_cids[path]}", rel)
    # Bullet icon is optional in email; skip broken cid in browser preview
    preview = preview.replace("cid:clove_bullet_icon", "")
    return preview


def render_pdf(html: str, output_path: Path) -> None:
    if HTML is None:
        logging.warning("WeasyPrint not installed – skipping PDF generation.")
        return
    HTML(string=html).write_pdf(str(output_path))


def send_email_with_report(
    ctx: WeeklyContext,
    html_body: str,
    chart_paths: Iterable[Path],
    pdf_path: Optional[Path],
    chart_cids: Optional[Dict[Path, str]] = None,
    ledger: Optional[pd.DataFrame] = None,
) -> None:
    """Send weekly report email via Resend API (handles SPF/DKIM/DMARC automatically)."""
    if not RESEND_AVAILABLE:
        raise RuntimeError("Resend package not installed. Install with: pip install resend")

    resend_api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL", "noreply@clove.solutions")
    recipient_raw = os.getenv("MUMMA_EMAIL_RECIPIENT", "davevondavrosh@gmail.com")
    recipient_emails = [e.strip() for e in recipient_raw.split(",") if e.strip()]
    cc_email = os.getenv("MUMMA_EMAIL_CC")
    bcc_raw = os.getenv("MUMMA_EMAIL_BCC")
    bcc_emails = [e.strip() for e in bcc_raw.split(",") if e.strip()] if bcc_raw else []

    if not resend_api_key:
        raise RuntimeError("RESEND_API_KEY environment variable not set")

    resend.api_key = resend_api_key

    # Prepare attachments (PDF + chart PNGs + clove favicon for bullets)
    attachments: List[Dict[str, Any]] = []
    
    # Attach PDF if available
    if pdf_path and pdf_path.exists():
        with open(pdf_path, "rb") as f:
            pdf_content = base64.b64encode(f.read()).decode("utf-8")
        attachments.append({
            "filename": pdf_path.name,
            "content": pdf_content,
        })

    # Attach charts as inline images with Content-ID for embedding in email body
    # This allows Gmail to display them inline instead of as attachments
    # Using Content-ID (CID) references which Gmail supports for inline images
    if chart_cids:
        for path in chart_paths:
            if path.exists() and path in chart_cids:
                with open(path, "rb") as f:
                    img_content = base64.b64encode(f.read()).decode("utf-8")
                cid = chart_cids[path]
                attachments.append({
                    "filename": path.name,
                    "content": img_content,
                    "content_id": cid,  # Content-ID for inline embedding (Gmail compatible)
                })
    else:
        # Fallback: attach as regular attachments if no CIDs provided
        for path in chart_paths:
            if path.exists():
                with open(path, "rb") as f:
                    img_content = base64.b64encode(f.read()).decode("utf-8")
                attachments.append({
                    "filename": path.name,
                    "content": img_content,
                })

    # Attach the Clove favicon used as the bullet icon in the insights list
    try:
        clove_icon_path = REPO_ROOT / "For Web" / "Favicons" / "browser.png"
        if clove_icon_path.exists():
            with open(clove_icon_path, "rb") as f:
                icon_content = base64.b64encode(f.read()).decode("utf-8")
            attachments.append({
                "filename": clove_icon_path.name,
                "content": icon_content,
                "content_id": "clove_bullet_icon",
            })
    except Exception:
        # If favicon can't be attached, just skip it – bullets will render without the icon.
        pass

    try:
        log_target = ", ".join(recipient_emails)
        if cc_email:
            log_target += f" (cc: {cc_email})"
        if bcc_emails:
            log_target += f" (bcc: {', '.join(bcc_emails)})"
        logging.info(f"Sending email via Resend to {log_target}...")

        # Calculate business year-to-date percentage change for email subject
        if ledger is not None:
            total_pct_change = calculate_business_year_to_date_pct_change(ledger, ctx)
            subject = f"Mumma Report {total_pct_change:+.0f}% YoY"
        else:
            subject = f"MUMMA Weekly Insights Report {ctx.label}"

        params: Dict[str, Any] = {
            "from": from_email,
            "to": recipient_emails,
            "subject": subject,
            "html": html_body,
        }

        if cc_email:
            params["cc"] = [cc_email]

        if bcc_emails:
            params["bcc"] = bcc_emails

        if attachments:
            params["attachments"] = attachments

        response = Emails.send(params)

        if response and hasattr(response, "id"):
            logging.info(f"Clove Email sent successfully via Resend! ID: {response.id}")
        else:
            logging.warning(f"Resend response: {response}")

        # Log file
        cc_display = "" if not cc_email else f" (cc: {cc_email})"
        bcc_display = "" if not bcc_emails else f" (bcc: {', '.join(bcc_emails)})"
        log_path = REPORTS_DIR / f"email_sent_{ctx.label.replace('-', '')}.log"
        log_path.write_text(
            f"Sent to {', '.join(recipient_emails)}"
            f"{cc_display}"
            f"{bcc_display} "
            f"at {datetime.utcnow().isoformat()}Z via Resend\n"
        )
        logging.info(f"Email sent to {log_target} – log at {log_path}")

    except Exception as e:
        error_msg = f"Error sending email via Resend: {e}"
        logging.error(error_msg)
        import traceback
        logging.error(traceback.format_exc())
        cc_display = "" if not cc_email else f" (cc: {cc_email})"
        bcc_display = "" if not bcc_emails else f" (bcc: {', '.join(bcc_emails)})"
        log_path = REPORTS_DIR / f"email_error_{ctx.label.replace('-', '')}.log"
        log_path.write_text(
            f"Failed to send to {', '.join(recipient_emails)}"
            f"{cc_display}"
            f"{bcc_display} "
            f"at {datetime.utcnow().isoformat()}Z\nError: {e}\n{traceback.format_exc()}\n"
        )
        raise


def compare_daily_weekly_formats() -> None:
    """Compare the format of daily_sales_summary.xlsx with weekly transaction data."""
    daily_path = DAILY_SALES_XLSX
    ledger_path = LEDGER_PATH
    
    if not daily_path.exists():
        logging.warning(f"Daily sales summary not found: {daily_path}")
        return
    
    if not ledger_path.exists():
        logging.warning(f"Revenue ledger not found: {ledger_path}")
        return
    
    daily_df = pd.read_excel(daily_path)
    ledger_df = pd.read_csv(ledger_path, parse_dates=["transaction_datetime"])
    
    print("\n" + "="*60)
    print("FORMAT COMPARISON: Daily Sales Summary vs Weekly Transactions")
    print("="*60)
    
    print("\n📊 DAILY SALES SUMMARY (daily_sales_summary.xlsx):")
    print(f"   Shape: {daily_df.shape[0]} rows × {daily_df.shape[1]} columns")
    print(f"   Columns: {list(daily_df.columns)}")
    print(f"   Date range: {daily_df['Date'].min()} to {daily_df['Date'].max()}")
    if 'Location' in daily_df.columns:
        print(f"   Locations: {daily_df['Location'].unique().tolist()}")
    print("\n   First few rows:")
    print(daily_df.head().to_string())
    
    print("\n📋 WEEKLY TRANSACTIONS (revenue_ledger.csv):")
    print(f"   Shape: {len(ledger_df)} rows × {len(ledger_df.columns)} columns")
    print(f"   Columns: {list(ledger_df.columns)}")
    if 'transaction_datetime' in ledger_df.columns:
        print(f"   Date range: {ledger_df['transaction_datetime'].min()} to {ledger_df['transaction_datetime'].max()}")
    if 'location' in ledger_df.columns:
        print(f"   Locations: {ledger_df['location'].unique().tolist()}")
    print("\n   First few rows:")
    print(ledger_df.head().to_string())
    
    # Check if daily summary can be derived from ledger
    print("\n🔍 COMPATIBILITY CHECK:")
    if 'Date' in daily_df.columns and 'transaction_datetime' in ledger_df.columns:
        ledger_df['date'] = pd.to_datetime(ledger_df['transaction_datetime']).dt.date
        daily_df['date'] = pd.to_datetime(daily_df['Date']).dt.date
        
        # Check date overlap
        ledger_dates = set(ledger_df['date'].unique())
        daily_dates = set(daily_df['date'].unique())
        overlap = ledger_dates & daily_dates
        print(f"   Date overlap: {len(overlap)} common dates")
        print(f"   Ledger-only dates: {len(ledger_dates - daily_dates)}")
        print(f"   Daily-only dates: {len(daily_dates - ledger_dates)}")
    
    print("\n" + "="*60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate & email the MUMMA Weekly Insights Report.")
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="Reference date (YYYY-MM-DD) within the target week. Defaults to latest ledger date.",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Generate report and charts but do not send email (for testing).",
    )
    parser.add_argument(
        "--compare-formats",
        action="store_true",
        help="Compare daily sales summary format with weekly transaction format and exit.",
    )
    args = parser.parse_args()

    # If just comparing formats, do that and exit
    if args.compare_formats:
        compare_daily_weekly_formats()
        return

    ledger = load_ledger()
    daily = load_daily_summary()
    product_detailed = load_product_insights_detailed()

    ctx = determine_week_context(ledger, args.week)
    logging.info(
        f"Building weekly report for week {ctx.week_start} – {ctx.report_date} "
        f"(prev week from {ctx.prev_week_start})"
    )

    weekly_kpis = summarize_week(ledger, ctx)
    
    # Generate insights for all sections
    yearly_insights = generate_yearly_insights(ledger, ctx)
    weekly_summary_insights = generate_weekly_summary_insights(daily, ctx, weekly_kpis)
    monthly_progress_insights = generate_monthly_progress_insights(daily, ctx)
    product_insights = generate_product_insights(ledger, ctx)
    price_increase_actions = calculate_price_increase_scenarios(ledger, ctx)

    # Charts
    charts_dir = REPORTS_DIR / f"charts_{ctx.label.replace('-', '')}"
    charts_dir.mkdir(parents=True, exist_ok=True)

    chart_paths: List[Path] = []
    # Monthly comparison chart (current month vs same month last year)
    monthly_chart = make_monthly_sales_chart(daily, ctx, charts_dir)
    if monthly_chart:
        chart_paths.append(monthly_chart)
    # Weekly comparison chart (current week vs same week last year)
    weekly_chart = make_weekly_sales_chart(daily, ctx, charts_dir)
    if weekly_chart:
        chart_paths.append(weekly_chart)
    # Top products by revenue (this week only)
    top_chart = make_top_products_chart(ledger, ctx, charts_dir)
    if top_chart:
        chart_paths.append(top_chart)
    # Top products by items sold (this week only)
    top_items_chart = make_top_products_by_items_chart(ledger, ctx, charts_dir)
    if top_items_chart:
        chart_paths.append(top_items_chart)
    # Category breakdown (this week only)
    cat_chart = make_category_chart(ledger, ctx, charts_dir)
    if cat_chart:
        chart_paths.append(cat_chart)

    html, chart_cids = build_html_report(
        ctx,
        yearly_insights,
        weekly_summary_insights,
        monthly_progress_insights,
        product_insights,
        price_increase_actions,
        weekly_kpis,
        chart_paths,
    )

    # PDF
    pdf_path = REPORTS_DIR / f"mumma_weekly_summary_{ctx.label.replace('-', '')}.pdf"
    render_pdf(html, pdf_path)

    html_path = REPORTS_DIR / f"mumma_weekly_summary_{ctx.label.replace('-', '')}.html"

    # Email (unless --no-email flag is set)
    if args.no_email:
        preview_html = html_for_browser_preview(html, chart_paths, chart_cids, REPORTS_DIR)
        html_path.write_text(preview_html, encoding="utf-8")
        logging.info("⏸️  --no-email flag set: Skipping email send. Report generated successfully.")
        logging.info(f"   HTML preview: {html_path}")
        logging.info(f"   Charts saved to: {charts_dir}")
        if pdf_path.exists():
            logging.info(f"   PDF saved to: {pdf_path}")
    else:
        send_email_with_report(ctx, html, chart_paths, pdf_path if pdf_path.exists() else None, chart_cids, ledger)


if __name__ == "__main__":
    main()



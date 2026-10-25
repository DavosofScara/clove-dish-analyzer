"""
Cumulative CA chart for the fiscal year (annual report only).

Reuses daily / smoothing helpers from ``cumulative_season_yoy`` without changing
the weekly season chart.

N-1: V14 extract when present; otherwise HIVER from dossier_travail_master +
ÉTÉ 25 definitive (same composition as annual KPI YoY), aligned on Date opération.
"""
from __future__ import annotations

import base64
import io
import logging
from datetime import date

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .config import CLOVE_GREEN, THEME_BORDER, THEME_DARK, THEME_MUTED, THEME_TEXT
from .cumulative_season_yoy import (
    FULL_SEASON_LINE_ALPHA,
    FULL_SEASON_LINE_COLOR,
    _align_prior_dates_to_current_season_window,
    _gradient_fill_under,
    _resolve_chart_columns,
    _smooth_monotonic_curve,
    compute_daily_confirmed_pdv,
    cumulative_series_by_calendar_date,
)
from .historical_master import compute_prior_fiscal_year_daily_confirmed
from .periods import SeasonPeriod, fiscal_year_containing, previous_fiscal_year_before

logger = logging.getLogger(__name__)


def _prior_fiscal_daily(df, cols: dict, prior: SeasonPeriod):
    """Extract daily N-1, falling back to historique when V14 has no prior ops."""
    daily_prior = compute_daily_confirmed_pdv(df, cols, prior.start, prior.end)
    extract_ca = float(daily_prior.sum()) if len(daily_prior) else 0.0
    if extract_ca >= 1.0:
        logger.info("N-1 cumulative from extract: CA=%.0f", extract_ca)
        return daily_prior, "extract"
    hist = compute_prior_fiscal_year_daily_confirmed(prior)
    hist_ca = float(hist.sum()) if len(hist) else 0.0
    logger.info(
        "N-1 cumulative from historique (extract CA=%.0f): CA=%.0f",
        extract_ca,
        hist_ca,
    )
    return hist, "historique"


def _make_cumulative_fiscal_yoy_figure(df, as_of: date) -> Figure:
    cols = _resolve_chart_columns(df)
    current: SeasonPeriod = fiscal_year_containing(as_of)
    prior: SeasonPeriod = previous_fiscal_year_before(current)

    daily_current = compute_daily_confirmed_pdv(df, cols, current.start, current.end)
    daily_prior, prior_source = _prior_fiscal_daily(df, cols, prior)

    cap = min(as_of, current.end)
    d_cur, y_cur_raw = cumulative_series_by_calendar_date(
        daily_current, current.start, current.end, cap
    )
    d_cur_full, y_cur_full_raw = cumulative_series_by_calendar_date(
        daily_current, current.start, current.end, current.end
    )
    d_pri, y_pri_raw = cumulative_series_by_calendar_date(
        daily_prior, prior.start, prior.end, prior.end
    )
    d_pri_on_current_axis = _align_prior_dates_to_current_season_window(
        d_pri,
        current_start=current.start,
        prior_start=prior.start,
    )

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor(THEME_DARK)
    ax.set_facecolor("#2a2d35")
    ax.set_axisbelow(True)

    prior_line_color = "#9ea3b5"
    prior_fill_top = "#7a8499"

    if len(d_pri_on_current_axis) and len(y_pri_raw):
        x_pri_s, y_pri_s = _smooth_monotonic_curve(d_pri_on_current_axis, y_pri_raw)
        _gradient_fill_under(ax, x_pri_s, y_pri_s, prior_fill_top, max_alpha=0.42, zorder=1)
        ax.plot(
            x_pri_s,
            y_pri_s,
            color=prior_line_color,
            linewidth=1.35,
            solid_capstyle="round",
            label=f"N-1 ({prior.label}) — année entière",
            zorder=3,
        )
    if len(d_cur_full) and len(y_cur_full_raw) and cap < current.end:
        x_full_s, y_full_s = _smooth_monotonic_curve(d_cur_full, y_cur_full_raw)
        ax.plot(
            x_full_s,
            y_full_s,
            color=FULL_SEASON_LINE_COLOR,
            alpha=FULL_SEASON_LINE_ALPHA,
            linewidth=1.2,
            linestyle="-",
            solid_capstyle="round",
            label=f"Confirmé année entière ({current.label})",
            zorder=3,
        )
    if len(d_cur) and len(y_cur_raw):
        x_cur_s, y_cur_s = _smooth_monotonic_curve(d_cur, y_cur_raw)
        _gradient_fill_under(ax, x_cur_s, y_cur_s, CLOVE_GREEN, max_alpha=0.45, zorder=2)
        ax.plot(
            x_cur_s,
            y_cur_s,
            color=CLOVE_GREEN,
            linewidth=2.6,
            solid_capstyle="round",
            label=f"Réalisé à date du rapport ({current.label})",
            zorder=4,
        )

    if not (y_pri_raw or y_cur_raw or y_cur_full_raw):
        ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", color=THEME_TEXT, fontsize=12)

    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y"))
    ax.set_xlim(mdates.date2num(current.start), mdates.date2num(current.end))

    ax.set_xlabel(
        f"Date — année fiscale ({current.start.strftime('%d/%m/%Y')} – {current.end.strftime('%d/%m/%Y')})",
        color=THEME_TEXT,
        fontsize=10,
    )
    ax.set_ylabel("CA confirmé cumulé HT (€)", color=THEME_TEXT, fontsize=10)
    ax.set_title(
        f"CA cumulé confirmé — {current.label} vs {prior.label}\n"
        f"(Date opération · ligne épaisse arrêtée au {cap.strftime('%d/%m/%Y')})",
        color=THEME_TEXT,
        fontsize=11,
        pad=12,
    )
    ax.tick_params(colors=THEME_TEXT)
    for spine in ax.spines.values():
        spine.set_color(THEME_BORDER)
    ax.grid(True, alpha=0.2, color=THEME_MUTED)

    def _fmt_euro(x, _pos):
        if x >= 1_000_000:
            return f"{x/1_000_000:.1f}M"
        if x >= 1000:
            return f"{x/1000:.0f}k"
        return f"{x:.0f}"

    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_euro))
    leg = ax.legend(loc="lower right", facecolor=THEME_DARK, edgecolor=THEME_BORDER, labelcolor=THEME_TEXT)
    for text in leg.get_texts():
        text.set_color(THEME_TEXT)

    n1_note = (
        "N-1 = extract"
        if prior_source == "extract"
        else "N-1 = historique (HIVER travail + ÉTÉ 25 définitif)"
    )
    fig.text(
        0.5,
        0.02,
        "Ligne épaisse = réalisé à la date du rapport · "
        f"{n1_note} · alignée sur le calendrier relatif 01/10–30/09",
        ha="center",
        fontsize=8,
        color=THEME_MUTED,
        transform=fig.transFigure,
    )
    fig.subplots_adjust(bottom=0.14, top=0.88)
    fig.autofmt_xdate()
    return fig


def render_cumulative_fiscal_yoy_data_uri(df, as_of: date) -> str:
    fig = _make_cumulative_fiscal_yoy_figure(df, as_of)
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=144, bbox_inches="tight")
    finally:
        plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"

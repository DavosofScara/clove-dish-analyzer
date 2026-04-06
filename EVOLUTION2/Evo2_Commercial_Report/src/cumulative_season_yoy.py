"""
Standalone cumulative CA (HT) chart: current season vs previous season of the same type.

Phase 1: not wired into the weekly email. Run:

    python -m src.cumulative_season_yoy --as-of YYYY-MM-DD

Output: ``outputs/cumulative_season_yoy.png`` (and optional HTML wrapper).
"""
from __future__ import annotations

import argparse
import base64
import io
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

import matplotlib.colors as mcolors
from matplotlib.figure import Figure
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from scipy.interpolate import PchipInterpolator

from .config import CLOVE_GREEN, OUTPUTS_DIR, THEME_BORDER, THEME_DARK, THEME_MUTED, THEME_TEXT
from .load_data import coerce_number, get_ci_column, load_excel_data
from .periods import date_in_range, previous_season_before, season_containing
from .status_norm import is_confirmed_exact

logger = logging.getLogger(__name__)


def _pdv_confirme(val) -> float:
    v = coerce_number(val)
    return float(v) if v is not None else 0.0


def _resolve_chart_columns(df: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    for logical in ("Date_opération", "CONFIRME", "PDV_DEVIS_CONFIRME"):
        c = get_ci_column(df, logical)
        if not c:
            raise ValueError(f"Required column missing for cumulative chart: {logical}")
        out[logical] = c
    return out


def compute_daily_confirmed_pdv(
    df: pd.DataFrame,
    cols: dict[str, str],
    season_start: date,
    season_end: date,
) -> pd.Series:
    """
    Sum PDV_DEVIS_CONFIRME by calendar day for CONFIRMÉ rows with Date_opération in [start, end].
    Index: datetime.date; values: float daily total.
    """
    date_col = cols["Date_opération"]
    conf_col = cols["CONFIRME"]
    pdv_col = cols["PDV_DEVIS_CONFIRME"]

    m = df[date_col].apply(lambda d: date_in_range(d, season_start, season_end)) & df[conf_col].map(
        is_confirmed_exact
    )
    sub = df.loc[m, [date_col, pdv_col]].copy()
    if sub.empty:
        return pd.Series(dtype=float)

    def _to_date(x) -> date | None:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        if hasattr(x, "date") and callable(getattr(x, "date")):
            return x.date()
        if isinstance(x, date):
            return x
        return None

    sub["_day"] = sub[date_col].map(_to_date)
    sub = sub.dropna(subset=["_day"])
    sub["_pdv"] = sub[pdv_col].map(_pdv_confirme)
    daily = sub.groupby("_day", sort=True)["_pdv"].sum()
    return daily


def cumulative_series_by_calendar_date(
    daily: pd.Series,
    season_start: date,
    season_end: date,
    cap_end: date,
) -> Tuple[List[date], List[float]]:
    """
    Build (calendar dates, cumulative €) for each day from season_start through min(cap_end, season_end).
    """
    end = min(cap_end, season_end)
    if end < season_start:
        return [], []

    dates: list[date] = []
    ys: list[float] = []
    running = 0.0
    d = season_start
    while d <= end:
        running += float(daily.get(d, 0.0))
        dates.append(d)
        ys.append(running)
        d += timedelta(days=1)
    return dates, ys


def _align_prior_dates_to_current_season_window(
    prior_dates: List[date],
    *,
    current_start: date,
    prior_start: date,
) -> List[date]:
    """
    Map each real calendar day of the prior season to the **same relative day**
    within the current season (day 0 = opening day of each season).

    YoY curves then share one x-axis: the current season calendar only
    (e.g. HIVER 25/26 → 15/11/2025 … 30/04/2026), instead of stretching from 2024 to 2026.
    """
    return [current_start + (d - prior_start) for d in prior_dates]


def _dates_to_mpl(dates: List[date]) -> np.ndarray:
    return np.array([mdates.date2num(d) for d in dates], dtype=float)


def _smooth_monotonic_curve(
    dates: List[date],
    y: List[float],
    *,
    n_points: int = 480,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Dense (x_mpl, y) for plotting: monotonic cubic between knots (preserves cumulative shape, smooth look).
    """
    if len(dates) < 2:
        if not dates:
            return np.array([]), np.array([])
        x0 = _dates_to_mpl(dates)
        return x0, np.array(y, dtype=float)

    xn = _dates_to_mpl(dates)
    yn = np.array(y, dtype=float)
    pchip = PchipInterpolator(xn, yn)
    n = max(n_points, len(dates) * 4)
    xf = np.linspace(float(xn[0]), float(xn[-1]), n)
    yf = np.clip(pchip(xf), 0.0, None)
    return xf, yf


def _gradient_fill_under(
    ax,
    x: np.ndarray,
    y: np.ndarray,
    color_hex: str,
    *,
    n_layers: int = 56,
    max_alpha: float = 0.38,
    zorder: float = 1,
) -> None:
    """Vertical gradient: strongest under the line, fading to transparent toward the x-axis."""
    if x.size < 2 or y.size < 2:
        return
    rgb = mcolors.to_rgb(color_hex)
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    for i in range(n_layers):
        t0 = i / n_layers
        t1 = (i + 1) / n_layers
        y_lo = y * t0
        y_hi = y * t1
        # t_mid 0 at axis → transparent; → 1 at line → max_alpha
        t_mid = 0.5 * (t0 + t1)
        a = max_alpha * (t_mid**0.92)
        ax.fill_between(x, y_lo, y_hi, facecolor=(*rgb, a), edgecolor="none", linewidth=0, zorder=zorder)


def _make_cumulative_season_yoy_figure(df: pd.DataFrame, as_of: date) -> Figure:
    """
    Build the figure (caller must plt.close(fig) after savefig).
    """
    cols = _resolve_chart_columns(df)
    current = season_containing(as_of)
    prior = previous_season_before(current)

    daily_current = compute_daily_confirmed_pdv(df, cols, current.start, current.end)
    daily_prior = compute_daily_confirmed_pdv(df, cols, prior.start, prior.end)

    cap = min(as_of, current.end)
    d_cur, y_cur_raw = cumulative_series_by_calendar_date(daily_current, current.start, current.end, cap)
    d_pri, y_pri_raw = cumulative_series_by_calendar_date(daily_prior, prior.start, prior.end, prior.end)
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
            label=f"Saison précédente ({prior.label})",
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
            label=f"Saison en cours ({current.label})",
            zorder=4,
        )

    if not (y_pri_raw or y_cur_raw):
        ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", color=THEME_TEXT, fontsize=12)

    ax.xaxis_date()
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y"))
    ax.set_xlim(mdates.date2num(current.start), mdates.date2num(current.end))

    ax.set_xlabel(
        f"Date — saison en cours ({current.start.strftime('%d/%m/%Y')} – {current.end.strftime('%d/%m/%Y')})",
        color=THEME_TEXT,
        fontsize=10,
    )
    ax.set_ylabel("CA réalisé cumulé HT (€)", color=THEME_TEXT, fontsize=10)
    ax.set_title(
        f"CA cumulé confirmé — {current.label} vs {prior.label}\n"
        f"(Date opération · arrêt saison en cours : {cap.strftime('%d/%m/%Y')})",
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

    fig.text(
        0.5,
        0.02,
        "CA = somme PDV devis confirmés (HT), CONFIRMÉ · N-1 alignée sur le même calendrier (même jour relatif dans la saison)",
        ha="center",
        fontsize=8,
        color=THEME_MUTED,
        transform=fig.transFigure,
    )
    fig.subplots_adjust(bottom=0.14, top=0.88)
    fig.autofmt_xdate()
    return fig


def render_cumulative_season_yoy_data_uri(df: pd.DataFrame, as_of: date) -> str:
    """PNG as ``data:image/png;base64,...`` for inline email HTML (same figure as standalone PNG)."""
    fig = _make_cumulative_season_yoy_figure(df, as_of)
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=144, bbox_inches="tight")
    finally:
        plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def render_cumulative_season_yoy_png(
    df: pd.DataFrame,
    as_of: date,
    *,
    out_path: Path | None = None,
) -> Path:
    """Write PNG to disk (standalone CLI)."""
    fig = _make_cumulative_season_yoy_figure(df, as_of)
    out = out_path or (OUTPUTS_DIR / "cumulative_season_yoy.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(out, format="png", dpi=144, bbox_inches="tight")
    finally:
        plt.close(fig)
    logger.info("Wrote cumulative season YoY chart to %s", out)
    return out


def write_preview_html(png_path: Path, html_path: Path | None = None) -> Path:
    """Minimal HTML wrapper to open the PNG in a browser."""
    html_path = html_path or (png_path.parent / "cumulative_season_yoy_preview.html")
    rel = png_path.name
    html_path.write_text(
        f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"/><title>CA cumulé saison (YoY)</title></head>
<body style="margin:0;background:#222831;">
  <img src="{rel}" alt="CA cumulé saison" style="max-width:100%;height:auto;display:block;margin:0 auto;"/>
</body>
</html>
""",
        encoding="utf-8",
    )
    logger.info("Wrote HTML preview to %s", html_path)
    return html_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Standalone cumulative realised revenue (HT) chart: current vs previous same-type season."
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Reference date YYYY-MM-DD (default: today). Truncates current season curve.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output PNG path (default: outputs/cumulative_season_yoy.png)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Also write cumulative_season_yoy_preview.html next to the PNG.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    out_png = Path(args.output).expanduser() if args.output else OUTPUTS_DIR / "cumulative_season_yoy.png"

    df = load_excel_data()
    render_cumulative_season_yoy_png(df, as_of, out_path=out_png)
    if args.html:
        write_preview_html(out_png)


if __name__ == "__main__":
    main()

from __future__ import annotations

import base64
import io
import logging
from datetime import date
from typing import Optional

import matplotlib.colors as mcolors
import matplotlib.patheffects as mpath_effects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from .config import (
    CLOVE_GREEN,
    CLOVE_GREEN_MUTED,
    THEME_BORDER,
    THEME_DARK,
    THEME_MUTED,
    THEME_TEXT,
)
from .load_data import coerce_number, get_ci_column
from .periods import date_in_range
from .status_norm import is_confirmed_exact

logger = logging.getLogger(__name__)


def _resolve_site_column(df: pd.DataFrame) -> Optional[str]:
    """Actual dataframe column for operational SITE (header match, case-insensitive)."""
    c = get_ci_column(df, "SITE")
    if c:
        return c
    for col in df.columns:
        key = str(col).strip().replace("\u00a0", " ").upper()
        if key == "SITE":
            return col
    return None


def _series_to_site_labels(series: pd.Series) -> pd.Series:
    """
    Build display labels from the SITE column only. Handles numeric Excel codes
    (int/float) so we do not collapse everything to a misleading '0' string.
    """
    out: list[str] = []
    for v in series:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            out.append("")
            continue
        if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
            out.append(str(int(v)))
            continue
        if isinstance(v, (float, np.floating)) and not isinstance(v, bool):
            if np.isnan(v):
                out.append("")
            elif float(v).is_integer():
                out.append(str(int(v)))
            else:
                out.append(str(v).strip())
            continue
        s = str(v).strip()
        out.append(s)
    return pd.Series(out, index=series.index, dtype="string")


def add_site_label_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bar chart dimension: **SITE column only** (not SITE_EVOLUTION, not CDP).
    Matches the operational site field in extract_devis.
    """
    out = df.copy()
    site_col = _resolve_site_column(out)
    if not site_col:
        logger.error(
            "SITE column not found in workbook; site bar chart will be empty. "
            "First columns: %s",
            list(out.columns)[:25],
        )
        out["_REPORT_SITE_LABEL"] = pd.Series("", index=out.index, dtype="string")
        return out

    labels = _series_to_site_labels(out[site_col])
    out["_REPORT_SITE_LABEL"] = labels.fillna("")
    n_nonempty = int((out["_REPORT_SITE_LABEL"].astype(str).str.strip() != "").sum())
    logger.info(
        "Site chart: using column %r; %d/%d rows have a non-empty SITE label.",
        site_col,
        n_nonempty,
        len(out),
    )
    return out


def _row_pdv_confirme(val) -> float:
    v = coerce_number(val)
    return float(v) if v is not None else 0.0


def compute_site_confirmed_pdv_by_season(
    df: pd.DataFrame,
    season_start: date,
    season_end: date,
    max_sites: int = 40,
) -> pd.Series:
    """
    Sum PDV_DEVIS_CONFIRME for confirmed rows with Date_opération in [season_start, season_end],
    grouped by site label. Descending sort; truncated to max_sites.
    """
    if "_REPORT_SITE_LABEL" in df.columns:
        work = df.copy()
    else:
        work = add_site_label_column(df)
    date_col = get_ci_column(work, "Date_opération")
    conf_col = get_ci_column(work, "CONFIRME")
    pdv_col = get_ci_column(work, "PDV_DEVIS_CONFIRME")
    if not (date_col and conf_col and pdv_col):
        logger.warning("Missing Date_opération, CONFIRME, or PDV_DEVIS_CONFIRME; site bar chart empty.")
        return pd.Series(dtype=float)

    m = work[date_col].apply(lambda d: date_in_range(d, season_start, season_end)) & work[
        conf_col
    ].map(is_confirmed_exact)
    sub = work.loc[m]
    if sub.empty:
        return pd.Series(dtype=float)

    sub = sub.copy()
    sub["_pdvc"] = sub[pdv_col].map(_row_pdv_confirme)
    totals = sub.groupby("_REPORT_SITE_LABEL", dropna=False)["_pdvc"].sum()
    totals.index = totals.index.astype(str).str.strip()
    totals = totals[totals.index != ""]
    totals = totals.sort_values(ascending=False)
    n_distinct = len(totals)
    if len(totals) > max_sites:
        totals = totals.iloc[:max_sites]
    logger.info(
        "Site chart aggregates: %d distinct SITE values in season window (chart shows %d bars).",
        n_distinct,
        len(totals),
    )
    return totals


ACCENT_PALETTES = {
    "blue": ("#20d9ff", "#1a3550"),
    "orange": ("#ff9a26", "#4a1e06"),
}


def render_site_pdv_season_bars(site_totals: pd.Series, *, accent: str = "blue") -> str:
    """
    Horizontal bars: site on Y, PDV confirmé on X. Highest value at top.
    ``accent`` is ``blue`` (electric blue → dark blue) or ``orange`` (electric orange → dark brown).
    """
    if site_totals.empty:
        logger.warning("Site PDV series empty, bar chart will be blank.")
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor(THEME_DARK)
        ax.set_facecolor(THEME_DARK)
        ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", color=THEME_TEXT, fontsize=12)
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    # barh: first row at bottom — sort ascending so largest ends up at top
    s = site_totals.sort_values(ascending=True)
    m = len(s)
    fig_h = max(4.0, 0.38 * m + 1.2)
    fig, ax = plt.subplots(figsize=(9, fig_h))
    fig.patch.set_facecolor(THEME_DARK)
    ax.set_facecolor(THEME_DARK)

    top_hex, bottom_hex = ACCENT_PALETTES.get(accent, ACCENT_PALETTES["blue"])
    top_rgb = np.array(mcolors.to_rgb(top_hex))
    bottom_rgb = np.array(mcolors.to_rgb(bottom_hex))
    if m == 1:
        colors = [top_rgb]
    else:
        colors = [bottom_rgb + (top_rgb - bottom_rgb) * (i / (m - 1)) for i in range(m)]

    y_pos = np.arange(m)
    ax.barh(y_pos, s.values, color=colors, height=0.68, edgecolor="none")

    ax.set_yticks(y_pos)
    ax.set_yticklabels([str(x) for x in s.index], color=THEME_TEXT, fontsize=9)
    ax.set_xlabel("PDV confirmé (€)", color=THEME_TEXT, fontsize=10)
    ax.tick_params(axis="x", colors=THEME_TEXT)
    ax.tick_params(axis="y", colors=THEME_TEXT)

    def _fmt_euro(x, _pos):
        if x >= 1_000_000:
            return f"{x/1_000_000:.1f}M"
        if x >= 1000:
            return f"{x/1000:.0f}k"
        return f"{x:.0f}"

    ax.xaxis.set_major_formatter(FuncFormatter(_fmt_euro))
    for spine in ax.spines.values():
        spine.set_color(THEME_BORDER)
    ax.grid(axis="x", alpha=0.2, color=THEME_TEXT)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def render_cdp_scatter(cdp_df: pd.DataFrame, *, green_alpha: float = 0.9) -> str:
    """
    CDP chart on dark background (same family as site bars): X = confirmation rate (%),
    Y = median PDV per client (€). **Bubble area ∝ total PDV confirmé** for that CDP
    (sum of PDV_DEVIS on confirmed rows — column ``PDV_confirme`` in ``cdp_df``).

    CDP codes are drawn above each bubble (offset in points) using the same sans-serif
    stack as the email body / Conversion par CDP table.
    """
    if cdp_df.empty:
        logger.warning("CDP dataframe is empty, chart will be blank.")
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor(THEME_DARK)
        ax.set_facecolor(THEME_DARK)
        ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", color=THEME_TEXT, fontsize=12)
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    x = (cdp_df["Taux_confirmation"].fillna(0.0) * 100).to_numpy()
    y = cdp_df["PDV_median_client"].fillna(0.0).to_numpy()
    size_raw = cdp_df["PDV_confirme"].fillna(0.0).to_numpy()
    max_sz = float(size_raw.max()) if size_raw.size and size_raw.max() > 0 else 1.0
    # scatter ``s`` is area in points^2
    areas = 140 + (size_raw / max_sz) * 920

    fig_w, fig_h = 9.0, 5.8
    # Match email / table: -apple-system, Segoe UI, Roboto, Helvetica, Arial (first available)
    font_ctx = {
        "font.family": "sans-serif",
        "font.sans-serif": [
            "Helvetica Neue",
            "Helvetica",
            "Arial",
            "Segoe UI",
            "Roboto",
            "DejaVu Sans",
        ],
    }

    with plt.rc_context(font_ctx):
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        fig.patch.set_facecolor(THEME_DARK)
        ax.set_facecolor(THEME_DARK)
        ax.grid(True, alpha=0.18, color=THEME_MUTED, linestyle="-")

        labels = cdp_df["CDP"].astype(str)

        for xi, yi, a, lab in zip(x, y, areas, labels):
            ax.scatter(
                [xi],
                [yi],
                s=a,
                c=[CLOVE_GREEN],
                alpha=green_alpha,
                edgecolors="#a8f578",
                linewidths=1.2,
                zorder=2,
            )
            # Label above bubble (screen space); extra lift scales slightly with bubble size
            offset_pt = 12.0 + min(np.sqrt(float(a)) * 0.32, 22.0)
            ann = ax.annotate(
                lab,
                xy=(xi, yi),
                xytext=(0, offset_pt),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=12,
                fontweight="medium",
                color=THEME_TEXT,
                zorder=4,
                annotation_clip=False,
            )
            ann.set_path_effects([mpath_effects.withStroke(linewidth=2.2, foreground="#0b0e12")])

        ax.set_xlabel("Taux de confirmation (%)", color=THEME_TEXT, fontsize=10)
        ax.set_ylabel("PDV médian par client (€)", color=THEME_TEXT, fontsize=10)
        ax.tick_params(colors=THEME_TEXT)
        for spine in ax.spines.values():
            spine.set_color(THEME_BORDER)

        fig.subplots_adjust(bottom=0.14)
        fig.text(
            0.5,
            0.02,
            "Surface de chaque bulle proportionnelle au PDV confirmé total du CDP (somme PDV devis confirmés)",
            ha="center",
            fontsize=8,
            color=THEME_MUTED,
            transform=fig.transFigure,
        )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
        plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _chart_font_context() -> dict:
    return {
        "font.family": "sans-serif",
        "font.sans-serif": [
            "Helvetica Neue",
            "Helvetica",
            "Arial",
            "Segoe UI",
            "Roboto",
            "DejaVu Sans",
        ],
    }


def _empty_chart_data_uri(*, figsize: tuple[float, float] = (9.0, 5.8)) -> str:
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(THEME_DARK)
    ax.set_facecolor(THEME_DARK)
    ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", color=THEME_TEXT, fontsize=12)
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def render_cdp_margin_bars(
    margin_df: pd.DataFrame,
    *,
    green_alpha: float = 1.0,
    budget_alpha: float = 1.0,
) -> str:
    """
    Grouped bars per CDP: simple average margin % of PDV_DEVIS (budget vs réelle).
    Same footprint and dark theme as ``render_cdp_scatter``.
    """
    fig_w, fig_h = 9.0, 5.8
    if margin_df.empty:
        logger.warning("CDP margin dataframe is empty, bar chart will be blank.")
        return _empty_chart_data_uri(figsize=(fig_w, fig_h))

    labels = margin_df["CDP"].astype(str).tolist()
    budget = margin_df["Marge_budget_pct_moyenne"].fillna(0.0).to_numpy()
    reelle = margin_df["Marge_reelle_pct_moyenne"].fillna(0.0).to_numpy()
    n = len(labels)
    x = np.arange(n, dtype=float)
    width = 0.36

    with plt.rc_context(_chart_font_context()):
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        fig.patch.set_facecolor(THEME_DARK)
        ax.set_facecolor(THEME_DARK)
        ax.grid(True, axis="y", alpha=0.18, color=THEME_MUTED, linestyle="-")

        ax.bar(
            x - width / 2,
            budget,
            width,
            label="Marge budget (moy. %)",
            color=CLOVE_GREEN_MUTED,
            alpha=budget_alpha,
            edgecolor=THEME_BORDER,
            linewidth=0.6,
            zorder=2,
        )
        ax.bar(
            x + width / 2,
            reelle,
            width,
            label="Marge réelle (moy. %)",
            color=CLOVE_GREEN,
            alpha=green_alpha,
            edgecolor="#a8f578",
            linewidth=0.6,
            zorder=3,
        )

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", color=THEME_TEXT)
        ax.set_ylabel("Marge / PDV (%)", color=THEME_TEXT, fontsize=10)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
        ax.tick_params(colors=THEME_TEXT)
        for spine in ax.spines.values():
            spine.set_color(THEME_BORDER)

        leg = ax.legend(
            loc="upper right",
            facecolor=THEME_DARK,
            edgecolor=THEME_BORDER,
            labelcolor=THEME_TEXT,
            fontsize=9,
        )
        for text in leg.get_texts():
            text.set_color(THEME_TEXT)

        fig.subplots_adjust(bottom=0.22)
        fig.text(
            0.5,
            0.02,
            "Feuille Marge_Reelle_Devis · lignes ALL_LINES_VALIDE = True · "
            "moyenne simple de (marge € ÷ PDV_DEVIS_CONFIRME) par ligne · "
            "marge réelle = MARGE_EVENTS_REEL (avant commission site EVO2)",
            ha="center",
            fontsize=8,
            color=THEME_MUTED,
            transform=fig.transFigure,
        )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
        plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

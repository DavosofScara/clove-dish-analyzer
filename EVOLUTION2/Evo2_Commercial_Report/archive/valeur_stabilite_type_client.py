# Archived – not used by active weekly report. See archive/README.md
from __future__ import annotations

import base64
import io
import logging
from typing import Tuple

import matplotlib.pyplot as plt
import pandas as pd

from src.config import THEME_DARK, THEME_TEXT
from src.load_data import get_ci_column, normalize_str_series
from src.metrics import _safe_divide
from src.status_norm import is_confirmed_exact

logger = logging.getLogger(__name__)


def compute_section2_client_type(df: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    type_col = get_ci_column(df, "TYPE_DE_CLIENT")
    if not type_col:
        raise ValueError("TYPE_DE_CLIENT column not found.")

    client_col = get_ci_column(df, "CLIENT_ID")
    confirme_col = get_ci_column(df, "CONFIRME")
    pdv_col = get_ci_column(df, "PDV_DEVIS")
    if not (client_col and confirme_col and pdv_col):
        raise ValueError("Missing required columns for Section 2 (CLIENT_ID, CONFIRME, PDV_DEVIS).")

    df = df.copy()
    df[client_col] = normalize_str_series(df[client_col])
    df = df[df[client_col] != ""]
    df[pdv_col] = df[pdv_col].fillna(0.0)
    df[type_col] = normalize_str_series(df[type_col])
    df = df[df[type_col] != ""]

    cdp_col = get_ci_column(df, "CDP")
    if not cdp_col:
        raise ValueError("CDP column missing for Section 2 deduplication.")

    client_agg = (
        df.groupby([cdp_col, client_col, type_col], as_index=False)
        .agg(
            PDV_CLIENT=(pdv_col, "sum"),
            CONFIRME_FLAG=(confirme_col, lambda s: s.map(is_confirmed_exact).any()),
        )
    )

    total_clients = client_agg.groupby(type_col)[client_col].nunique()
    conf_clients = client_agg[client_agg["CONFIRME_FLAG"]].groupby(type_col)[client_col].nunique()

    pdv_median = client_agg.groupby(type_col)["PDV_CLIENT"].median()
    pdv_mean = client_agg.groupby(type_col)["PDV_CLIENT"].mean()

    pdv_confirmed = client_agg[client_agg["CONFIRME_FLAG"]].groupby(type_col)["PDV_CLIENT"].sum()
    total_confirmed = pdv_confirmed.sum()
    share_conf = _safe_divide(pdv_confirmed, pd.Series(total_confirmed, index=pdv_confirmed.index))

    out = pd.DataFrame({
        "Type_client": total_clients.index,
        "Clients_uniques": total_clients.values,
        "Taux_confirmation": _safe_divide(conf_clients.reindex(total_clients.index, fill_value=0), total_clients).values,
        "PDV_median": pdv_median.reindex(total_clients.index, fill_value=0).values,
        "PDV_moyen": pdv_mean.reindex(total_clients.index, fill_value=0).values,
        "Part_PDV_confirme": share_conf.reindex(total_clients.index, fill_value=0).values,
    })

    return out.sort_values("Part_PDV_confirme", ascending=False), type_col


def render_cdp_type_stack(df: pd.DataFrame, max_cdp: int = 8) -> str:
    """Graphique 100% empilé : PDV confirmé par CDP × TYPE_DE_CLIENT."""
    if df.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", color=THEME_TEXT)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    conf_col = get_ci_column(df, "CONFIRME")
    pdv_col = get_ci_column(df, "PDV_DEVIS")
    cdp_col = get_ci_column(df, "CDP")
    type_col = get_ci_column(df, "TYPE_DE_CLIENT")
    if not all([conf_col, pdv_col, cdp_col, type_col]):
        raise ValueError("CONFIRME, PDV_DEVIS, CDP, TYPE_DE_CLIENT required.")

    work = df.copy()
    confirmed = work[work[conf_col].map(is_confirmed_exact)].copy()
    confirmed[pdv_col] = pd.to_numeric(confirmed[pdv_col], errors="coerce").fillna(0.0)

    pivot = (
        confirmed.groupby([cdp_col, type_col])[pdv_col]
        .sum()
        .reset_index()
        .pivot(index=cdp_col, columns=type_col, values=pdv_col)
        .fillna(0.0)
    )

    if pivot.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", color=THEME_TEXT)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    totals = pivot.sum(axis=1).sort_values(ascending=False)
    pivot = pivot.loc[totals.index].head(max_cdp)
    row_totals = pivot.sum(axis=1).replace(0, pd.NA)
    pivot = pivot.div(row_totals, axis=0).fillna(0.0)
    type_totals = pivot.sum(axis=0).sort_values(ascending=False)
    pivot = pivot[type_totals.index]

    label_color_overrides = {
        "INCONNU": "#ffffff",
        "Autre": "#9adfb0",
        "CLUB_MED": "#f2c94c",
        "Agence évènementielle": "#1f77b4",
        "Office de Tourisme": "#e25555",
        "Ancien Client": "#9fd1ff",
        "Hotel": "#2f5f9f",
        "Entreprise": "#ff7f0e",
    }
    colors = [label_color_overrides.get(str(col), "#9ea3b5") for col in pivot.columns]

    fig, ax = plt.subplots(figsize=(8, 4 + 0.35 * len(pivot.index)))
    fig.patch.set_facecolor(THEME_DARK)
    ax.set_facecolor(THEME_DARK)
    left = pd.Series([0.0] * len(pivot.index), index=pivot.index)
    for color, col in zip(colors, pivot.columns):
        ax.barh(pivot.index, pivot[col], left=left, color=color, edgecolor="none", label=str(col))
        left = left + pivot[col]

    from matplotlib.ticker import PercentFormatter

    ax.set_xlabel("Répartition du PDV confirmé (%)", color=THEME_TEXT)
    ax.set_xlim(0, 1.0)
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.tick_params(colors=THEME_TEXT)
    for spine in ax.spines.values():
        spine.set_color(THEME_TEXT)
    ax.grid(axis="x", alpha=0.2, color=THEME_TEXT)
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=min(3, len(pivot.columns)),
        frameon=False,
        fontsize=8,
        labelcolor=THEME_TEXT,
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
    plt.close(fig)
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"

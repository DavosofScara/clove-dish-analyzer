# Archived – not used by active weekly report. See archive/README.md
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from src.load_data import get_ci_column, normalize_str_series
from src.metrics import _safe_divide
from src.status_norm import is_confirmed_exact


def _find_column(
    df: pd.DataFrame,
    candidates: list[str],
    token_groups: list[list[str]],
) -> Optional[str]:
    for name in candidates:
        actual = get_ci_column(df, name)
        if actual:
            return actual
    upper_cols = {c.upper(): c for c in df.columns}
    for upper, original in upper_cols.items():
        for tokens in token_groups:
            if all(tok in upper for tok in tokens):
                return original
    return None


def compute_section3_agents(df: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    agent_col = _find_column(
        df,
        candidates=["NOM_AGENT", "AGENT", "COMMERCIAL", "NOM_COMMERCIAL"],
        token_groups=[["AGENT"]],
    )
    if not agent_col:
        raise ValueError("Agent column not found.")

    client_col = get_ci_column(df, "CLIENT_ID")
    confirme_col = get_ci_column(df, "CONFIRME")
    pdv_col = get_ci_column(df, "PDV_DEVIS")
    if not (client_col and confirme_col and pdv_col):
        raise ValueError("Missing required columns for Section 3 (CLIENT_ID, CONFIRME, PDV_DEVIS).")

    df = df.copy()
    df[client_col] = normalize_str_series(df[client_col])
    df = df[df[client_col] != ""]
    df[pdv_col] = df[pdv_col].fillna(0.0)
    df[agent_col] = normalize_str_series(df[agent_col])
    df = df[df[agent_col] != ""]

    total_clients = df.groupby(agent_col)[client_col].nunique()
    conf_clients = df[df[confirme_col].map(is_confirmed_exact)].groupby(agent_col)[client_col].nunique()

    client_pdv = df.groupby([agent_col, client_col])[pdv_col].sum().reset_index()
    pdv_median = client_pdv.groupby(agent_col)[pdv_col].median()

    pdv_confirmed = df[df[confirme_col].map(is_confirmed_exact)].groupby(agent_col)[pdv_col].sum()
    pdv_per_conf_client = _safe_divide(
        pdv_confirmed.reindex(total_clients.index, fill_value=0),
        conf_clients.reindex(total_clients.index, fill_value=0),
    )

    out = pd.DataFrame({
        "Agent": total_clients.index,
        "Clients_uniques": total_clients.values,
        "Taux_confirmation": _safe_divide(conf_clients.reindex(total_clients.index, fill_value=0), total_clients).values,
        "PDV_median_client": pdv_median.reindex(total_clients.index, fill_value=0).values,
        "PDV_confirme": pdv_confirmed.reindex(total_clients.index, fill_value=0).values,
        "PDV_par_client_confirme": pdv_per_conf_client.values,
    })

    return out.sort_values("PDV_confirme", ascending=False), agent_col

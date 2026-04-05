from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd

from .load_data import get_ci_column, normalize_str_series
from .status_norm import is_cancelled_status, is_confirmed_exact, is_en_cours


def _safe_divide(num: pd.Series, den: pd.Series) -> pd.Series:
    out = num / den.replace(0, pd.NA)
    return pd.to_numeric(out, errors="coerce").fillna(0.0)


def _prep_client_df(df: pd.DataFrame) -> pd.DataFrame:
    client_col = get_ci_column(df, "CLIENT_ID")
    if not client_col:
        raise ValueError("CLIENT_ID column missing.")
    df = df.copy()
    df[client_col] = normalize_str_series(df[client_col])
    return df[df[client_col] != ""]


def compute_section1_cdp(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    cdp_col = get_ci_column(df, "CDP")
    client_col = get_ci_column(df, "CLIENT_ID")
    confirme_col = get_ci_column(df, "CONFIRME")
    pdv_col = get_ci_column(df, "PDV_DEVIS")

    if not (cdp_col and client_col and confirme_col and pdv_col):
        raise ValueError("Missing required columns for Section 1 (CDP, CLIENT_ID, CONFIRME, PDV_DEVIS).")

    df = _prep_client_df(df)
    df[pdv_col] = df[pdv_col].fillna(0.0)

    total_clients = df.groupby(cdp_col)[client_col].nunique()
    conf_clients = df[df[confirme_col].map(is_confirmed_exact)].groupby(cdp_col)[client_col].nunique()
    encours_clients = df[df[confirme_col].map(is_en_cours)].groupby(cdp_col)[client_col].nunique()
    annule_clients = df[df[confirme_col].map(is_cancelled_status)].groupby(cdp_col)[client_col].nunique()

    pdv_total = df.groupby(cdp_col)[pdv_col].sum()
    pdv_confirmed = df[df[confirme_col].map(is_confirmed_exact)].groupby(cdp_col)[pdv_col].sum()

    client_pdv = df.groupby([cdp_col, client_col])[pdv_col].sum().reset_index()
    pdv_median = client_pdv.groupby(cdp_col)[pdv_col].median()
    pdv_mean = client_pdv.groupby(cdp_col)[pdv_col].mean()

    out = pd.DataFrame({
        "CDP": total_clients.index,
        "Clients_uniques": total_clients.values,
        "Clients_confirmes": conf_clients.reindex(total_clients.index, fill_value=0).values,
        "Clients_en_cours": encours_clients.reindex(total_clients.index, fill_value=0).values,
        "Clients_annules": annule_clients.reindex(total_clients.index, fill_value=0).values,
        "Taux_confirmation": _safe_divide(conf_clients.reindex(total_clients.index, fill_value=0), total_clients).values,
        "PDV_total": pdv_total.reindex(total_clients.index, fill_value=0).values,
        "PDV_confirme": pdv_confirmed.reindex(total_clients.index, fill_value=0).values,
        "PDV_median_client": pdv_median.reindex(total_clients.index, fill_value=0).values,
        "PDV_moyen_client": pdv_mean.reindex(total_clients.index, fill_value=0).values,
    })

    sanity = {
        "confirmed_le_total": float((out["Clients_confirmes"] <= out["Clients_uniques"]).all()),
        "rates_valid": float(((out["Taux_confirmation"] >= 0) & (out["Taux_confirmation"] <= 1)).all()),
    }

    return out.sort_values("PDV_confirme", ascending=False), sanity

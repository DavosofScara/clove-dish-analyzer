from __future__ import annotations

from datetime import date
from typing import Dict, Optional, Tuple

import pandas as pd

from .load_data import get_ci_column, normalize_str_series
from .periods import date_in_range
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


def filter_rows_by_date_operation(
    df: pd.DataFrame,
    period_start: date,
    period_end: date,
) -> pd.DataFrame:
    """Keep rows whose ``Date_opération`` falls in [period_start, period_end] inclusive."""
    date_col = get_ci_column(df, "Date_opération")
    if not date_col:
        raise ValueError("Date_opération column missing.")
    mask = df[date_col].apply(lambda d: date_in_range(d, period_start, period_end))
    return df.loc[mask].copy()


def compute_section1_cdp(
    df: pd.DataFrame,
    *,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    cdp_col = get_ci_column(df, "CDP")
    client_col = get_ci_column(df, "CLIENT_ID")
    confirme_col = get_ci_column(df, "CONFIRME")
    pdv_col = get_ci_column(df, "PDV_DEVIS")

    if not (cdp_col and client_col and confirme_col and pdv_col):
        raise ValueError("Missing required columns for Section 1 (CDP, CLIENT_ID, CONFIRME, PDV_DEVIS).")

    work = _prep_client_df(df)
    if period_start is not None and period_end is not None:
        work = filter_rows_by_date_operation(work, period_start, period_end)
    work[pdv_col] = work[pdv_col].fillna(0.0)

    if work.empty:
        return (
            pd.DataFrame(
                columns=[
                    "CDP",
                    "Clients_uniques",
                    "Clients_confirmes",
                    "Clients_en_cours",
                    "Clients_annules",
                    "Taux_confirmation",
                    "PDV_total",
                    "PDV_confirme",
                    "PDV_median_client",
                    "PDV_moyen_client",
                ]
            ),
            {"confirmed_le_total": 1.0, "rates_valid": 1.0},
        )

    total_clients = work.groupby(cdp_col)[client_col].nunique()
    conf_clients = work[work[confirme_col].map(is_confirmed_exact)].groupby(cdp_col)[client_col].nunique()
    encours_clients = work[work[confirme_col].map(is_en_cours)].groupby(cdp_col)[client_col].nunique()
    annule_clients = work[work[confirme_col].map(is_cancelled_status)].groupby(cdp_col)[client_col].nunique()

    pdv_total = work.groupby(cdp_col)[pdv_col].sum()
    pdv_confirmed = work[work[confirme_col].map(is_confirmed_exact)].groupby(cdp_col)[pdv_col].sum()

    client_pdv = work.groupby([cdp_col, client_col])[pdv_col].sum().reset_index()
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


def compute_cdp_margin_pct_averages(
    marge_df: pd.DataFrame,
    *,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    max_cdp: int = 8,
) -> pd.DataFrame:
    """
    Per CDP: simple mean of row-level margin % = 100 × margin_eur / PDV_DEVIS.
    Budget = MARGE_EVENTS_FINAL_BUDGET; réelle = MARGE_EVENTS_REELLE (before site commission).
    """
    empty = pd.DataFrame(
        columns=[
            "CDP",
            "Marge_budget_pct_moyenne",
            "Marge_reelle_pct_moyenne",
            "N_lignes",
        ]
    )
    if marge_df.empty:
        return empty

    sub = marge_df.copy()
    if period_start is not None and period_end is not None:
        if "Date_opération" not in sub.columns:
            raise ValueError("Date_opération column missing on Marge_Reelle_Devis.")
        mask = sub["Date_opération"].apply(lambda d: date_in_range(d, period_start, period_end))
        sub = sub.loc[mask].copy()
    if sub.empty:
        return empty

    pdv = sub["PDV_DEVIS"].astype(float)
    sub["_budget_pct"] = 100.0 * sub["MARGE_EVENTS_FINAL_BUDGET"].fillna(0) / pdv
    sub["_reelle_pct"] = 100.0 * sub["MARGE_EVENTS_REELLE"].fillna(0) / pdv

    agg = (
        sub.groupby("CDP", as_index=False)
        .agg(
            Marge_budget_pct_moyenne=("_budget_pct", "mean"),
            Marge_reelle_pct_moyenne=("_reelle_pct", "mean"),
            N_lignes=("CDP", "count"),
        )
        .sort_values("Marge_reelle_pct_moyenne", ascending=False)
    )
    return agg.head(max_cdp).reset_index(drop=True)

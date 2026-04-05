# Archived – not used by active weekly report. See archive/README.md
from __future__ import annotations

from typing import Dict

import pandas as pd

from src.load_data import get_ci_column, normalize_str_series


def compute_section4_concentration(df: pd.DataFrame) -> Dict[str, object]:
    client_col = get_ci_column(df, "CLIENT_ID")
    pdv_col = get_ci_column(df, "PDV_DEVIS")
    cdp_col = get_ci_column(df, "CDP")
    if not (client_col and pdv_col):
        raise ValueError("Missing required columns for Section 4 (CLIENT_ID, PDV_DEVIS).")

    df = df.copy()
    df[client_col] = normalize_str_series(df[client_col])
    df = df[df[client_col] != ""]
    df[pdv_col] = df[pdv_col].fillna(0.0)

    client_pdv = df.groupby(client_col)[pdv_col].sum().sort_values(ascending=False)
    total_pdv = client_pdv.sum()
    top5_share = float(client_pdv.head(5).sum() / total_pdv) if total_pdv else 0.0
    top10_share = float(client_pdv.head(10).sum() / total_pdv) if total_pdv else 0.0

    cdp_top5 = {}
    if cdp_col:
        for cdp, grp in df.groupby(cdp_col):
            cdp_client = grp.groupby(client_col)[pdv_col].sum().sort_values(ascending=False)
            total = cdp_client.sum()
            share = float(cdp_client.head(5).sum() / total) if total else 0.0
            cdp_top5[cdp] = share
    top_risky = sorted(cdp_top5.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "top5_share": top5_share,
        "top10_share": top10_share,
        "cdp_top5_risk": top_risky,
    }

#!/usr/bin/env python3
"""
Compare ÉTÉ 2025 duplicate-detection strategies on DOSSIER TRAVAIL recap extract.

Usage (from Evo2_Commercial_Report/):
    python scripts/analyze_ete_2025_duplicates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import pandas as pd

from src.config import DOSSIERS_TB_ROOT, ETE_2025_DEFINITIVE_CSV, NEW_LOADS_DIR
from src.historical_extract import extract_dossier_tb_pre_v13, extract_dossier_travail
from src.historical_master import (
    _amount,
    _client_column,
    _filter_ete_2025_confirmed,
    _norm_client,
    _norm_cdp,
    _parse_date,
    _recap_is_confirmed,
    _source_file_rank,
    analyze_duplicates,
    load_ete_2025_definitive,
    merge_ete_2025_definitive,
    normalize_devis_rows,
    normalize_recap_rows,
)


def _ete_confirmed_recap(recap: pd.DataFrame) -> pd.DataFrame:
    date_col = "Date opération"
    conf_col = "EC/C/A"
    amt_col = "Prix de vente final"
    client_col = _client_column(recap)

    raw = recap.copy()
    raw["_date"] = _parse_date(raw[date_col])
    raw["_amt"] = raw[amt_col].map(_amount)
    raw["_cdp"] = raw["CDP"].map(_norm_cdp) if "CDP" in raw.columns else ""
    raw["_client"] = raw[client_col].map(_norm_client) if client_col else ""
    raw["_conf"] = raw[conf_col].map(_recap_is_confirmed)
    mask = (
        raw["_conf"]
        & raw["_date"].notna()
        & raw["_date"].between("2025-05-01", "2025-09-30")
        & (raw["_amt"] > 0)
    )
    return raw.loc[mask].copy()


def _report(label: str, df: pd.DataFrame) -> None:
    june = df[df["_date"].dt.month == 6]
    july = df[df["_date"].dt.month == 7]
    print(
        f"  {label:42s} {len(df):4d} rows  "
        f"total €{df['_amt'].sum():>10,.0f}  "
        f"june €{june['_amt'].sum():>8,.0f}  "
        f"july €{july['_amt'].sum():>8,.0f}"
    )


def main() -> int:
    if not NEW_LOADS_DIR.is_dir():
        print(f"Missing New Loads copy: {NEW_LOADS_DIR}")
        return 1

    print("Extracting recap + pre-V13 TB (fresh read)...")
    recap = extract_dossier_travail(NEW_LOADS_DIR)
    tb = extract_dossier_tb_pre_v13(DOSSIERS_TB_ROOT)
    ete = _ete_confirmed_recap(recap)

    print("\n=== Recap dedupe strategies (ÉTÉ 2025 confirmed) ===")
    _report("1. Raw (all snapshot files)", ete)
    _report("2. Dedupe date + amount", ete.drop_duplicates(["_date", "_amt"], keep="first"))
    _report(
        "3. Dedupe date + amount + CDP + client",
        ete.drop_duplicates(["_date", "_amt", "_cdp", "_client"], keep="first"),
    )

    ranked = ete.copy()
    ranked["_rank"] = ranked["Source File"].map(_source_file_rank)
    ranked = ranked.sort_values("_rank")
    _report(
        "4. Prefer canonical file, then biz key",
        ranked.drop_duplicates(["_date", "_amt", "_cdp", "_client"], keep="first"),
    )

    canonical_only = ete[
        ete["Source File"].str.upper().str.endswith("DOSSIER TRAVAIL CA.XLS")
    ]
    _report("5. Canonical DOSSIER TRAVAIL CA.xls rows only", canonical_only)
    _report(
        "6. #5 + date + amount + CDP + client",
        canonical_only.drop_duplicates(["_date", "_amt", "_cdp", "_client"], keep="first"),
    )

    merged = merge_ete_2025_definitive(recap, tb)
    definitive = load_ete_2025_definitive(ETE_2025_DEFINITIVE_CSV)
    if definitive.empty:
        definitive = merged

    print("\n=== Pipeline outputs ===")
    recap_norm = _filter_ete_2025_confirmed(normalize_recap_rows(recap))
    tb_norm = _filter_ete_2025_confirmed(normalize_devis_rows(tb))
    tb_dedup_id = tb_norm.drop_duplicates(subset=["DEVIS_ID"], keep="last")
    print(
        f"  Recap normalized (current dedupe): {len(recap_norm):4d} rows  "
        f"€{recap_norm['PDV_DEVIS_CONFIRME'].sum():,.0f}"
    )
    print(
        f"  TB pre-v13 raw:                    {len(tb_norm):4d} rows  "
        f"€{tb_norm['PDV_DEVIS_CONFIRME'].sum():,.0f}"
    )
    print(
        f"  TB dedupe by DEVIS_ID:             {len(tb_dedup_id):4d} rows  "
        f"€{tb_dedup_id['PDV_DEVIS_CONFIRME'].sum():,.0f}"
    )
    print(
        f"  Merged definitive:                 {len(merged):4d} rows  "
        f"€{merged['PDV_DEVIS_CONFIRME'].sum():,.0f}"
    )

    print("\n=== analyze_duplicates() summary ===")
    for name, ca in analyze_duplicates(recap, tb).items():
        print(f"  {name}: €{ca:,.0f}")

    print("\n=== Definitive monthly (loaded from CSV) ===")
    monthly = definitive.groupby(definitive["Date_opération"].dt.to_period("M"))["PDV_DEVIS_CONFIRME"].sum()
    for period, ca in monthly.items():
        print(f"  {period}: €{ca:,.0f}")

    june = definitive[definitive["Date_opération"].dt.month == 6]
    dup_june = june.groupby(
        [june["Date_opération"].dt.date, june["PDV_DEVIS_CONFIRME"].round(2), june["CDP"].astype(str)]
    ).filter(lambda g: len(g) > 1)
    print(f"\nJune duplicate groups in definitive (date+amt+cdp): {dup_june.groupby(level=0).ngroups if len(dup_june) else 0}")
    print(f"June rows in definitive: {len(june)}  CA €{june['PDV_DEVIS_CONFIRME'].sum():,.0f}")

    tb_dup = tb_norm[tb_norm.duplicated(subset=["DEVIS_ID"], keep=False)]
    if not tb_dup.empty:
        extra = tb_dup["PDV_DEVIS_CONFIRME"].sum() - tb_dedup_id["PDV_DEVIS_CONFIRME"].sum()
        print(
            f"\nTB duplicate DEVIS_ID rows: {len(tb_dup)} "
            f"({tb_dup['DEVIS_ID'].nunique()} ids); extra CA if kept: €{extra:,.0f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

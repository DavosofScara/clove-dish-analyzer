#!/usr/bin/env python3
"""
Build historical extracts from New Loads DOSSIER TRAVAIL copy + pre-V13 TB dossiers.

Usage (from Evo2_Commercial_Report/):
    python scripts/build_ete_2025_definitive.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.config import (
    DOSSIER_TB_PRE_V13_CSV,
    DOSSIER_TRAVAIL_MASTER_CSV,
    DOSSIERS_TB_ROOT,
    ETE_2025_DEFINITIVE_CSV,
    NEW_LOADS_DIR,
)
from src.historical_extract import extract_dossier_tb_pre_v13, extract_dossier_travail
from src.historical_master import (
    analyze_duplicates,
    merge_ete_2025_definitive,
    save_ete_2025_definitive,
    summarize_ete_2025,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    if not NEW_LOADS_DIR.is_dir():
        logger.error("New Loads copy not found: %s", NEW_LOADS_DIR)
        return 1

    logger.info("Extracting DOSSIER TRAVAIL recap from %s", NEW_LOADS_DIR)
    recap = extract_dossier_travail(NEW_LOADS_DIR)
    DOSSIER_TRAVAIL_MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    recap.to_csv(DOSSIER_TRAVAIL_MASTER_CSV, index=False)
    logger.info("Wrote %s (%d rows)", DOSSIER_TRAVAIL_MASTER_CSV, len(recap))

    logger.info("Extracting pre-V13 TB dossiers from %s", DOSSIERS_TB_ROOT)
    tb = extract_dossier_tb_pre_v13(DOSSIERS_TB_ROOT)
    tb.to_csv(DOSSIER_TB_PRE_V13_CSV, index=False)
    logger.info("Wrote %s (%d rows)", DOSSIER_TB_PRE_V13_CSV, len(tb))

    definitive = merge_ete_2025_definitive(recap, tb)
    save_ete_2025_definitive(definitive)

    monthly = summarize_ete_2025(definitive)
    total = definitive["PDV_DEVIS_CONFIRME"].sum() if not definitive.empty else 0

    print("\n=== Dedupe strategy comparison (ÉTÉ 2025 confirmed CA) ===")
    for name, ca in analyze_duplicates(recap, tb).items():
        print(f"  {name}: €{ca:,.0f}")

    print("\n=== ÉTÉ 2025 definitive summary (after dedupe) ===")
    print(f"Rows: {len(definitive)}")
    print(f"Total CA HT (confirmed): €{total:,.0f}")
    for month, ca in sorted(monthly.items()):
        print(f"  {month}: €{ca:,.0f}")
    print(f"\nOutput: {ETE_2025_DEFINITIVE_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

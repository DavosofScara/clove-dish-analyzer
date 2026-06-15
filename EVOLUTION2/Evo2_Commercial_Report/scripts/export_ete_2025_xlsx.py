#!/usr/bin/env python3
"""
Export ÉTÉ 2025 confirmed CA to Excel (Agent, Client, Date d'opération, Prix de vente final).

Usage (from Evo2_Commercial_Report/):
    python scripts/export_ete_2025_xlsx.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.config import (
    DOSSIERS_TB_ROOT,
    ETE_2025_EXPORT_END,
    ETE_2025_EXPORT_XLSX,
    ETE_2025_START,
    NEW_LOADS_DIR,
    OUTPUTS_DIR,
)
from src.historical_extract import extract_dossier_tb_pre_v13, extract_dossier_travail
from src.historical_master import build_ete_2025_export, save_ete_2025_export_xlsx

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    if not NEW_LOADS_DIR.is_dir():
        logger.error("New Loads copy not found: %s", NEW_LOADS_DIR)
        return 1

    logger.info("Extracting recap from %s", NEW_LOADS_DIR)
    recap = extract_dossier_travail(NEW_LOADS_DIR)
    logger.info("Extracting pre-V13 TB from %s", DOSSIERS_TB_ROOT)
    tb = extract_dossier_tb_pre_v13(DOSSIERS_TB_ROOT)

    export = build_ete_2025_export(recap, tb)
    save_ete_2025_export_xlsx(recap, tb, ETE_2025_EXPORT_XLSX)

    mirror = OUTPUTS_DIR / ETE_2025_EXPORT_XLSX.name
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    save_ete_2025_export_xlsx(recap, tb, mirror)

    total = export["Prix de vente final"].sum() if not export.empty else 0
    print(f"\nÉTÉ 2025 export ({ETE_2025_START.strftime('%d/%m')}–{ETE_2025_EXPORT_END.strftime('%d/%m/%Y')})")
    print(f"Rows: {len(export)}")
    print(f"Total CA HT (confirmed): €{total:,.2f}")
    if not export.empty:
        print(f"  recap: {(export['Source'] == 'recap').sum()} rows")
        print(f"  TB pre-V13: {(export['Source'] == 'TB pre-V13').sum()} rows")
        missing_path = (export["Chemin source"].astype(str).str.strip() == "").sum()
        if missing_path:
            print(f"  Warning: {missing_path} rows missing Chemin source")
    print(f"\nOutput:")
    print(f"  {ETE_2025_EXPORT_XLSX}")
    print(f"  {mirror}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

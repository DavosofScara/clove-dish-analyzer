from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv  # optional
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = PROJECT_DIR.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs"
LOG_DIR = PROJECT_DIR / "logs"
HISTORICAL_DATA_DIR = PROJECT_DIR / "data" / "historical"

# Frozen legacy DOSSIER TRAVAIL copy (Dropbox New Loads snapshot).
NEW_LOADS_DIR = Path(
    "/Users/davidcraig/Evolution2 Events Dropbox/"
    "djacraig@hotmail.com/New Loads/DOSSIERS CA copy"
)
DOSSIERS_TB_ROOT = Path(
    "/Users/davidcraig/Evolution2 Events Dropbox/"
    "djacraig@hotmail.com/DOSSIERS_TB"
)

ETE_2025_START = date(2025, 5, 1)
ETE_2025_END = date(2025, 11, 15)
ETE_2025_EXPORT_END = date(2025, 11, 14)
DOSSIER_TRAVAIL_MASTER_CSV = HISTORICAL_DATA_DIR / "dossier_travail_master.csv"
DOSSIER_TB_PRE_V13_CSV = HISTORICAL_DATA_DIR / "dossier_tb_pre_v13.csv"
ETE_2025_DEFINITIVE_CSV = HISTORICAL_DATA_DIR / "ete_2025_definitive.csv"
ETE_2025_EXPORT_XLSX = HISTORICAL_DATA_DIR / "ete_2025_confirme_export.xlsx"


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

ENV_PATH = REPO_DIR / ".env"
if load_dotenv and ENV_PATH.exists():
    load_dotenv(ENV_PATH)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
DROPBOX_REPORT_URL = os.getenv("DROPBOX_REPORT_URL", "")


def parse_recipient_list(raw: str) -> List[str]:
    """Split comma- or semicolon-separated addresses from .env."""
    if not raw or not str(raw).strip():
        return []
    parts = re.split(r"[,;]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


# RECIPIENT_EMAILS if set, else RECIPIENT_EMAIL (backward compatible)
RECIPIENT_EMAILS = parse_recipient_list(
    os.getenv("RECIPIENT_EMAILS", "") or os.getenv("RECIPIENT_EMAIL", "")
)

# Optional CC (comma/semicolon-separated); CC_EMAILS or CC_EMAIL
CC_EMAILS = parse_recipient_list(os.getenv("CC_EMAILS", "") or os.getenv("CC_EMAIL", ""))


# ---------------------------------------------------------------------------
# Data source (same as weekly report)
# ---------------------------------------------------------------------------

EXCEL_PATH = Path(
    "/Users/davidcraig/Evolution2 Events Dropbox/"
    "djacraig@hotmail.com/DOSSIERS_TB/ALL_DOSSIERS_CA_2025/REPORTS/"
    "Evolution2_Report_V13.xlsm"
)
EXCEL_SHEET_NAME = "extract_devis"
MARGE_REELLE_SHEET_NAME = os.getenv("MARGE_REELLE_SHEET_NAME", "Marge_Reelle_Devis")

# Local path (pandas reads the synced file). Override with CLIENT_DB_PATH in .env.
_DEFAULT_CLIENT_DB = (
    "/Users/davidcraig/Evolution2 Events Dropbox/"
    "djacraig@hotmail.com/DOSSIERS_TB/ALL_DOSSIERS_CA_2025/CLIENT_DATABASE/"
    "Clients Database.xlsx"
)
_client_db_path_raw = (os.getenv("CLIENT_DB_PATH") or "").strip()
CLIENT_DB_PATH = Path(_client_db_path_raw) if _client_db_path_raw else Path(_DEFAULT_CLIENT_DB)

# Share link for humans / email copy (optional — not used to open the workbook).
DROPBOX_CLIENT_DATABASE_URL = (os.getenv("DROPBOX_CLIENT_DATABASE_URL") or "").strip()

# Sheet name in Clients Database.xlsx. Default unchanged from original code (MARKETING_MAIL).
# Set CLIENT_DB_SHEET_NAME=CLIENTS in .env when DATE CONFIRME lives on the CLIENTS sheet.
CLIENT_DB_SHEET_NAME = os.getenv("CLIENT_DB_SHEET_NAME", "MARKETING_MAIL")


# ---------------------------------------------------------------------------
# Logos (same as weekly report candidates)
# ---------------------------------------------------------------------------

CLOVE_LOGO_CANDIDATES = [
    REPO_DIR / "Color logo - no background.png",
    REPO_DIR / "clove_logo.png",
    REPO_DIR / "clove_color_logo.png",
    Path("/Users/davidcraig/code/clove/Clove_Sales_Analyzer/For Web") / "clove_logo.png",
]
EVO2_LOGO_CANDIDATES = [
    REPO_DIR / "evo2_logo.png",
    REPO_DIR / "evo2_log.png",
]


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

CLOVE_GREEN = "#62d13c"
CLOVE_GREEN_DARK = "#59a52c"
CLOVE_GREEN_MUTED = "#3a7d32"  # budget margin bars (less intense than réelle)
THEME_DARK = "#222831"
THEME_DARK_ALT = "#1a1d26"
THEME_BORDER = "#2d3139"
THEME_TEXT = "#f5f5f5"
THEME_MUTED = "#9ea3b5"
THEME_TABLE_DIVIDER = "#2a2d35"
THEME_ORANGE = "#e07c3c"


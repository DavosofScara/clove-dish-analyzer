from __future__ import annotations

import os
import re
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


# ---------------------------------------------------------------------------
# Data source (same as weekly report)
# ---------------------------------------------------------------------------

EXCEL_PATH = Path(
    "/Users/davidcraig/Evolution2 Events Dropbox/"
    "djacraig@hotmail.com/DOSSIERS_TB/ALL_DOSSIERS_CA_2025/REPORTS/"
    "Evolution2_Report_V13.xlsm"
)
EXCEL_SHEET_NAME = "extract_devis"

CLIENT_DB_PATH = Path(
    "/Users/davidcraig/Evolution2 Events Dropbox/"
    "djacraig@hotmail.com/DOSSIERS_TB/ALL_DOSSIERS_CA_2025/CLIENT_DATABASE/"
    "Clients Database.xlsx"
)
CLIENT_DB_SHEET_NAME = "MARKETING_MAIL"


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
THEME_DARK = "#222831"
THEME_DARK_ALT = "#1a1d26"
THEME_BORDER = "#2d3139"
THEME_TEXT = "#f5f5f5"
THEME_MUTED = "#9ea3b5"
THEME_TABLE_DIVIDER = "#2a2d35"
THEME_ORANGE = "#e07c3c"


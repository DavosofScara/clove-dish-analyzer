#!/usr/bin/env python3
"""
Weekly Evolution2 executive report.

Usage (after refreshing Excel manually):

    python evo2_weekly_report.py

Environment:
    RESEND_API_KEY
    EMAIL_FROM
    DROPBOX_REPORT_URL
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import pandas as pd
import requests

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

try:
    from dotenv import load_dotenv  # optional but recommended
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

EXCEL_PATH = Path(
    "/Users/davidcraig/Evolution2 Events Dropbox/"
    "djacraig@hotmail.com/DOSSIERS_TB/ALL_DOSSIERS_CA_2025/REPORTS/Evolution2_Report_V13.xlsm"
)
EXCEL_SHEET_NAME = "extract_devis"

PARIS_TZ = ZoneInfo("Europe/Paris")

# Logo paths: project folder first, then env, then defaults
CLOVE_LOGO_CANDIDATES = [
    BASE_DIR / "Color logo - no background.png",
    BASE_DIR / "clove_logo.png",
    BASE_DIR / "clove_color_logo.png",
    Path("/Users/davidcraig/code/clove/Clove_Sales_Analyzer/For Web") / "clove_logo.png",
]
DEFAULT_EVO2_LOGO = BASE_DIR / "evo2_logo.png"  # fallback, we also try evo2_log.png


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "evo2_weekly_report.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid adding multiple handlers if main() is called twice
    if not root.handlers:
        # Console
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        root.addHandler(ch)

        # File
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers: parsing
# ---------------------------------------------------------------------------


def parse_excel_date(value) -> pd.Timestamp | pd.NaT:
    """
    Parse mixed Excel-like dates.

    Rules:
        - If numeric: Excel serial (origin 1899-12-30).
        - If string: parse as day-first.
        - Else: NaT.
    """
    if pd.isna(value):
        return pd.NaT

    # Numeric Excel serial
    if isinstance(value, (int, float)):
        try:
            # pandas origin for Excel 1900 system is "1899-12-30"
            return pd.to_datetime(value, unit="d", origin="1899-12-30")
        except Exception:
            return pd.NaT

    # String dates
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return pd.NaT
        try:
            return pd.to_datetime(s, dayfirst=True, errors="coerce")
        except Exception:
            return pd.NaT

    # Already datetime-like
    if isinstance(value, (datetime, pd.Timestamp, date)):
        return pd.to_datetime(value)

    return pd.NaT


def coerce_number(value) -> float | None:
    """
    Coerce European-style numeric representations to float.

    Rules:
        - Remove spaces and non-breaking spaces.
        - Remove '€'.
        - Replace comma decimal with dot.
        - Remove thousands separators heuristically.
    """
    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        value = str(value)

    s = (
        value.replace("\u00a0", " ")
        .replace("€", "")
        .replace(" ", "")
        .strip()
    )
    if not s:
        return None

    # Replace decimal comma with dot, and handle thousand separators
    if "," in s and "." in s:
        # Assume '.' are thousands, ',' is decimal
        s = s.replace(".", "").replace(",", ".")
    else:
        # Single separator
        s = s.replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return None


def normalize_str_series(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .fillna("")
        .str.strip()
    )


def get_ci_column(df: pd.DataFrame, logical_name: str) -> Optional[str]:
    """
    Return actual column name in df matching logical_name, case-insensitive.
    """
    lower_map = {c.lower(): c for c in df.columns}
    return lower_map.get(logical_name.lower())


# ---------------------------------------------------------------------------
# Time and week helpers
# ---------------------------------------------------------------------------


@dataclass
class WeekWindow:
    start: date  # Monday
    end: date    # Sunday (inclusive)


def get_last_complete_week(tz: ZoneInfo) -> WeekWindow:
    """
    Returns last complete Monday-Sunday week in given timezone.
    """
    today = datetime.now(tz).date()
    weekday = today.weekday()  # Monday=0, Sunday=6

    # Last Sunday before (or equal to) yesterday
    last_sunday = today - timedelta(days=weekday + 1)
    week_start = last_sunday - timedelta(days=6)
    return WeekWindow(start=week_start, end=last_sunday)


def get_this_week(tz: ZoneInfo) -> WeekWindow:
    """
    Returns current week Monday–Sunday in given timezone (today through end of week).
    """
    today = datetime.now(tz).date()
    weekday = today.weekday()  # Monday=0, Sunday=6
    week_start = today - timedelta(days=weekday)
    week_end = week_start + timedelta(days=6)
    return WeekWindow(start=week_start, end=week_end)


def date_in_week(d: pd.Timestamp, window: WeekWindow) -> bool:
    if pd.isna(d):
        return False
    dd = d.date()
    return window.start <= dd <= window.end


# ---------------------------------------------------------------------------
# Data loading and preparation
# ---------------------------------------------------------------------------


def load_excel_data() -> pd.DataFrame:
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel file not found: {EXCEL_PATH}")

    logger.info("Loading Excel data from %s", EXCEL_PATH)
    df = pd.read_excel(
        EXCEL_PATH,
        sheet_name=EXCEL_SHEET_NAME,
        engine="openpyxl",
        dtype=object,  # keep raw, we'll coerce manually
    )

    if df.empty:
        logger.warning("Excel sheet '%s' is empty.", EXCEL_SHEET_NAME)

    # Normalise ID columns to strings
    for col_name in ["DEVIS_ID", "CLIENT_ID"]:
        actual = get_ci_column(df, col_name)
        if actual:
            df[actual] = normalize_str_series(df[actual])
        else:
            logger.warning("Column %s not found in sheet.", col_name)

    # Date columns
    for col_name in ["Date_Demande", "Date_opération"]:
        actual = get_ci_column(df, col_name)
        if actual:
            df[actual] = df[actual].apply(parse_excel_date)
        else:
            logger.warning("Date column %s not found in sheet.", col_name)

    # Amount columns
    for col_name in ["PDV_DEVIS", "PDV_DEVIS_CONFIRME", "MARGE_FINAL_EVENTS"]:
        actual = get_ci_column(df, col_name)
        if actual:
            df[actual] = df[actual].apply(coerce_number)
        else:
            logger.warning("Amount column %s not found in sheet.", col_name)

    # CONFIRME flag
    confirme_col = get_ci_column(df, "CONFIRME")
    if confirme_col:
        df[confirme_col] = (
            normalize_str_series(df[confirme_col])
            .str.upper()
        )

    # SITE_EVOLUTION with fallback SITE
    site_evo_col = get_ci_column(df, "SITE_EVOLUTION")
    site_col = get_ci_column(df, "SITE")
    if site_evo_col or site_col:
        final = None
        if site_evo_col:
            final = normalize_str_series(df[site_evo_col])
        if site_col:
            fallback = normalize_str_series(df[site_col])
            final = final.where(final != "", other=fallback) if final is not None else fallback
        df["SITE_FINAL"] = final

    return df


def filter_confirmed(df: pd.DataFrame) -> pd.DataFrame:
    confirme_col = get_ci_column(df, "CONFIRME")
    if not confirme_col:
        logger.warning("CONFIRME column missing, treating all rows as non-confirmed.")
        return df.iloc[0:0].copy()
    confirmed = df[df[confirme_col] == "CONFIRME"].copy()
    logger.info("Confirmed rows: %d", len(confirmed))
    return confirmed


# ---------------------------------------------------------------------------
# Snapshot handling
# ---------------------------------------------------------------------------

CONFIRMED_SNAPSHOT_CSV = DATA_DIR / "confirmed_snapshot.csv"
WEEKLY_KPI_HISTORY_CSV = DATA_DIR / "weekly_kpi_history.csv"


def load_previous_snapshot() -> pd.DataFrame:
    if not CONFIRMED_SNAPSHOT_CSV.exists():
        logger.info("No previous confirmed_snapshot.csv found (first run?).")
        return pd.DataFrame(columns=["snapshot_date", "DEVIS_ID", "PDV_DEVIS_CONFIRME", "CDP"])
    try:
        df = pd.read_csv(CONFIRMED_SNAPSHOT_CSV, dtype={"DEVIS_ID": "string"})
        df["DEVIS_ID"] = normalize_str_series(df["DEVIS_ID"])
        return df
    except Exception as exc:
        logger.error("Failed to read confirmed_snapshot.csv: %s", exc)
        return pd.DataFrame(columns=["snapshot_date", "DEVIS_ID", "PDV_DEVIS_CONFIRME", "CDP"])


def save_current_snapshot(confirmed_df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    devis_col = get_ci_column(confirmed_df, "DEVIS_ID")
    pdv_conf_col = get_ci_column(confirmed_df, "PDV_DEVIS_CONFIRME")
    cdp_col = get_ci_column(confirmed_df, "CDP")

    if not devis_col:
        logger.warning("DEVIS_ID column missing in confirmed_df, skipping snapshot save.")
        return

    snapshot_date = datetime.now(PARIS_TZ).date().isoformat()
    out = pd.DataFrame()
    out["snapshot_date"] = snapshot_date
    out["DEVIS_ID"] = normalize_str_series(confirmed_df[devis_col])

    if pdv_conf_col:
        out["PDV_DEVIS_CONFIRME"] = confirmed_df[pdv_conf_col].astype(float).fillna(0.0)
    else:
        out["PDV_DEVIS_CONFIRME"] = 0.0

    if cdp_col:
        out["CDP"] = normalize_str_series(confirmed_df[cdp_col])
    else:
        out["CDP"] = ""

    try:
        out.to_csv(CONFIRMED_SNAPSHOT_CSV, index=False)
        logger.info("Saved confirmed snapshot to %s", CONFIRMED_SNAPSHOT_CSV)
    except Exception as exc:
        logger.error("Failed to save confirmed_snapshot.csv: %s", exc)


def compute_newly_confirmed(
    confirmed_df: pd.DataFrame, prev_snapshot: pd.DataFrame
) -> Tuple[pd.DataFrame, float, Optional[str], float]:
    """
    Returns:
        new_rows (DataFrame),
        newly_confirmed_value (sum PDV_DEVIS_CONFIRME),
        top_cdp_name,
        top_cdp_value
    """
    devis_col = get_ci_column(confirmed_df, "DEVIS_ID")
    pdv_conf_col = get_ci_column(confirmed_df, "PDV_DEVIS_CONFIRME")
    cdp_col = get_ci_column(confirmed_df, "CDP")

    if not devis_col or not pdv_conf_col:
        logger.warning("DEVIS_ID or PDV_DEVIS_CONFIRME missing; cannot compute newly confirmed.")
        return confirmed_df.iloc[0:0].copy(), 0.0, None, 0.0

    current_ids = set(
        normalize_str_series(confirmed_df[devis_col]).tolist()
    )

    prev_ids = set()
    if not prev_snapshot.empty and "DEVIS_ID" in prev_snapshot.columns:
        prev_ids = set(
            normalize_str_series(prev_snapshot["DEVIS_ID"]).tolist()
        )

    new_ids = current_ids - prev_ids
    logger.info("Newly confirmed deals since last snapshot: %d", len(new_ids))

    new_rows = confirmed_df[
        confirmed_df[devis_col].isin(new_ids)
    ].copy()

    if new_rows.empty:
        return new_rows, 0.0, None, 0.0

    value_series = new_rows[pdv_conf_col].astype(float).fillna(0.0)
    newly_confirmed_value = float(value_series.sum())

    # Top CDP
    top_cdp_name = None
    top_cdp_value = 0.0

    if cdp_col:
        grouped = new_rows.groupby(new_rows[cdp_col].fillna(""), dropna=False)[pdv_conf_col].sum()
        if not grouped.empty:
            top_cdp_name = str(grouped.idxmax())
            top_cdp_value = float(grouped.max())

    return new_rows, newly_confirmed_value, top_cdp_name, top_cdp_value


# ---------------------------------------------------------------------------
# Weekly KPIs and history
# ---------------------------------------------------------------------------


@dataclass
class WeeklyKPIs:
    week: WeekWindow
    new_clients: int
    proposed_value: float
    newly_confirmed_value: float
    top_cdp: Optional[str]
    top_cdp_value: float
    deltas_vs_prev: Dict[str, float]
    # Week-based totals (confirmed rows with Date_Demande in week)
    total_confirmed_week_value: float
    top_cdp_week: Optional[str]
    top_cdp_week_value: float
    # Meilleur CDP = highest sum(PDV_DEVIS) for rows with Date_Demande in week
    top_cdp_proposed: Optional[str]
    top_cdp_proposed_value: float


def load_weekly_history() -> pd.DataFrame:
    if not WEEKLY_KPI_HISTORY_CSV.exists():
        return pd.DataFrame(
            columns=[
                "week_start",
                "new_clients",
                "proposed_value",
                "newly_confirmed_value",
                "top_cdp",
                "top_cdp_value",
            ]
        )
    try:
        df = pd.read_csv(WEEKLY_KPI_HISTORY_CSV)
        if "week_start" in df.columns:
            df["week_start"] = pd.to_datetime(df["week_start"]).dt.date
        return df
    except Exception as exc:
        logger.error("Failed to read weekly_kpi_history.csv: %s", exc)
        return pd.DataFrame(
            columns=[
                "week_start",
                "new_clients",
                "proposed_value",
                "newly_confirmed_value",
                "top_cdp",
                "top_cdp_value",
            ]
        )


def compute_deltas_vs_previous_week(
    week_start: date,
    new_clients: int,
    proposed_value: float,
    newly_confirmed_value: float,
) -> Dict[str, float]:
    hist = load_weekly_history()
    if hist.empty:
        return {"new_clients": 0.0, "proposed_value": 0.0, "newly_confirmed_value": 0.0}

    # Ensure date type
    if hist["week_start"].dtype != "O":
        hist["week_start"] = pd.to_datetime(hist["week_start"]).dt.date

    prev = hist[hist["week_start"] < week_start].sort_values("week_start")
    if prev.empty:
        return {"new_clients": 0.0, "proposed_value": 0.0, "newly_confirmed_value": 0.0}

    last = prev.iloc[-1]
    deltas = {
        "new_clients": float(new_clients - float(last.get("new_clients", 0.0))),
        "proposed_value": float(proposed_value - float(last.get("proposed_value", 0.0))),
        "newly_confirmed_value": float(
            newly_confirmed_value - float(last.get("newly_confirmed_value", 0.0))
        ),
    }
    return deltas


def save_weekly_history(current: WeeklyKPIs) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hist = load_weekly_history()

    week_start = current.week.start
    row = {
        "week_start": week_start,
        "new_clients": current.new_clients,
        "proposed_value": current.proposed_value,
        "newly_confirmed_value": current.newly_confirmed_value,
        "top_cdp": current.top_cdp or "",
        "top_cdp_value": current.top_cdp_value,
    }

    if hist.empty:
        hist = pd.DataFrame([row])
    else:
        mask = hist["week_start"] == week_start
        if mask.any():
            hist = hist.loc[~mask]
            hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
        else:
            hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)

    try:
        hist.sort_values("week_start", inplace=True)
        hist.to_csv(WEEKLY_KPI_HISTORY_CSV, index=False)
        logger.info("Updated weekly KPI history at %s", WEEKLY_KPI_HISTORY_CSV)
    except Exception as exc:
        logger.error("Failed to save weekly KPI history: %s", exc)


def compute_weekly_kpis(
    df: pd.DataFrame,
    confirmed_df: pd.DataFrame,
    newly_confirmed_rows: pd.DataFrame,
    newly_confirmed_value: float,
    top_cdp: Optional[str],
    top_cdp_value: float,
    week_window: WeekWindow,
) -> WeeklyKPIs:
    date_demande_col = get_ci_column(df, "Date_Demande")
    pdv_dev_col = get_ci_column(df, "PDV_DEVIS")
    client_id_col = get_ci_column(df, "CLIENT_ID")

    if not date_demande_col:
        logger.warning("Date_Demande column missing, no weekly KPIs will be fully computed.")
        return WeeklyKPIs(
            week=week_window,
            new_clients=0,
            proposed_value=0.0,
            newly_confirmed_value=newly_confirmed_value,
            top_cdp=top_cdp,
            top_cdp_value=top_cdp_value,
            deltas_vs_prev={"new_clients": 0.0, "proposed_value": 0.0, "newly_confirmed_value": 0.0},
            total_confirmed_week_value=0.0,
            top_cdp_week=None,
            top_cdp_week_value=0.0,
            top_cdp_proposed=None,
            top_cdp_proposed_value=0.0,
        )

    in_week_mask = df[date_demande_col].apply(lambda d: date_in_week(d, week_window))
    week_df = df[in_week_mask].copy()

    # New clients
    new_clients = 0
    if client_id_col:
        client_ids = normalize_str_series(week_df[client_id_col])
        new_clients = int(client_ids[client_ids != ""].nunique())

    # Devis proposés
    proposed_value = 0.0
    if pdv_dev_col:
        proposed_value = float(
            week_df[pdv_dev_col].astype(float).fillna(0.0).sum()
        )

    # Meilleur CDP = CDP with highest sum(PDV_DEVIS) for rows with Date_Demande in week
    top_cdp_proposed: Optional[str] = None
    top_cdp_proposed_value = 0.0
    cdp_col = get_ci_column(df, "CDP")
    if cdp_col and pdv_dev_col and not week_df.empty:
        grouped_proposed = week_df.groupby(
            week_df[cdp_col].fillna(""), dropna=False
        )[pdv_dev_col].sum()
        if not grouped_proposed.empty:
            top_cdp_proposed = str(grouped_proposed.idxmax())
            top_cdp_proposed_value = float(grouped_proposed.max())

    # Valeur confirmée (confirmed rows with Date_Demande in week)
    total_confirmed_week_value = 0.0
    top_cdp_week: Optional[str] = None
    top_cdp_week_value = 0.0
    conf_date_col = get_ci_column(confirmed_df, "Date_Demande")
    conf_pdv_col = get_ci_column(confirmed_df, "PDV_DEVIS_CONFIRME")
    conf_cdp_col = get_ci_column(confirmed_df, "CDP")
    if conf_date_col and conf_pdv_col:
        conf_week_mask = confirmed_df[conf_date_col].apply(lambda d: date_in_week(d, week_window))
        week_confirmed = confirmed_df[conf_week_mask]
        if not week_confirmed.empty:
            total_confirmed_week_value = float(
                week_confirmed[conf_pdv_col].astype(float).fillna(0.0).sum()
            )
            if conf_cdp_col:
                grouped = week_confirmed.groupby(
                    week_confirmed[conf_cdp_col].fillna(""), dropna=False
                )[conf_pdv_col].sum()
                if not grouped.empty:
                    top_cdp_week = str(grouped.idxmax())
                    top_cdp_week_value = float(grouped.max())

    # Deltas vs previous week from history
    deltas = compute_deltas_vs_previous_week(
        week_start=week_window.start,
        new_clients=new_clients,
        proposed_value=proposed_value,
        newly_confirmed_value=newly_confirmed_value,
    )

    return WeeklyKPIs(
        week=week_window,
        new_clients=new_clients,
        proposed_value=proposed_value,
        newly_confirmed_value=newly_confirmed_value,
        top_cdp=top_cdp,
        top_cdp_value=top_cdp_value,
        deltas_vs_prev=deltas,
        total_confirmed_week_value=total_confirmed_week_value,
        top_cdp_week=top_cdp_week,
        top_cdp_week_value=top_cdp_week_value,
        top_cdp_proposed=top_cdp_proposed,
        top_cdp_proposed_value=top_cdp_proposed_value,
    )


# ---------------------------------------------------------------------------
# Forward 4 quarters (confirmed)
# ---------------------------------------------------------------------------


def compute_forward_quarters(
    df: pd.DataFrame,
    confirmed_df: pd.DataFrame,
) -> List[Tuple[str, float, float, float]]:
    """
    Returns list of (quarter_label, valeur_confirmée, valeur_en_cours, marge_final_events)
    for next 4 quarters, based on Date_opération.
    - valeur_confirmée: sum PDV_DEVIS_CONFIRME for confirmed rows in quarter.
    - valeur_en_cours: sum PDV_DEVIS for rows where CONFIRME == "EN COURS" in quarter.
    - marge_final_events: sum MARGE_FINAL_EVENTS for confirmed rows in quarter.
    """
    date_op_col = get_ci_column(confirmed_df, "Date_opération")
    pdv_conf_col = get_ci_column(confirmed_df, "PDV_DEVIS_CONFIRME")
    marge_col = get_ci_column(confirmed_df, "MARGE_FINAL_EVENTS")
    results: List[Tuple[str, float, float, float]] = []

    if not date_op_col or not pdv_conf_col:
        logger.warning("Date_opération or PDV_DEVIS_CONFIRME missing; no forward quarters.")
        return results

    today = datetime.now(PARIS_TZ).date()
    year = today.year
    month = today.month
    current_q = (month - 1) // 3 + 1  # 1..4

    quarters: List[Tuple[int, int]] = []
    q, y = current_q, year
    for _ in range(4):
        quarters.append((q, y))
        q += 1
        if q > 4:
            q, y = 1, y + 1

    conf_df = confirmed_df.copy()
    conf_df[date_op_col] = conf_df[date_op_col].apply(parse_excel_date)

    # EN COURS rows (full df) for valeur en cours by quarter
    en_cours_df = pd.DataFrame()
    confirme_col = get_ci_column(df, "CONFIRME")
    date_op_full = get_ci_column(df, "Date_opération")
    pdv_dev_col = get_ci_column(df, "PDV_DEVIS")
    if confirme_col and date_op_full and pdv_dev_col:
        en_cours_mask = (
            df[confirme_col].astype(str).str.upper().str.strip() == "EN COURS"
        )
        en_cours_df = df.loc[en_cours_mask].copy()
        en_cours_df[date_op_full] = en_cours_df[date_op_full].apply(parse_excel_date)

    for q, y in quarters:
        start_month = 3 * (q - 1) + 1
        end_month = start_month + 2
        start_date = date(y, start_month, 1)
        end_date = date(y, 12, 31) if end_month == 12 else date(y, end_month + 1, 1) - timedelta(days=1)

        def in_quarter(d):
            if pd.isna(d):
                return False
            try:
                _d = pd.Timestamp(d).date()
                return start_date <= _d <= end_date
            except Exception:
                return False

        mask = conf_df[date_op_col].apply(in_quarter)
        sub = conf_df[mask]
        valeur_conf = float(sub[pdv_conf_col].astype(float).fillna(0.0).sum())
        marge = float(sub[marge_col].astype(float).fillna(0.0).sum()) if marge_col else 0.0

        if not en_cours_df.empty:
            eq_mask = en_cours_df[date_op_full].apply(in_quarter)
            valeur_en_cours = float(en_cours_df.loc[eq_mask, pdv_dev_col].astype(float).fillna(0.0).sum())
        else:
            valeur_en_cours = 0.0

        results.append((f"T{q} {y}", valeur_conf, valeur_en_cours, marge))

    return results


def compute_clients_operation_this_week(df: pd.DataFrame, tz: ZoneInfo) -> int:
    """
    Number of unique CLIENT_ID with Date_opération in the current week (Mon–Sun).
    """
    date_op_col = get_ci_column(df, "Date_opération")
    client_id_col = get_ci_column(df, "CLIENT_ID")
    if not date_op_col or not client_id_col:
        return 0
    this_week = get_this_week(tz)
    mask = df[date_op_col].apply(lambda d: date_in_week(d, this_week))
    subset = df.loc[mask, client_id_col]
    ids = normalize_str_series(subset)
    return int(ids[ids != ""].nunique())


def compute_this_week_metrics(
    df: pd.DataFrame,
    tz: ZoneInfo,
) -> Tuple[int, float, int]:
    """
    Metrics for 'Cette semaine' (current week Monday–Sunday, based on Date_opération):
      - operations_count: number of rows with Date_opération in this week
      - operations_value: sum PDV_DEVIS for those rows
      - clients_in_week: unique CLIENT_ID with at least one row in this week
    """
    date_op_col = get_ci_column(df, "Date_opération")
    pdv_dev_col = get_ci_column(df, "PDV_DEVIS")
    client_id_col = get_ci_column(df, "CLIENT_ID")
    confirme_col = get_ci_column(df, "CONFIRME")

    if not date_op_col:
        return 0, 0.0, 0

    this_week = get_this_week(tz)
    week_mask = df[date_op_col].apply(lambda d: date_in_week(d, this_week))
    week_rows = df[week_mask]

    operations_count = int(len(week_rows))

    operations_value = 0.0
    if pdv_dev_col:
        operations_value = float(
            week_rows[pdv_dev_col].astype(float).fillna(0.0).sum()
        )

    clients_in_week = 0
    if client_id_col:
        clients = normalize_str_series(week_rows[client_id_col])
        clients_in_week = int(clients[clients != ""].nunique())

    return operations_count, operations_value, clients_in_week


# ---------------------------------------------------------------------------
# Email generation
# ---------------------------------------------------------------------------


def load_logo_base64(path: Path, mime: str = "image/png") -> Optional[str]:
    try:
        if not path.exists():
            return None
        with path.open("rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as exc:
        logger.warning("Failed to load logo at %s: %s", path, exc)
        return None


def get_logos() -> Tuple[Optional[str], Optional[str]]:
    # Clove: project folder first, then env, then default paths
    clove_candidates = []
    if os.getenv("CLOVE_LOGO_PATH"):
        clove_candidates.append(Path(os.getenv("CLOVE_LOGO_PATH", "")))
    clove_candidates.extend(CLOVE_LOGO_CANDIDATES)
    clove = None
    for path in clove_candidates:
        if path and path.exists():
            clove = load_logo_base64(path)
            if clove:
                break

    evo2_logo_env = os.getenv("EVO2_LOGO_PATH")
    evo2_logo_candidates = []
    if evo2_logo_env:
        evo2_logo_candidates.append(Path(evo2_logo_env))
    evo2_logo_candidates.append(DEFAULT_EVO2_LOGO)
    evo2_logo_candidates.append(BASE_DIR / "evo2_log.png")  # alternative name

    evo2 = None
    for candidate in evo2_logo_candidates:
        evo2 = load_logo_base64(candidate)
        if evo2:
            break

    return clove, evo2


def format_currency(value: float) -> str:
    # Simple Euro formatting with thousands separator
    if value is None:
        return "0 €"
    if abs(value - round(value)) < 0.005:
        return f"{int(round(value)):,} €".replace(",", " ")
    return f"{value:,.2f} €".replace(",", " ")


def format_delta(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{format_currency(abs(value))}"


def build_email_html(
    kpis: WeeklyKPIs,
    quarters: List[Tuple[str, float, float, float]],
    dropbox_url: str,
    this_week_ops_count: int = 0,
    this_week_ops_value: float = 0.0,
    this_week_clients: int = 0,
    this_week_date_range: str = "",
    resume_week_date_range: str = "",
) -> str:
    clove_logo, evo2_logo = get_logos()

    week_label = (
        f"{kpis.week.start.strftime('%d/%m/%Y')} → "
        f"{kpis.week.end.strftime('%d/%m/%Y')}"
    )

    # KPI values for 'Résumé de la semaine' (last complete week)
    nv_clients = kpis.new_clients
    dv_proposed = format_currency(kpis.proposed_value)
    # Valeur confirmée (nouvelle) – strictly snapshot-diff, no fallback
    val_conf = format_currency(kpis.newly_confirmed_value)
    # Meilleur CDP = highest sum(PDV_DEVIS) proposed in the analysed week
    top_cdp_name = kpis.top_cdp_proposed or "N/A"
    top_cdp_val = format_currency(kpis.top_cdp_proposed_value)

    # 'Cette semaine' metrics (current week, Date_opération)
    cw_ops_count = this_week_ops_count
    cw_ops_value = format_currency(this_week_ops_value)
    cw_clients = this_week_clients

    d_new_clients = kpis.deltas_vs_prev.get("new_clients", 0.0)
    d_prop = kpis.deltas_vs_prev.get("proposed_value", 0.0)
    d_conf = kpis.deltas_vs_prev.get("newly_confirmed_value", 0.0)

    d_new_clients_str = f"{d_new_clients:+.0f}"
    d_prop_str = format_delta(d_prop)
    d_conf_str = format_delta(d_conf)

    # Quarters table rows (label, valeur_confirmée, valeur_en_cours, marge)
    q_rows = ""
    for label, val_conf, val_en_cours, marge in quarters:
        marge_pct = (100.0 * marge / val_conf) if val_conf and val_conf > 0 else 0.0
        q_rows += f"""
            <tr>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2d35; color: #f5f5f5;">{label}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2d35; text-align: right; color: #f5f5f5;">{format_currency(val_conf)}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2d35; text-align: right; color: #e07c3c;">{format_currency(val_en_cours)}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2d35; text-align: right; color: #62d13c;">{marge_pct:.1f}%</td>
            </tr>
        """

    # Left header: Clove colour logo only (no text fallback)
    clove_img_html = (
        f'<img src="{clove_logo}" alt="" style="height:32px;" />'
        if clove_logo
        else ''
    )
    evo2_img_html = (
        f'<img src="{evo2_logo}" alt="Evolution2" style="height:32px;" />'
        if evo2_logo
        else '<span style="color:#f5f5f5;font-weight:600;">Evolution2</span>'
    )

    html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8" />
    <title>Résumé hebdomadaire – Evolution2</title>
</head>
<body style="margin:0;padding:0;background-color:#0f1115;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0f1115;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="background-color:#14171f;border-radius:12px;padding:24px 28px 32px;box-shadow:0 18px 40px rgba(0,0,0,0.55);border:1px solid #222633;">
          <!-- Header -->
          <tr>
            <td style="padding-bottom:20px;">
              <table width="100%" role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td align="left" style="vertical-align:middle;">
                    {clove_img_html}
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    {evo2_img_html}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Title -->
          <tr>
            <td style="padding-bottom:16px;">
              <div style="color:#f5f5f5;font-size:22px;font-weight:600;">
                Résumé hebdomadaire – Evolution2
              </div>
              <div style="color:#9ea3b5;font-size:13px;margin-top:4px;">
                Semaine du {week_label}
              </div>
            </td>
          </tr>

          <!-- Section 1: Cette semaine (current week, Date_opération) -->
          <tr>
            <td style="padding-top:8px;padding-bottom:20px;">
              <div style="color:#9ea3b5;font-size:12px;font-weight:500;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                1 • Cette semaine ({this_week_date_range})
              </div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <!-- Opérations cette semaine -->
                  <td style="width:33.33%;padding:6px 4px 6px 0;">
                    <div style="background:linear-gradient(145deg,#222831,#1a1d26);border-radius:10px;padding:12px 10px;border:1px solid #2d3139;">
                      <div style="font-size:10px;color:#9ea3b5;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">Opérations cette semaine</div>
                      <div style="font-size:18px;color:#f5f5f5;font-weight:600;">{cw_ops_count}</div>
                    </div>
                  </td>
                  <!-- Valeur de ces opérations -->
                  <td style="width:33.33%;padding:6px 4px;">
                    <div style="background:linear-gradient(145deg,#222831,#1a1d26);border-radius:10px;padding:12px 10px;border:1px solid #2d3139;">
                      <div style="font-size:10px;color:#9ea3b5;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">Valeur de ces opérations</div>
                      <div style="font-size:18px;color:#f5f5f5;font-weight:600;">{cw_ops_value}</div>
                    </div>
                  </td>
                  <!-- Nombre de clients cette semaine -->
                  <td style="width:33.33%;padding:6px 0 6px 4px;">
                    <div style="background:linear-gradient(145deg,#222831,#1a1d26);border-radius:10px;padding:12px 10px;border:1px solid #2d3139;">
                      <div style="font-size:10px;color:#9ea3b5;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">Nombre de clients cette semaine</div>
                      <div style="font-size:18px;color:#f5f5f5;font-weight:600;">{cw_clients}</div>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Section 2: Résumé de la semaine (last complete week) -->
          <tr>
            <td style="padding-top:4px;padding-bottom:20px;">
              <div style="color:#9ea3b5;font-size:12px;font-weight:500;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                2 • Résumé de la semaine ({resume_week_date_range})
              </div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <!-- Nouveaux clients -->
                  <td style="width:33%;padding:6px 4px 6px 0;">
                    <div style="background:linear-gradient(145deg,#222831,#1a1d26);border-radius:10px;padding:12px 10px;border:1px solid #2d3139;">
                      <div style="font-size:10px;color:#9ea3b5;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">Nouveaux clients</div>
                      <div style="font-size:16px;color:#f5f5f5;font-weight:600;">{nv_clients}</div>
                    </div>
                  </td>
                  <!-- Devis proposés -->
                  <td style="width:33%;padding:6px 4px;">
                    <div style="background:linear-gradient(145deg,#222831,#1a1d26);border-radius:10px;padding:12px 10px;border:1px solid #2d3139;">
                      <div style="font-size:10px;color:#9ea3b5;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">Devis proposés</div>
                      <div style="font-size:16px;color:#f5f5f5;font-weight:600;">{dv_proposed}</div>
                    </div>
                  </td>
                  <!-- Meilleur CDP -->
                  <td style="width:33%;padding:6px 0 6px 4px;">
                    <div style="background:linear-gradient(145deg,#222831,#1a1d26);border-radius:10px;padding:12px 10px;border:1px solid #2d3139;">
                      <div style="font-size:10px;color:#9ea3b5;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">Meilleur CDP</div>
                      <div style="font-size:16px;color:#f5f5f5;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{top_cdp_name}</div>
                      <div style="font-size:16px;color:#f5f5f5;font-weight:500;">{top_cdp_val}</div>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Section 3: Forward quarters -->
          <tr>
            <td style="padding-top:4px;padding-bottom:20px;">
              <div style="color:#9ea3b5;font-size:12px;font-weight:500;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                3 • Confirmé – 4 prochains trimestres
              </div>
              <table width="100%" cellspacing="0" cellpadding="0" style="border-radius:10px;background-color:#222831;border:1px solid #2d3139;border-collapse:collapse;">
                <thead>
                  <tr>
                    <th align="left" style="padding:8px 12px;border-bottom:1px solid #2a2d35;color:#9ea3b5;font-size:12px;font-weight:500;">Trimestre</th>
                    <th align="right" style="padding:8px 12px;border-bottom:1px solid #2a2d35;color:#9ea3b5;font-size:12px;font-weight:500;">Valeur confirmée</th>
                    <th align="right" style="padding:8px 12px;border-bottom:1px solid #2a2d35;color:#9ea3b5;font-size:12px;font-weight:500;">Valeur en cours</th>
                    <th align="right" style="padding:8px 12px;border-bottom:1px solid #2a2d35;color:#9ea3b5;font-size:12px;font-weight:500;">Marge Provision</th>
                  </tr>
                </thead>
                <tbody>
                  {q_rows}
                </tbody>
              </table>
            </td>
          </tr>

          <!-- Section 4: CTA -->
          <tr>
            <td style="padding-top:4px;padding-bottom:20px;">
              <div style="color:#9ea3b5;font-size:12px;font-weight:500;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                4 • Rapport complet
              </div>
              <table role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <a href="{dropbox_url}" target="_blank" style="display:inline-block;background:#222831;color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;padding:10px 20px;border-radius:8px;border:2px solid #59a52c;">
                      Ouvrir le rapport complet
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer: définitions des indicateurs -->
          <tr>
            <td style="padding-top:16px;border-top:1px solid #2d3139;">
              <div style="color:#b4b9c6;font-size:11px;line-height:1.6;">
                <strong style="color:#e2e5eb;">Définitions :</strong><br/>
                Section 1 – Cette semaine : opérations, valeur et nombre de clients basés sur Date_opération entre ce lundi et ce dimanche (PDV_DEVIS).<br/>
                Section 2 – Résumé de la semaine : Nouveaux clients = clients distincts avec Date_Demande dans la semaine analysée ; Devis proposés = somme PDV_DEVIS pour ces demandes ; Meilleur CDP = chargé avec la plus haute somme PDV_DEVIS proposée sur la semaine.<br/>
                Section 3 – Confirmé, 4 prochains trimestres : Valeur confirmée = somme PDV_DEVIS_CONFIRME pour les devis confirmés dont Date_opération est dans le trimestre ; Valeur en cours = somme PDV_DEVIS pour les devis \"EN COURS\" dont Date_opération est dans le trimestre ; Marge Provision = somme MARGE_FINAL_EVENTS rapportée à la valeur confirmée du trimestre.
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# Email sending (Resend)
# ---------------------------------------------------------------------------


def send_email(
    subject: str,
    html: str,
    api_key: str,
    email_from: str,
    recipient: str,
) -> None:
    url = "https://api.resend.com/emails"

    payload = {
        "from": email_from,
        "to": [recipient],
        "subject": subject,
        "html": html,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info("Sending email via Resend to %s", recipient)
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)

    if not resp.ok:
        logger.error("Email sending failed: %s - %s", resp.status_code, resp.text)
        raise RuntimeError(f"Resend API error: {resp.status_code} {resp.text}")

    logger.info("Email sent successfully. Response: %s", resp.text)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()  # silently loads .env if exists

    setup_logging()
    logger.info("Starting Evolution2 weekly report generation.")

    # Ensure dirs
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Env vars
    api_key = os.getenv("RESEND_API_KEY")
    email_from = os.getenv("EMAIL_FROM")
    dropbox_url = os.getenv("DROPBOX_REPORT_URL")
    recipient_email = os.getenv("RECIPIENT_EMAIL")

    missing_env = [name for name, val in [
        ("RESEND_API_KEY", api_key),
        ("EMAIL_FROM", email_from),
        ("DROPBOX_REPORT_URL", dropbox_url),
        ("RECIPIENT_EMAIL", recipient_email),
    ] if not val]

    if missing_env:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing_env)
        )

    # Load data
    df = load_excel_data()
    confirmed_df = filter_confirmed(df)

    # Week window (last complete Mon–Sun)
    week_window = get_last_complete_week(PARIS_TZ)

    # Snapshot diff for Valeur confirmée (nouvelle) & Meilleur CDP
    prev_snapshot = load_previous_snapshot()
    newly_confirmed_rows, newly_confirmed_value, top_cdp, top_cdp_value = compute_newly_confirmed(
        confirmed_df, prev_snapshot
    )

    # Weekly KPIs
    kpis = compute_weekly_kpis(
        df=df,
        confirmed_df=confirmed_df,
        newly_confirmed_rows=newly_confirmed_rows,
        newly_confirmed_value=newly_confirmed_value,
        top_cdp=top_cdp,
        top_cdp_value=top_cdp_value,
        week_window=week_window,
    )

    # Forward quarters
    quarters = compute_forward_quarters(df, confirmed_df)

    # 'Cette semaine' metrics (current week, Date_opération)
    this_week_ops_count, this_week_ops_value, this_week_clients = compute_this_week_metrics(
        df, PARIS_TZ
    )

    # Update history & snapshot
    save_weekly_history(kpis)
    save_current_snapshot(confirmed_df)

    # Email
    subject = (
        "Résumé hebdomadaire – Evolution2 – "
        f"Semaine du {kpis.week.start.strftime('%d/%m/%Y')}"
    )
    this_week = get_this_week(PARIS_TZ)
    this_week_date_range = f"{this_week.start.strftime('%d/%m/%Y')} → {this_week.end.strftime('%d/%m/%Y')}"
    resume_week_date_range = f"{kpis.week.start.strftime('%d/%m/%Y')} → {kpis.week.end.strftime('%d/%m/%Y')}"

    html = build_email_html(
        kpis,
        quarters,
        dropbox_url=dropbox_url,
        this_week_ops_count=this_week_ops_count,
        this_week_ops_value=this_week_ops_value,
        this_week_clients=this_week_clients,
        this_week_date_range=this_week_date_range,
        resume_week_date_range=resume_week_date_range,
    )

    send_email(
        subject=subject,
        html=html,
        api_key=api_key,
        email_from=email_from,
        recipient=recipient_email,
    )

    # Console output
    print(f"Week analysed: {kpis.week.start} → {kpis.week.end}")
    print(f"Nouveaux clients (semaine analysée): {kpis.new_clients}")
    print(f"Devis proposés (semaine analysée): {kpis.proposed_value:.2f}")
    print(f"Valeur confirmée (nouvelle): {kpis.newly_confirmed_value:.2f}")
    print(f"Top CDP (nouveaux confirmés): {kpis.top_cdp or 'N/A'} ({kpis.top_cdp_value:.2f})")
    print(f"Cette semaine (Date_opération) – opérations: {this_week_ops_count}, valeur: {this_week_ops_value:.2f}, clients: {this_week_clients}")
    print(f"Email sent to: {recipient_email}")

    logger.info("Evolution2 weekly report completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Last‑resort logging
        setup_logging()
        logger.exception("Fatal error in evo2_weekly_report: %s", exc)
        raise


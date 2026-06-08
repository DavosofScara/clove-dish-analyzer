from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional

import pandas as pd

from .config import (
    EXCEL_PATH,
    EXCEL_SHEET_NAME,
    MARGE_REELLE_SHEET_NAME,
    CLIENT_DB_PATH,
    CLIENT_DB_SHEET_NAME,
)
logger = logging.getLogger(__name__)


def parse_excel_date(value) -> pd.Timestamp | pd.NaT:
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (int, float)):
        try:
            return pd.to_datetime(value, unit="d", origin="1899-12-30")
        except Exception:
            return pd.NaT
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return pd.NaT
        try:
            return pd.to_datetime(s, dayfirst=True, errors="coerce")
        except Exception:
            return pd.NaT
    if isinstance(value, (datetime, pd.Timestamp, date)):
        return pd.to_datetime(value)
    return pd.NaT


def coerce_number(value) -> float | None:
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
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
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


def normalize_key(value: str) -> str:
    s = str(value or "")
    s = " ".join(s.strip().upper().split())
    return s


def get_ci_column(df: pd.DataFrame, logical_name: str) -> Optional[str]:
    lower_map = {c.lower(): c for c in df.columns}
    return lower_map.get(logical_name.lower())


def load_excel_data() -> pd.DataFrame:
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel file not found: {EXCEL_PATH}")

    logger.info("Loading Excel data from %s", EXCEL_PATH)
    df = pd.read_excel(
        EXCEL_PATH,
        sheet_name=EXCEL_SHEET_NAME,
        engine="openpyxl",
        dtype=object,
    )

    if df.empty:
        logger.warning("Excel sheet '%s' is empty.", EXCEL_SHEET_NAME)

    for col_name in ["DEVIS_ID", "CLIENT_ID", "CDP"]:
        actual = get_ci_column(df, col_name)
        if actual:
            df[actual] = normalize_str_series(df[actual])
        else:
            logger.warning("Column %s not found in sheet.", col_name)

    for col_name in ["Date_Demande", "Date_opération"]:
        actual = get_ci_column(df, col_name)
        if actual:
            df[actual] = df[actual].apply(parse_excel_date)
        else:
            logger.warning("Date column %s not found in sheet.", col_name)

    for col_name in ["PDV_DEVIS", "PDV_DEVIS_CONFIRME", "MARGE_FINAL_EVENTS"]:
        actual = get_ci_column(df, col_name)
        if actual:
            df[actual] = df[actual].apply(coerce_number)
        else:
            logger.warning("Amount column %s not found in sheet.", col_name)

    confirme_col = get_ci_column(df, "CONFIRME")
    if confirme_col:
        df[confirme_col] = (
            normalize_str_series(df[confirme_col])
            .str.upper()
        )

    return df


def _resolve_column(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """Return first matching column (case-insensitive) from candidates."""
    for name in candidates:
        col = get_ci_column(df, name)
        if col:
            return col
    return None


def _is_truthy_flag(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().upper() in {"TRUE", "OUI", "YES", "1", "VRAI"}


def load_marge_reelle_devis() -> pd.DataFrame:
    """
    Hidden sheet Marge_Reelle_Devis: confirmed devis margins vs PDV.
    Returns logical column names: CDP, PDV_DEVIS, MARGE_EVENTS_REELLE, MARGE_EVENTS_FINAL_BUDGET.
    """
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel file not found: {EXCEL_PATH}")

    logger.info(
        "Loading margin sheet '%s' from %s", MARGE_REELLE_SHEET_NAME, EXCEL_PATH
    )
    try:
        df = pd.read_excel(
            EXCEL_PATH,
            sheet_name=MARGE_REELLE_SHEET_NAME,
            engine="openpyxl",
            dtype=object,
        )
    except ValueError as exc:
        if "Worksheet" in str(exc) or "sheet" in str(exc).lower():
            import openpyxl

            wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
            available = ", ".join(repr(s) for s in wb.sheetnames)
            wb.close()
            raise ValueError(
                f"Worksheet '{MARGE_REELLE_SHEET_NAME}' not found in {EXCEL_PATH}. "
                f"Available sheets: {available}"
            ) from exc
        raise

    column_map = {
        "CDP": _resolve_column(df, "CDP"),
        "PDV_DEVIS": _resolve_column(df, "PDV_DEVIS", "PDV_DEVIS_CONFIRME"),
        "MARGE_EVENTS_REELLE": _resolve_column(
            df, "MARGE_EVENTS_REELLE", "MARGE_EVENTS_REEL"
        ),
        "MARGE_EVENTS_FINAL_BUDGET": _resolve_column(
            df, "MARGE_EVENTS_FINAL_BUDGET", "MARGE EVENTS FINAL BUDGET"
        ),
    }
    missing = [k for k, v in column_map.items() if not v]
    if missing:
        cols = ", ".join(str(c) for c in df.columns)
        raise ValueError(
            f"Required column(s) {missing} missing on sheet {MARGE_REELLE_SHEET_NAME}. "
            f"Found: {cols}"
        )

    out = df[[column_map[k] for k in column_map]].copy()
    out.columns = list(column_map.keys())

    out["CDP"] = normalize_str_series(out["CDP"])
    for col in ("PDV_DEVIS", "MARGE_EVENTS_REELLE", "MARGE_EVENTS_FINAL_BUDGET"):
        out[col] = out[col].apply(coerce_number)

    valide_col = _resolve_column(df, "ALL_LINES_VALIDE", "ALL LINES VALIDE")
    before_valide = len(out)
    if valide_col:
        mask = df[valide_col].map(_is_truthy_flag)
        out = out[mask].copy()
        logger.info(
            "Marge_Reelle_Devis: kept %d / %d rows with ALL_LINES_VALIDE = True",
            len(out),
            before_valide,
        )
    else:
        logger.warning(
            "ALL_LINES_VALIDE column missing on %s; no line-level validation filter applied",
            MARGE_REELLE_SHEET_NAME,
        )

    out = out[out["CDP"].astype(str).str.strip() != ""]
    out = out[out["PDV_DEVIS"].fillna(0) > 0]

    logger.info(
        "Marge_Reelle_Devis: %d rows, %d distinct CDPs after filters",
        len(out),
        out["CDP"].nunique(),
    )
    return out


def load_client_database() -> pd.DataFrame:
    if not CLIENT_DB_PATH.exists():
        raise FileNotFoundError(f"Client database file not found: {CLIENT_DB_PATH}")

    logger.info("Loading client database from %s", CLIENT_DB_PATH)
    df = pd.read_excel(
        CLIENT_DB_PATH,
        sheet_name=CLIENT_DB_SHEET_NAME,
        engine="openpyxl",
        dtype=object,
    )

    rename_map = {
        "NOM CLIENT": "NOM_CLIENT",
        "NOM.AGENT": "NOM_AGENT",
        "TYPE_DE_CLIENT": "TYPE_DE_CLIENT",
        "Date_opération": "DATE_OPERATION",
        "Nb_Devis": "NB_DEVIS",
        "DATE CONFIRME": "DATE_CONFIRME_CLIENT",
        "DATE CONFIRMÉ": "DATE_CONFIRME_CLIENT",
        "DATE_CONFIRME": "DATE_CONFIRME_CLIENT",
    }
    df = df.rename(columns=rename_map)

    for col_name in ["NOM_CLIENT", "NOM_AGENT", "TYPE_DE_CLIENT"]:
        if col_name in df.columns:
            df[col_name] = normalize_str_series(df[col_name])

    if "DATE_OPERATION" in df.columns:
        df["DATE_OPERATION"] = df["DATE_OPERATION"].apply(parse_excel_date)

    if "DATE_CONFIRME_CLIENT" in df.columns:
        df["DATE_CONFIRME_CLIENT"] = df["DATE_CONFIRME_CLIENT"].apply(parse_excel_date)

    return df


def augment_client_key(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``client_key`` = normalize(NOM_CLIENT)|normalize(NOM_AGENT) (same rule as extract merge)."""
    if "NOM_CLIENT" not in df.columns or "NOM_AGENT" not in df.columns:
        raise ValueError("augment_client_key requires NOM_CLIENT and NOM_AGENT.")
    out = df.copy()
    out["client_key"] = (
        out["NOM_CLIENT"].astype(str).map(normalize_key)
        + "|"
        + out["NOM_AGENT"].astype(str).map(normalize_key)
    )
    return out


def enrich_with_client_type(extract_df: pd.DataFrame, client_df: pd.DataFrame) -> pd.DataFrame:
    if "NOM_CLIENT" not in extract_df.columns or "NOM_AGENT" not in extract_df.columns:
        raise ValueError("extract_devis must include NOM_CLIENT and NOM_AGENT.")
    if "NOM_CLIENT" not in client_df.columns or "NOM_AGENT" not in client_df.columns:
        raise ValueError("client database must include NOM_CLIENT and NOM_AGENT.")

    extract_df = augment_client_key(extract_df.copy())
    client_df = augment_client_key(client_df.copy())

    def pick_row(group: pd.DataFrame) -> pd.Series:
        if "DATE_OPERATION" in group.columns and group["DATE_OPERATION"].notna().any():
            row = group.sort_values("DATE_OPERATION", ascending=False).iloc[0]
            if pd.notna(row.get("TYPE_DE_CLIENT")) and str(row.get("TYPE_DE_CLIENT")).strip():
                return row
        for _, r in group.iterrows():
            if pd.notna(r.get("TYPE_DE_CLIENT")) and str(r.get("TYPE_DE_CLIENT")).strip():
                return r
        return group.iloc[0]

    lookup = (
        client_df.groupby("client_key", as_index=False)
        .apply(pick_row)
        .reset_index(drop=True)
    )
    lookup = lookup[["client_key", "TYPE_DE_CLIENT"]].copy()

    # DATE CONFIRME may live on a different row than pick_row (TYPE / DATE_OPERATION) — merge max per key.
    if "DATE_CONFIRME_CLIENT" in client_df.columns:
        dc_agg = (
            client_df.groupby("client_key", as_index=False)["DATE_CONFIRME_CLIENT"]
            .max()
        )
        lookup = lookup.merge(dc_agg, on="client_key", how="left")
    else:
        lookup["DATE_CONFIRME_CLIENT"] = pd.NaT

    merged = extract_df.merge(lookup, on="client_key", how="left")
    merged["TYPE_DE_CLIENT"] = merged["TYPE_DE_CLIENT"].fillna("INCONNU")
    if "DATE_CONFIRME_CLIENT" not in merged.columns:
        merged["DATE_CONFIRME_CLIENT"] = pd.NaT

    total = len(merged)
    matched = int((merged["TYPE_DE_CLIENT"] != "INCONNU").sum())
    unmatched = total - matched
    pct_unmatched = (unmatched / total) if total else 0.0
    logger.info("Client type enrichment: total=%d matched=%d unmatched=%d (%.1f%%)",
                total, matched, unmatched, pct_unmatched * 100)

    return merged

"""
Extract legacy DOSSIER TRAVAIL (recap) and pre-V13 TB dossiers (DEVIS) for historical reporting.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

TRAVAIL_NAME_RE = re.compile(r"DOSSIER TRAVAIL", re.IGNORECASE)
TB_VERSION_RE = re.compile(r"TBv(\d+)", re.IGNORECASE)
MAX_TB_VERSION = 12


def _excel_engine(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".xls":
        return "xlrd"
    if ext in {".xlsx", ".xlsm"}:
        return "openpyxl"
    return None


def _is_travail_file(path: Path) -> bool:
    return _excel_engine(path) is not None and bool(TRAVAIL_NAME_RE.search(path.name))


def _tb_version(path: Path) -> int | None:
    m = TB_VERSION_RE.search(path.name)
    return int(m.group(1)) if m else None


def read_recap_sheet(filepath: Path) -> pd.DataFrame:
    """Read recap tab using the original _get_data row/header convention."""
    engine = _excel_engine(filepath)
    df = pd.read_excel(filepath, sheet_name="recap", header=None, engine=engine)
    if df.empty or len(df) < 8:
        return pd.DataFrame()

    new_header = df.iloc[4].tolist()
    body = df.iloc[3:].copy()
    body.columns = new_header
    body.columns = body.columns.map(lambda c: str(c).strip() if c is not None else "")

    body["USER"] = filepath.parent.name
    body["Source File"] = filepath.name
    body["source_path"] = str(filepath)
    body["source_format"] = "recap"

    body = body.iloc[6:].reset_index(drop=True)
    body = body.dropna(how="all")
    return body


def extract_dossier_travail(root: Path) -> pd.DataFrame:
    """Walk *root* and concatenate all DOSSIER TRAVAIL recap sheets."""
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    file_count = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _is_travail_file(path):
            continue
        file_count += 1
        try:
            df = read_recap_sheet(path)
            if not df.empty:
                frames.append(df)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            logger.warning("Skipping %s: %s", path, exc)

    if errors:
        logger.info("Recap extract: %d files skipped due to errors", len(errors))

    if not frames:
        logger.warning("No recap data extracted from %s (%d files scanned)", root, file_count)
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info(
        "Recap extract: %d files, %d rows from %s",
        file_count,
        len(combined),
        root,
    )
    return combined


def read_devis_sheet(filepath: Path) -> pd.DataFrame:
    """Read DEVIS tab using extract_devis.py convention."""
    header = pd.read_excel(
        filepath, sheet_name="DEVIS", skiprows=23, nrows=0, engine="openpyxl"
    ).columns.tolist()
    df = pd.read_excel(
        filepath,
        sheet_name="DEVIS",
        skiprows=24,
        nrows=463,
        header=None,
        engine="openpyxl",
    )
    if df.empty:
        return pd.DataFrame()

    df.columns = [str(c) for c in header]
    if "DEVIS_ID" in df.columns:
        df = df[df["DEVIS_ID"].notna()].copy()
    df["Source File"] = filepath.name
    df["source_path"] = str(filepath)
    df["source_format"] = "devis"
    return df


def extract_dossier_tb_pre_v13(root: Path) -> pd.DataFrame:
    """Extract DEVIS rows from TBv8–TBv12 dossier files under *root*."""
    frames: list[pd.DataFrame] = []
    seen_paths: set[str] = set()

    for path in sorted(root.rglob("*.xlsm")):
        name_upper = path.name.upper()
        if "DOSSIER_CA" not in name_upper and "TOSSIER_CA" not in name_upper:
            continue
        ver = _tb_version(path)
        if ver is None or ver > MAX_TB_VERSION:
            continue
        key = str(path.resolve())
        if key in seen_paths:
            continue
        seen_paths.add(key)
        try:
            df = read_devis_sheet(path)
            if not df.empty:
                frames.append(df)
        except Exception as exc:
            logger.warning("Skipping TB dossier %s: %s", path, exc)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info("TB pre-v13 extract: %d files, %d rows", len(frames), len(combined))
    return combined

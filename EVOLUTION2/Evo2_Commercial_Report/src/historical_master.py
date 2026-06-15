"""
Load and merge historical CA extracts for prior-season YoY chart lines.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from .config import ETE_2025_DEFINITIVE_CSV, ETE_2025_END, ETE_2025_EXPORT_END, ETE_2025_START
from .load_data import coerce_number
from .periods import SeasonPeriod
from .status_norm import is_confirmed_exact

logger = logging.getLogger(__name__)

CANONICAL_COLUMNS = (
    "DEVIS_ID",
    "Date_opération",
    "CONFIRME",
    "PDV_DEVIS_CONFIRME",
    "CDP",
    "Source File",
    "source_format",
)

BUSINESS_KEY_COLS = ("Date_opération", "_amt_round", "_cdp_norm", "_client_norm")


def _recap_is_confirmed(val) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return str(val).strip().upper() == "C"


def _parse_date(series: pd.Series) -> pd.Series:
    """Parse French day-first dates from Excel and ISO dates from CSV exports."""
    if series.empty:
        return pd.to_datetime(series, errors="coerce")
    as_str = series.astype(str).str.strip()
    iso_like = as_str.str.match(r"^\d{4}-\d{2}-\d{2}")
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if iso_like.any():
        out.loc[iso_like] = pd.to_datetime(as_str.loc[iso_like], errors="coerce")
    if (~iso_like).any():
        out.loc[~iso_like] = pd.to_datetime(as_str.loc[~iso_like], errors="coerce", dayfirst=True)
    return out


def _amount(val) -> float:
    v = coerce_number(val)
    return float(v) if v is not None else 0.0


def _norm_cdp(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip().upper()


def _norm_client(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip().upper()
    return "" if s in ("", "NAN", "0", "NONE") else s


def _source_file_rank(name: str) -> tuple:
    """
    Prefer canonical workbook name, then shortest filename (usually latest snapshot).
    """
    n = str(name).strip().upper()
    if n == "DOSSIER TRAVAIL CA.XLS":
        return (0, 0, n)
    return (1, len(n), n)


def _synthetic_devis_id(date_op, cdp, amount, client: str = "") -> str:
    key = "|".join(
        str(x)
        for x in (
            pd.Timestamp(date_op).date() if pd.notna(date_op) else "",
            _norm_cdp(cdp),
            round(float(amount), 2),
            _norm_client(client),
        )
    )
    return "RECAP_" + hashlib.md5(key.encode()).hexdigest()[:12]


def _client_column(df: pd.DataFrame) -> str | None:
    for col in ("Clients", "Client final", "NOM_CLIENT"):
        if col in df.columns:
            return col
    return None


def dedupe_recap_snapshots(recap_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Collapse duplicate events recorded in multiple dated DOSSIER TRAVAIL snapshots.

    Returns (deduped recap dataframe, number of rows removed).
    """
    if recap_df.empty:
        return recap_df, 0

    date_col = "Date opération" if "Date opération" in recap_df.columns else "Date_opération"
    amt_col = "Prix de vente final" if "Prix de vente final" in recap_df.columns else "PDV_DEVIS"
    conf_col = "EC/C/A" if "EC/C/A" in recap_df.columns else "CONFIRME"
    client_col = _client_column(recap_df)

    df = recap_df.copy()
    df["_date"] = _parse_date(df[date_col])
    df["_amt"] = df[amt_col].map(_amount) if amt_col in df.columns else 0.0
    df["_cdp"] = df["CDP"].map(_norm_cdp) if "CDP" in df.columns else ""
    df["_client"] = df[client_col].map(_norm_client) if client_col else ""
    df["_conf"] = df[conf_col].map(_recap_is_confirmed) if conf_col in df.columns else True

    in_season = (
        df["_conf"]
        & df["_date"].notna()
        & (df["_date"] >= pd.Timestamp(ETE_2025_START))
        & (df["_date"] <= pd.Timestamp(ETE_2025_END))
        & (df["_amt"] > 0)
    )
    if not in_season.any():
        return recap_df, 0

    ete = df.loc[in_season].copy()
    other = df.loc[~in_season].copy()
    before = len(ete)

    ete["_rank"] = ete["Source File"].map(_source_file_rank) if "Source File" in ete.columns else (0,)
    ete = ete.sort_values("_rank")
    ete = ete.drop_duplicates(subset=["_date", "_amt", "_cdp", "_client"], keep="first")

    removed = before - len(ete)
    ete = ete.drop(columns=["_date", "_amt", "_cdp", "_client", "_conf", "_rank"], errors="ignore")
    other = other.drop(columns=["_date", "_amt", "_cdp", "_client", "_conf"], errors="ignore")

    return pd.concat([other, ete], ignore_index=True), removed


def normalize_recap_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    date_col = "Date opération" if "Date opération" in df.columns else "Date_opération"
    amt_col = "Prix de vente final" if "Prix de vente final" in df.columns else "PDV_DEVIS"
    conf_col = "EC/C/A" if "EC/C/A" in df.columns else "CONFIRME"
    cdp_col = "CDP" if "CDP" in df.columns else None
    client_col = _client_column(df)

    out = pd.DataFrame()
    out["Date_opération"] = _parse_date(df[date_col])
    out["PDV_DEVIS_CONFIRME"] = df[amt_col].map(_amount) if amt_col in df.columns else 0.0
    out["CONFIRME"] = df[conf_col].map(lambda v: "CONFIRMÉ" if _recap_is_confirmed(v) else str(v))
    out["CDP"] = df[cdp_col] if cdp_col and cdp_col in df.columns else ""
    out["Source File"] = df.get("Source File", "")
    out["source_format"] = "recap"
    clients = df[client_col].map(_norm_client) if client_col else pd.Series([""] * len(df))
    out["DEVIS_ID"] = [
        _synthetic_devis_id(out.iloc[i]["Date_opération"], out.iloc[i]["CDP"], out.iloc[i]["PDV_DEVIS_CONFIRME"], clients.iloc[i])
        for i in range(len(out))
    ]
    return out[list(CANONICAL_COLUMNS)]


def normalize_devis_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    out = pd.DataFrame()
    out["DEVIS_ID"] = df["DEVIS_ID"].astype(str).str.strip() if "DEVIS_ID" in df.columns else ""
    out["Date_opération"] = _parse_date(df["Date_opération"]) if "Date_opération" in df.columns else pd.NaT
    pdv_col = "PDV_DEVIS_CONFIRME" if "PDV_DEVIS_CONFIRME" in df.columns else "PDV_DEVIS"
    out["PDV_DEVIS_CONFIRME"] = df[pdv_col].map(_amount) if pdv_col in df.columns else 0.0
    out["CONFIRME"] = df["CONFIRME"] if "CONFIRME" in df.columns else ""
    out["CDP"] = df["CDP"] if "CDP" in df.columns else ""
    out["Source File"] = df.get("Source File", "")
    out["source_format"] = "devis"
    return out[list(CANONICAL_COLUMNS)]


def _prepare_tb_pre_v13(tb_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pre-V13 TB rows for merge/export: CONFIRME status only, one row per DEVIS_ID.

    Pre-V13 DEVIS sheets expose ``PDV_DEVIS`` (not ``PDV_DEVIS_CONFIRME``); amounts are
    only included when ``CONFIRME`` is CONFIRMÉ / CONFIRME.
    """
    if tb_df.empty:
        return tb_df

    if "CONFIRME" not in tb_df.columns:
        logger.warning("TB extract missing CONFIRME column; skipping TB overlay")
        return tb_df.iloc[0:0]

    out = tb_df.loc[tb_df["CONFIRME"].map(is_confirmed_exact)].copy()
    if out.empty or "DEVIS_ID" not in out.columns:
        return out

    out["_devis_id"] = out["DEVIS_ID"].astype(str).str.strip()
    out = out.loc[out["_devis_id"].ne("") & out["_devis_id"].ne("nan")].copy()
    if out.empty:
        return out.iloc[0:0]

    source = out["Source File"] if "Source File" in out.columns else pd.Series("", index=out.index)
    out["_tb_ver"] = source.astype(str).str.extract(r"TBv(\d+)", flags=re.I)[0].astype(float).fillna(0)
    out = out.sort_values(["_devis_id", "_tb_ver", "Source File"], na_position="last")
    before = len(out)
    out = out.drop_duplicates("_devis_id", keep="last")
    if before > len(out):
        logger.info(
            "TB pre-v13: %d duplicate CONFIRME DEVIS_ID rows collapsed to %d",
            before,
            len(out),
        )
    return out.drop(columns=["_devis_id", "_tb_ver"], errors="ignore")


def _filter_ete_2025_confirmed(
    df: pd.DataFrame,
    *,
    end: date | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    end_ts = pd.Timestamp(end or ETE_2025_END)
    m = (
        df["Date_opération"].notna()
        & (df["Date_opération"] >= pd.Timestamp(ETE_2025_START))
        & (df["Date_opération"] <= end_ts)
        & df["CONFIRME"].map(is_confirmed_exact)
        & (df["PDV_DEVIS_CONFIRME"] > 0)
    )
    return df.loc[m].copy()


def _recap_client_value(row: pd.Series, client_col: str | None) -> str:
    if not client_col or client_col not in row.index:
        return ""
    val = row.get(client_col)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        val = ""
    text = str(val).strip()
    if text.lower() in ("", "nan", "none"):
        if "Client final" in row.index:
            alt = row.get("Client final")
            if alt is not None and not (isinstance(alt, float) and pd.isna(alt)):
                text = str(alt).strip()
    return "" if text.lower() in ("", "nan", "none") else text


def _recap_detail_rows(recap_deduped: pd.DataFrame, *, end: date | None = None) -> pd.DataFrame:
    """Confirmed ÉTÉ recap rows with agent/client for export."""
    if recap_deduped.empty:
        return pd.DataFrame(columns=["DEVIS_ID", "Agent", "Client"])

    date_col = "Date opération" if "Date opération" in recap_deduped.columns else "Date_opération"
    amt_col = "Prix de vente final" if "Prix de vente final" in recap_deduped.columns else "PDV_DEVIS"
    conf_col = "EC/C/A" if "EC/C/A" in recap_deduped.columns else "CONFIRME"
    client_col = _client_column(recap_deduped)
    end_ts = pd.Timestamp(end or ETE_2025_END)

    rows: list[dict] = []
    for _, row in recap_deduped.iterrows():
        date_op = _parse_date(pd.Series([row.get(date_col)])).iloc[0]
        amount = _amount(row.get(amt_col))
        if not _recap_is_confirmed(row.get(conf_col)):
            continue
        if pd.isna(date_op) or date_op < pd.Timestamp(ETE_2025_START) or date_op > end_ts or amount <= 0:
            continue
        client = _recap_client_value(row, client_col)
        cdp = row.get("CDP", "")
        agent = "" if cdp is None or (isinstance(cdp, float) and pd.isna(cdp)) else str(cdp).strip()
        rows.append(
            {
                "DEVIS_ID": _synthetic_devis_id(date_op, cdp, amount, client),
                "Agent": agent,
                "Client": client,
                "Source": "recap",
                "Fichier source": "" if row.get("Source File") is None else str(row.get("Source File")).strip(),
                "Chemin source": "" if row.get("source_path") is None else str(row.get("source_path")).strip(),
                "Dossier CDP": "" if row.get("USER") is None else str(row.get("USER")).strip(),
            }
        )
    return pd.DataFrame(rows)


def _devis_detail_rows(tb_df: pd.DataFrame, *, end: date | None = None) -> pd.DataFrame:
    """Confirmed ÉTÉ DEVIS rows with agent/client for export."""
    if tb_df.empty:
        return pd.DataFrame(columns=["DEVIS_ID", "Agent", "Client"])

    end_ts = pd.Timestamp(end or ETE_2025_END)
    pdv_col = "PDV_DEVIS_CONFIRME" if "PDV_DEVIS_CONFIRME" in tb_df.columns else "PDV_DEVIS"
    rows: list[dict] = []
    for _, row in tb_df.iterrows():
        date_op = _parse_date(pd.Series([row.get("Date_opération")])).iloc[0]
        amount = _amount(row.get(pdv_col))
        conf = row.get("CONFIRME", "")
        if not is_confirmed_exact(conf):
            continue
        if pd.isna(date_op) or date_op < pd.Timestamp(ETE_2025_START) or date_op > end_ts or amount <= 0:
            continue
        devis_id = str(row.get("DEVIS_ID", "")).strip()
        if not devis_id:
            continue
        agent = row.get("NOM_AGENT", row.get("CDP", ""))
        client = row.get("NOM_CLIENT", "")
        agent = "" if agent is None or (isinstance(agent, float) and pd.isna(agent)) else str(agent).strip()
        client = "" if client is None or (isinstance(client, float) and pd.isna(client)) else str(client).strip()
        rows.append(
            {
                "DEVIS_ID": devis_id,
                "Agent": agent,
                "Client": client,
                "Source": "TB pre-V13",
                "Fichier source": "" if row.get("Source File") is None else str(row.get("Source File")).strip(),
                "Chemin source": "" if row.get("source_path") is None else str(row.get("source_path")).strip(),
                "Dossier CDP": "",
            }
        )
    return pd.DataFrame(rows)


def build_ete_2025_export(recap_df: pd.DataFrame, tb_df: pd.DataFrame, *, end: date | None = None) -> pd.DataFrame:
    """
    Export-ready ÉTÉ 2025 confirmed CA with source metadata for spot-checking.
    Uses the same deduped merge as the definitive chart dataset.
    """
    export_end = end or ETE_2025_EXPORT_END
    export_columns = [
        "Agent",
        "Client",
        "Date d'opération",
        "Prix de vente final",
        "Source",
        "Fichier source",
        "Chemin source",
        "Dossier CDP",
        "DEVIS_ID",
    ]
    merged = merge_ete_2025_definitive(recap_df, tb_df)
    if merged.empty:
        return pd.DataFrame(columns=export_columns)

    merged = _filter_ete_2025_confirmed(merged, end=export_end)

    recap_deduped, _ = dedupe_recap_snapshots(recap_df)
    recap_lookup = _recap_detail_rows(recap_deduped, end=export_end).drop_duplicates("DEVIS_ID", keep="first")
    tb_prepared = _prepare_tb_pre_v13(tb_df)
    devis_lookup = _devis_detail_rows(tb_prepared, end=export_end).drop_duplicates("DEVIS_ID", keep="first")
    lookup = pd.concat([recap_lookup, devis_lookup], ignore_index=True).drop_duplicates("DEVIS_ID", keep="first")

    export = merged.merge(lookup, on="DEVIS_ID", how="left")
    # Fallback to merge metadata when lookup join misses (should be rare).
    if "Source File" in export.columns:
        export["Fichier source"] = export["Fichier source"].fillna(export["Source File"].astype(str))
    if "source_format" in export.columns:
        export["Source"] = export["Source"].fillna(
            export["source_format"].map({"recap": "recap", "devis": "TB pre-V13"})
        )
    export = export.sort_values(["Date_opération", "Client", "Agent"], na_position="last")
    return pd.DataFrame(
        {
            "Agent": export["Agent"].fillna(""),
            "Client": export["Client"].fillna(""),
            "Date d'opération": export["Date_opération"].dt.date,
            "Prix de vente final": export["PDV_DEVIS_CONFIRME"].round(2),
            "Source": export["Source"].fillna(""),
            "Fichier source": export["Fichier source"].fillna(""),
            "Chemin source": export["Chemin source"].fillna(""),
            "Dossier CDP": export["Dossier CDP"].fillna(""),
            "DEVIS_ID": export["DEVIS_ID"].fillna(""),
        }
    )


def save_ete_2025_export_xlsx(
    recap_df: pd.DataFrame,
    tb_df: pd.DataFrame,
    path: Path,
    *,
    end: date | None = None,
) -> Path:
    export = build_ete_2025_export(recap_df, tb_df, end=end)
    path.parent.mkdir(parents=True, exist_ok=True)
    export.to_excel(path, index=False, sheet_name="ÉTÉ 2025")
    logger.info(
        "Wrote ÉTÉ 2025 export %s (%d rows, €%.0f)",
        path,
        len(export),
        export["Prix de vente final"].sum() if not export.empty else 0,
    )
    return path


def _with_business_key(df: pd.DataFrame, *, client_default: str = "") -> pd.DataFrame:
    out = df.copy()
    out["_amt_round"] = out["PDV_DEVIS_CONFIRME"].round(2)
    out["_cdp_norm"] = out["CDP"].map(_norm_cdp)
    out["_client_norm"] = client_default
    return out


def _dedupe_business_key(df: pd.DataFrame, *, prefer_recap: bool = True) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if prefer_recap and "source_format" in out.columns:
        out["_src_rank"] = out["source_format"].map({"recap": 0, "devis": 1}).fillna(2)
        out = out.sort_values("_src_rank")
    out = out.drop_duplicates(subset=list(BUSINESS_KEY_COLS), keep="first")
    return out.drop(columns=["_amt_round", "_cdp_norm", "_client_norm", "_src_rank"], errors="ignore")


def merge_ete_2025_definitive(recap_df: pd.DataFrame, tb_df: pd.DataFrame) -> pd.DataFrame:
    """Merge recap (primary) + pre-V13 TB rows for ÉTÉ 2025, deduped."""
    recap_deduped, recap_removed = dedupe_recap_snapshots(recap_df)
    if recap_removed:
        logger.info("Recap snapshot dedupe removed %d duplicate ÉTÉ 2025 rows", recap_removed)

    recap_norm = _filter_ete_2025_confirmed(normalize_recap_rows(recap_deduped))
    tb_prepared = _prepare_tb_pre_v13(tb_df)
    tb_norm = _filter_ete_2025_confirmed(normalize_devis_rows(tb_prepared))

    recap_bk = _with_business_key(recap_norm)
    recap_keys = set(map(tuple, recap_bk[list(BUSINESS_KEY_COLS)].itertuples(index=False, name=None)))

    tb_bk = _with_business_key(tb_norm)
    tb_bk["_key_tuple"] = list(map(tuple, tb_bk[list(BUSINESS_KEY_COLS)].itertuples(index=False, name=None)))
    tb_extra = tb_norm.loc[~tb_bk["_key_tuple"].isin(recap_keys)].copy()

    merged = pd.concat([recap_norm, tb_extra], ignore_index=True)
    merged = _dedupe_business_key(_with_business_key(merged), prefer_recap=True)

    logger.info(
        "ÉTÉ 2025 definitive: recap=%d, tb_extra=%d, merged=%d, CA=%.0f",
        len(recap_norm),
        len(tb_extra),
        len(merged),
        merged["PDV_DEVIS_CONFIRME"].sum(),
    )
    return merged


def save_ete_2025_definitive(df: pd.DataFrame, path: Path | None = None) -> Path:
    out = path or ETE_2025_DEFINITIVE_CSV
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    logger.info("Wrote %s (%d rows)", out, len(df))
    return out


def load_ete_2025_definitive(path: Path | None = None) -> pd.DataFrame:
    p = path or ETE_2025_DEFINITIVE_CSV
    if not p.exists():
        logger.warning("ÉTÉ 2025 definitive file missing: %s", p)
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    df = pd.read_csv(p, low_memory=False)
    df["Date_opération"] = _parse_date(df["Date_opération"])
    df["PDV_DEVIS_CONFIRME"] = df["PDV_DEVIS_CONFIRME"].map(_amount)
    return df


def _find_date_operation_column(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        norm = str(c).strip().lower().replace("é", "e")
        if norm == "date_operation":
            return c
    for c in df.columns:
        if "op" in str(c).lower() and "date" in str(c).lower():
            return c
    return None


def augment_df_for_prior_season(df: pd.DataFrame, prior: SeasonPeriod) -> pd.DataFrame:
    """
    For ÉTÉ 25 prior line, replace V13 rows with the definitive historical extract.
    Other prior seasons fall back to *df* (V13).
    """
    if prior.label != "ÉTÉ 25":
        return df

    hist = load_ete_2025_definitive()
    if hist.empty:
        logger.warning("No ÉTÉ 2025 definitive data; prior season uses V13 only")
        return df

    date_col = _find_date_operation_column(df)
    if date_col:
        d = _parse_date(df[date_col])
        outside = d.isna() | (d < pd.Timestamp(prior.start)) | (d > pd.Timestamp(prior.end))
        base = df.loc[outside].copy()
    else:
        base = df.copy()

    return pd.concat([base, hist], ignore_index=True)


def summarize_ete_2025(df: pd.DataFrame) -> dict:
    """Monthly CA totals for validation logging."""
    if df.empty:
        return {}
    monthly = df.groupby(df["Date_opération"].dt.to_period("M"))["PDV_DEVIS_CONFIRME"].sum()
    return {str(k): float(v) for k, v in monthly.items()}


def analyze_duplicates(recap_df: pd.DataFrame, tb_df: pd.DataFrame) -> dict:
    """Compare totals under different dedupe strategies (for validation scripts)."""
    date_col = "Date opération" if "Date opération" in recap_df.columns else "Date_opération"
    conf_col = "EC/C/A" if "EC/C/A" in recap_df.columns else "CONFIRME"
    amt_col = "Prix de vente final" if "Prix de vente final" in recap_df.columns else "PDV_DEVIS"
    client_col = _client_column(recap_df)

    raw = recap_df.copy()
    raw["_date"] = _parse_date(raw[date_col])
    raw["_amt"] = raw[amt_col].map(_amount)
    raw["_cdp"] = raw["CDP"].map(_norm_cdp) if "CDP" in raw.columns else ""
    raw["_client"] = raw[client_col].map(_norm_client) if client_col else ""
    raw["_conf"] = raw[conf_col].map(_recap_is_confirmed)

    m = (
        raw["_conf"]
        & raw["_date"].notna()
        & (raw["_date"] >= pd.Timestamp(ETE_2025_START))
        & (raw["_date"] <= pd.Timestamp(ETE_2025_END))
        & (raw["_amt"] > 0)
    )
    ete = raw.loc[m]

    def _tot(sub: pd.DataFrame) -> float:
        return float(sub["_amt"].sum())

    ete_pref = ete.copy()
    if "Source File" in ete_pref.columns:
        ete_pref["_rank"] = ete_pref["Source File"].map(_source_file_rank)
        ete_pref = ete_pref.sort_values("_rank")
    strategies = {
        "raw_confirmed": _tot(ete),
        "dedupe_date_amt_cdp": _tot(ete.drop_duplicates(subset=["_date", "_amt", "_cdp"], keep="first")),
        "dedupe_date_amt_cdp_client": _tot(
            ete.drop_duplicates(subset=["_date", "_amt", "_cdp", "_client"], keep="first")
        ),
        "dedupe_with_file_preference": _tot(
            ete_pref.drop_duplicates(subset=["_date", "_amt", "_cdp", "_client"], keep="first")
        ),
        "merged_definitive": float(merge_ete_2025_definitive(recap_df, tb_df)["PDV_DEVIS_CONFIRME"].sum()),
    }
    return strategies

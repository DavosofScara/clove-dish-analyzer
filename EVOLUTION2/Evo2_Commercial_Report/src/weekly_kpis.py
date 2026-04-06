"""
Weekly and seasonal KPIs + provisional revenue (current and next season).

Definitions (locked):
- Confirmed: CONFIRMÉ or CONFIRME (after normalise) on column CONFIRME.
- Propositions envoyées (email label) — **week**: distinct CLIENT_ID with ≥1 row whose **Date_Demande** falls in the
  reference week (Mon–Sun ending last Sunday ≤ report date), regardless of CONFIRME / Date_opération.
  **Season** row: Date_opération in the full current season.
- Realised revenue (season row in email): sum PDV_DEVIS_CONFIRME on confirmed rows with Date_opération
  in the full calendar current season (same bounds as proposed dossiers season).
- Dossiers réalisés (saison): confirmed, Date_opération in report-to-date window
  (season start → min(report date, season end)).
- Dossiers confirmés (saison): distinct CLIENT_ID with ≥1 CONFIRMÉ row and Date_opération in the
  **full calendar current season** (proxy until a true “date confirmed” exists).
- Provisional CA (“potential” season revenue): (1) Sum PDV_DEVIS_CONFIRME on CONFIRMÉ rows with
  Date_opération in the full calendar season [start, end]. (2) Add pipeline: EN COURS rows with
  Date_opération from the day after min(week_end, season end) through season end; per CLIENT_ID,
  contribution = sum(PDV_DEVIS) / count(distinct DEVIS_ID). Here week_end is the Sunday end of the
  Mon–Sun week ending on the last Sunday ≤ ``as_of``, so the window updates as the season progresses.
- One dossier = one CLIENT_ID (distinct counts).

Week row: réalisés = confirmés (same window). Saison row: confirmés = full season; réalisés = report-to-date.

Realised revenue (week row): sum PDV_DEVIS_CONFIRME on confirmed rows with Date_opération in the week window.

Provisional revenue: full-season confirmed PDV + forward EN COURS add-on (see compute_ca_provisionnel).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .load_data import get_ci_column
from .periods import (
    SeasonPeriod,
    date_in_range,
    next_season_after,
    previous_completed_week,
    season_containing,
    season_window_for_metrics,
)
from .status_norm import is_cancelled_status, is_confirmed_exact, is_en_cours

logger = logging.getLogger(__name__)


def _to_float(x: Any) -> float:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("\u00a0", " ").replace("€", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


@dataclass
class WeeklyKpiResult:
    # Period labels
    week_start: date
    week_end: date
    current_season: SeasonPeriod
    next_season: SeasonPeriod
    season_metrics_end: date

    # Counts (unique CLIENT_ID)
    dossiers_realise_semaine: int
    dossiers_realise_saison: int
    dossiers_propose_semaine: int
    dossiers_propose_saison: int
    dossiers_confirme_semaine: int
    dossiers_confirme_saison: int

    # Realised revenue (€)
    ca_realise_semaine: float
    ca_realise_saison: float

    # CA provisionnel (€)
    ca_provisionnel_saison_cours: float
    ca_provisionnel_saison_suivante: float

    validation: Dict[str, Any] = field(default_factory=dict)


def _resolve_columns(df: pd.DataFrame) -> Dict[str, str]:
    out = {}
    for logical in (
        "CLIENT_ID",
        "DEVIS_ID",
        "Date_opération",
        "Date_Demande",
        "CONFIRME",
        "PDV_DEVIS",
        "PDV_DEVIS_CONFIRME",
    ):
        c = get_ci_column(df, logical)
        if not c:
            raise ValueError(f"Required column missing: {logical}")
        out[logical] = c
    return out


def _mask_period(df: pd.DataFrame, date_col: str, start: date, end: date) -> pd.Series:
    return df[date_col].apply(lambda d: date_in_range(d, start, end))


def _unique_clients_in_period(
    df: pd.DataFrame,
    cols: Dict[str, str],
    start: date,
    end: date,
    row_mask_extra: Optional[pd.Series] = None,
) -> int:
    date_col = cols["Date_opération"]
    client_col = cols["CLIENT_ID"]
    m = _mask_period(df, date_col, start, end)
    if row_mask_extra is not None:
        m = m & row_mask_extra
    sub = df.loc[m, client_col]
    s = sub.astype(str).str.strip()
    return int(s[s != ""].nunique())


def _confirmed_client_ids_in_period(
    df: pd.DataFrame,
    cols: Dict[str, str],
    start: date,
    end: date,
) -> set:
    """CLIENT_ID values with ≥1 CONFIRMÉ row and Date_opération in [start,end]."""
    date_col = cols["Date_opération"]
    conf_col = cols["CONFIRME"]
    client_col = cols["CLIENT_ID"]
    m = _mask_period(df, date_col, start, end) & df[conf_col].map(is_confirmed_exact)
    ids = df.loc[m, client_col].astype(str).str.strip()
    return set(ids[ids != ""].unique())


def _client_ids_with_date_operation_in_period(
    df: pd.DataFrame,
    cols: Dict[str, str],
    start: date,
    end: date,
) -> set:
    """
    Distinct non-empty CLIENT_ID with ≥1 row where Date_opération ∈ [start, end] inclusive.
    No filter on CONFIRME (CONFIRMÉ, EN COURS, ANNULE, etc. all count).
    """
    date_col = cols["Date_opération"]
    client_col = cols["CLIENT_ID"]
    m = _mask_period(df, date_col, start, end)
    sub = df.loc[m, client_col].astype(str).str.strip()
    return set(sub[sub != ""].unique())


def _client_ids_with_date_demande_in_period(
    df: pd.DataFrame,
    cols: Dict[str, str],
    start: date,
    end: date,
) -> set:
    """
    Distinct non-empty CLIENT_ID with ≥1 row where Date_Demande ∈ [start, end] inclusive.
    Used for “propositions envoyées (semaine)” — proposal/request date, not operation date.
    """
    date_col = cols["Date_Demande"]
    client_col = cols["CLIENT_ID"]
    m = _mask_period(df, date_col, start, end)
    sub = df.loc[m, client_col].astype(str).str.strip()
    return set(sub[sub != ""].unique())


def _ca_realise(df: pd.DataFrame, cols: Dict[str, str], start: date, end: date) -> float:
    date_col = cols["Date_opération"]
    conf_col = cols["CONFIRME"]
    pdv_c = cols["PDV_DEVIS_CONFIRME"]
    m = _mask_period(df, date_col, start, end) & df[conf_col].map(is_confirmed_exact)
    return float(df.loc[m, pdv_c].map(_to_float).sum())


def compute_ca_provisionnel(
    df: pd.DataFrame,
    cols: Dict[str, str],
    season_start: date,
    season_end: date,
    report_end: date,
) -> Tuple[float, Dict[str, Any]]:
    """
    CA provisionnel = full-season confirmed PDV + forward EN COURS add-on.

    1) **Base**: sum ``PDV_DEVIS_CONFIRME`` on CONFIRMÉ rows with ``Date_opération`` in
       ``[season_start, season_end]`` (full calendar season, same as ``_ca_realise``).

    2) **Forward add-on**: rows that are **EN COURS** (not cancelled) with ``Date_opération`` in the
       intersection of ``(report_end, season_end]`` and ``[season_start, season_end]``.
       Equivalently: ``forward_start = max(season_start, report_end + 1 day)`` through ``season_end``.

       For each ``CLIENT_ID`` in that slice: let ``n`` = number of distinct ``DEVIS_ID`` and
       ``S`` = sum of ``PDV_DEVIS`` on those rows. Contribution = ``S / n`` (one devis → ``S``;
       several devis → average per devis, then one amount per client — sum ``S`` and divide by ``n``).

    ``report_end`` should be ``min(week_end, season_end)`` where ``week_end`` comes from
    ``previous_completed_week(as_of)`` (Sunday). The forward window **ends at season_end**
    (e.g. 30 Apr for HIVER), not the day after — so it matches “remaining pipeline to end of season”.

    Returns (total_eur, debug_counts).
    """
    date_col = cols["Date_opération"]
    client_col = cols["CLIENT_ID"]
    devis_col = cols["DEVIS_ID"]
    conf_col = cols["CONFIRME"]
    pdv_col = cols["PDV_DEVIS"]

    base = _ca_realise(df, cols, season_start, season_end)

    # Forward window: strictly after report_end, through season end; clipped to season bounds.
    forward_start = max(season_start, report_end + timedelta(days=1))
    forward_end = season_end
    empty_dbg: Dict[str, Any] = {
        "base_pdv_confirme_full_season": base,
        "forward_en_cours_addon": 0.0,
        "forward_window": f"{forward_start}..{forward_end}",
        "report_end": str(report_end),
        "clients_forward_en_cours": 0,
    }
    if forward_start > forward_end:
        return base, {**empty_dbg, "forward_window": "(empty)"}

    m_fwd = _mask_period(df, date_col, forward_start, forward_end) & df[conf_col].map(
        is_en_cours
    ) & ~df[conf_col].map(is_cancelled_status)
    sub = df.loc[m_fwd].copy()
    if sub.empty:
        return base, empty_dbg

    sub["_pdv"] = sub[pdv_col].map(_to_float)
    addon = 0.0
    n_clients_fwd = 0
    for cid, g in sub.groupby(client_col):
        cid_s = str(cid).strip()
        if not cid_s:
            continue
        pdv_sum = float(g["_pdv"].sum())
        n_devis = int(g[devis_col].nunique(dropna=False))
        if n_devis < 1:
            n_devis = 1
        addon += pdv_sum / float(n_devis)
        n_clients_fwd += 1

    total = base + addon
    return total, {
        "base_pdv_confirme_full_season": base,
        "forward_en_cours_addon": addon,
        "forward_window": f"{forward_start}..{forward_end}",
        "report_end": str(report_end),
        "season_bounds": f"{season_start}..{season_end}",
        "clients_forward_en_cours": n_clients_fwd,
    }


def compute_weekly_kpis(
    df: pd.DataFrame,
    as_of: Optional[date] = None,
) -> WeeklyKpiResult:
    """
    Compute all KPIs. `as_of` is typically the send date (e.g. Monday);
    the week window is the previous completed Mon–Sun.
    """
    import datetime as dt

    if as_of is None:
        as_of = dt.date.today()
    elif hasattr(as_of, "date"):
        as_of = as_of.date()

    cols = _resolve_columns(df)
    week_start, week_end = previous_completed_week(as_of)
    current_season = season_containing(as_of)
    next_se = next_season_after(current_season)
    s_start, s_end = season_window_for_metrics(current_season, as_of)

    # Realised dossier count = confirmed (same definition; see README)
    dossiers_confirme_sem = _unique_clients_in_period(
        df,
        cols,
        week_start,
        week_end,
        row_mask_extra=df[cols["CONFIRME"]].map(is_confirmed_exact),
    )
    dossiers_confirme_sai = _unique_clients_in_period(
        df,
        cols,
        current_season.start,
        current_season.end,
        row_mask_extra=df[cols["CONFIRME"]].map(is_confirmed_exact),
    )
    dossiers_realise_sem = dossiers_confirme_sem
    dossiers_realise_sai = _unique_clients_in_period(
        df,
        cols,
        s_start,
        s_end,
        row_mask_extra=df[cols["CONFIRME"]].map(is_confirmed_exact),
    )

    dossiers_propose_sem = len(
        _client_ids_with_date_demande_in_period(df, cols, week_start, week_end)
    )
    dossiers_propose_sai = len(
        _client_ids_with_date_operation_in_period(
            df, cols, current_season.start, current_season.end
        )
    )

    ca_sem = _ca_realise(df, cols, week_start, week_end)
    # Full calendar season — aligns with Excel when filtering Date_opération through season end (e.g. 30 Apr).
    ca_sai = _ca_realise(df, cols, current_season.start, current_season.end)

    # Pipeline "after report" should start the day after the last day of the *completed* week
    # (Sunday), not after the email send date (Monday) — otherwise we drop one calendar day of
    # EN COURS rows vs typical Excel cuts.
    report_end_cours = min(week_end, current_season.end)
    prov_cours, dbg_cours = compute_ca_provisionnel(
        df, cols, current_season.start, current_season.end, report_end_cours
    )
    dbg_cours["as_of"] = str(as_of)
    dbg_cours["week_end"] = str(week_end)

    report_end_next = min(week_end, next_se.end)
    prov_next, dbg_next = compute_ca_provisionnel(
        df, cols, next_se.start, next_se.end, report_end_next
    )
    dbg_next["as_of"] = str(as_of)
    dbg_next["week_end"] = str(week_end)

    n_rows = len(df)
    n_clients_all = int(
        df[cols["CLIENT_ID"]].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    )

    c_sem = _confirmed_client_ids_in_period(df, cols, week_start, week_end)
    p_sem = _client_ids_with_date_demande_in_period(df, cols, week_start, week_end)
    c_sai = _confirmed_client_ids_in_period(
        df, cols, current_season.start, current_season.end
    )
    p_sai = _client_ids_with_date_operation_in_period(
        df, cols, current_season.start, current_season.end
    )

    validation: Dict[str, Any] = {
        "source_rows": n_rows,
        "unique_client_id": n_clients_all,
        "week_start": str(week_start),
        "week_end": str(week_end),
        "dossiers_propose_semaine_basis": "Date_Demande",
        "dossiers_propose_saison_basis": "Date_opération",
        "dossiers_confirme_saison_window": f"{current_season.start}..{current_season.end}",
        "dossiers_realise_saison_window": f"{s_start}..{s_end}",
        "current_season_label": current_season.label,
        "next_season_label": next_se.label,
        "season_metrics_start": str(s_start),
        "season_metrics_end": str(s_end),
        "proposed_dossiers_season_window": f"{current_season.start}..{current_season.end}",
        "ca_realise_saison_window": f"{current_season.start}..{current_season.end}",
        "ca_provisionnel_cours_window": f"{current_season.start}..{current_season.end}",
        "ca_provisionnel_cours_report_end": str(report_end_cours),
        "ca_provisionnel_report_cutoff_note": "report_end = min(week_end, season_end), not as_of",
        "ca_provisionnel_next_window": f"{next_se.start}..{next_se.end}",
        "ca_provisionnel_next_report_end": str(report_end_next),
        "dossiers_realise_semaine": dossiers_realise_sem,
        "dossiers_confirme_semaine": dossiers_confirme_sem,
        "dossiers_propose_semaine": dossiers_propose_sem,
        "dossiers_realise_saison": dossiers_realise_sai,
        "dossiers_confirme_saison": dossiers_confirme_sai,
        "dossiers_propose_saison": dossiers_propose_sai,
        "ca_realise_semaine": round(ca_sem, 2),
        "ca_realise_saison": round(ca_sai, 2),
        "ca_provisionnel_saison_cours": round(prov_cours, 2),
        "ca_provisionnel_saison_suivante": round(prov_next, 2),
        "provisionnel_cours_breakdown": dbg_cours,
        "provisionnel_next_breakdown": dbg_next,
        "overlap_proposed_confirmed_week": len(c_sem & p_sem),
        "overlap_proposed_confirmed_season": len(c_sai & p_sai),
    }

    logger.info("Weekly KPI validation: %s", validation)

    return WeeklyKpiResult(
        week_start=week_start,
        week_end=week_end,
        current_season=current_season,
        next_season=next_se,
        season_metrics_end=s_end,
        dossiers_realise_semaine=dossiers_realise_sem,
        dossiers_realise_saison=dossiers_realise_sai,
        dossiers_propose_semaine=dossiers_propose_sem,
        dossiers_propose_saison=dossiers_propose_sai,
        dossiers_confirme_semaine=dossiers_confirme_sem,
        dossiers_confirme_saison=dossiers_confirme_sai,
        ca_realise_semaine=ca_sem,
        ca_realise_saison=ca_sai,
        ca_provisionnel_saison_cours=prov_cours,
        ca_provisionnel_saison_suivante=prov_next,
        validation=validation,
    )

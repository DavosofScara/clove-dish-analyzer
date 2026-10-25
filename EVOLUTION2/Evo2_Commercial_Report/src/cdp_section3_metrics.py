"""Metrics for CDP weekly report section 3 (team-wide, no CDP leaderboard)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple

import pandas as pd

from .charts import add_site_label_column, render_site_pdv_season_bars
from .load_data import augment_client_key, coerce_number, get_ci_column, normalize_str_series
from .periods import date_in_range
from .status_norm import is_confirmed_exact, is_en_cours
from .weekly_kpis import (
    WeeklyKpiResult,
    _resolve_columns as resolve_weekly_kpi_columns,
    ca_confirme_semaine_by_date_confirme,
    median_pdv_confirme_semaine_by_date_confirme,
)


def calendar_week_containing(d: date) -> Tuple[date, date]:
    """Monday–Sunday of the calendar week that contains ``d``."""
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


@dataclass
class ClientAgentRow:
    client: str
    agent: str
    pdv: float
    date_operation: Optional[date] = None
    days_stagnant: Optional[int] = None


@dataclass
class SiteSeasonRow:
    site: str
    taux_confirmation: float
    marge_confirme_eur: float
    marge_pct_avg: float
    ca_confirme_pdv: float


@dataclass
class CdpSection3Metrics:
    en_cours_clients: int
    en_cours_pdv: float
    stagnant_clients: int
    season_marge_pct_global: Optional[float]
    cal_week_start: date
    cal_week_end: date
    confirmed_cal_week_clients: int
    confirmed_cal_week_ca: float
    ca_confirme_semaine: float
    median_pdv_confirme_semaine: float
    median_pdv_ref_week: float
    median_pdv_season: float
    date_confirme_missing_count: int
    date_confirme_fill_pct: Optional[float]
    season_taux_confirmation: float
    season_marge_confirme_eur: float
    season_marge_final_pct: Optional[float]
    season_marge_reelle_eur: float
    season_ca_confirme_pdv: float
    type_mix_pct: pd.Series
    site_marge_pct_chart: pd.Series
    site_ca_confirme_chart: pd.Series
    site_season_table: List[SiteSeasonRow]
    list_upcoming: List[ClientAgentRow]
    list_stagnant: List[ClientAgentRow]
    top_agents_en_cours: List[Tuple[str, int, float]]
    chart_type_mix_uri: str = ""
    chart_site_marge_pct_uri: str = ""
    chart_site_ca_confirme_uri: str = ""


def _col(df: pd.DataFrame, name: str) -> Optional[str]:
    return get_ci_column(df, name)


def _to_date(val) -> Optional[date]:
    if val is None or pd.isna(val):
        return None
    if hasattr(val, "date") and callable(getattr(val, "date")):
        try:
            return val.date()
        except (ValueError, AttributeError):
            pass
    if isinstance(val, date):
        return val
    return None


def _en_cours_season_mask(
    df: pd.DataFrame,
    cols: dict,
    season_start: date,
    season_end: date,
) -> pd.Series:
    conf = df[cols["confirme"]].map(is_en_cours)
    dop = df[cols["date_op"]].apply(lambda d: date_in_range(d, season_start, season_end))
    return conf & dop


def _client_level_en_cours(
    df: pd.DataFrame,
    mask: pd.Series,
    cols: dict,
) -> pd.DataFrame:
    sub = df.loc[mask].copy()
    if sub.empty:
        return pd.DataFrame(
            columns=["client", "agent", "pdv", "date_op", "date_demande"]
        )
    cid = cols["client_id"]
    pdv_col = cols["pdv"]
    sub["_pdv"] = sub[pdv_col].fillna(0).astype(float)
    nom_c = cols.get("nom_client") or cid
    nom_a = cols.get("nom_agent") or cid

    def _first_nonempty(s: pd.Series) -> str:
        for v in s:
            t = str(v or "").strip()
            if t:
                return t
        return "—"

    def _min_date_col(s: pd.Series) -> Optional[date]:
        dates = [_to_date(x) for x in s if _to_date(x) is not None]
        return min(dates) if dates else None

    agg = (
        sub.groupby(cid, as_index=False)
        .agg(
            pdv=("_pdv", "sum"),
            client=(nom_c, _first_nonempty),
            agent=(nom_a, _first_nonempty),
            date_op=(cols["date_op"], _min_date_col),
            date_demande=(cols["date_demande"], _min_date_col),
        )
    )
    return agg


def _compute_date_confirme_stats(
    df: pd.DataFrame,
    client_db: pd.DataFrame,
    season_start: date,
    season_end: date,
    cols: dict,
) -> Tuple[int, Optional[float]]:
    """Missing confirmed-season dossiers without DATE CONFIRME; fill % on distinct client keys."""
    if client_db.empty or "NOM_CLIENT" not in client_db.columns:
        return 0, None

    cdf = augment_client_key(client_db.copy())
    if "DATE_CONFIRME_CLIENT" in cdf.columns:
        has_date = cdf["DATE_CONFIRME_CLIENT"].notna()
        keys_filled = set(
            cdf.loc[has_date, "client_key"].astype(str).str.strip().replace("", pd.NA).dropna()
        )
        all_keys = cdf["client_key"].astype(str).str.strip().replace("", pd.NA).dropna().unique()
        fill_pct = (100.0 * len(keys_filled) / len(all_keys)) if len(all_keys) else None
    else:
        keys_filled = set()
        fill_pct = None

    conf = df[cols["confirme"]].map(is_confirmed_exact)
    in_season = df[cols["date_op"]].apply(lambda d: date_in_range(d, season_start, season_end))
    sub = df.loc[conf & in_season]
    if sub.empty or "client_key" not in sub.columns:
        return 0, fill_pct

    missing = 0
    for _, grp in sub.groupby(cols["client_id"]):
        key = str(grp["client_key"].iloc[0] or "").strip()
        if key and key not in keys_filled:
            missing += 1
    return missing, fill_pct


def _median_pdv_confirmed_period(
    df: pd.DataFrame,
    period_start: date,
    period_end: date,
    cols: dict,
) -> float:
    conf = df[cols["confirme"]].map(is_confirmed_exact)
    in_period = df[cols["date_op"]].apply(
        lambda d: date_in_range(d, period_start, period_end)
    )
    sub = df.loc[conf & in_period]
    if sub.empty:
        return 0.0
    pdv_col = cols["pdv_confirme"] or cols["pdv"]
    per_client = sub.groupby(cols["client_id"])[pdv_col].sum()
    if per_client.empty:
        return 0.0
    return float(per_client.median())


def _season_confirmed_extract_mask(
    df: pd.DataFrame,
    cols: dict,
    season_start: date,
    season_end: date,
) -> pd.Series:
    conf = df[cols["confirme"]].map(is_confirmed_exact)
    in_season = df[cols["date_op"]].apply(
        lambda d: date_in_range(d, season_start, season_end)
    )
    return conf & in_season


def _season_marge_confirme_extract_eur(
    df: pd.DataFrame,
    cols: dict,
    season_start: date,
    season_end: date,
) -> float:
    """
    Sum ``MARGE_FINAL_EVENTS`` on CONFIRMÉ extract rows with ``Date_opération`` in the
    full calendar season (all confirmed dossiers, not ``Marge_Reelle_Devis`` validated only).
    """
    marge_col = _col(df, "MARGE_FINAL_EVENTS")
    if not marge_col:
        return 0.0
    mask = _season_confirmed_extract_mask(df, cols, season_start, season_end)
    sub = df.loc[mask, marge_col]
    if sub.empty:
        return 0.0
    return float(sub.apply(coerce_number).fillna(0).astype(float).sum())


def _season_marge_final_pct_ratio(
    df: pd.DataFrame,
    cols: dict,
    season_start: date,
    season_end: date,
) -> Optional[float]:
    """Σ ``MARGE_FINAL_EVENTS`` ÷ Σ ``PDV_DEVIS_CONFIRME`` on confirmed season rows (ratio 0–1)."""
    marge_col = _col(df, "MARGE_FINAL_EVENTS")
    pdvc_col = cols.get("pdv_confirme") or _col(df, "PDV_DEVIS_CONFIRME")
    if not marge_col or not pdvc_col:
        return None
    mask = _season_confirmed_extract_mask(df, cols, season_start, season_end)
    sub = df.loc[mask]
    if sub.empty:
        return None
    pdv_total = float(sub[pdvc_col].apply(coerce_number).fillna(0).astype(float).sum())
    if pdv_total <= 0:
        return None
    marge_total = float(sub[marge_col].apply(coerce_number).fillna(0).astype(float).sum())
    return marge_total / pdv_total


def _confirmed_type_mix(
    df: pd.DataFrame,
    season_start: date,
    season_end: date,
    cols: dict,
) -> pd.Series:
    type_col = cols.get("type_client")
    if not type_col:
        return pd.Series(dtype=float)
    conf = df[cols["confirme"]].map(is_confirmed_exact)
    in_season = df[cols["date_op"]].apply(lambda d: date_in_range(d, season_start, season_end))
    sub = df.loc[conf & in_season].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    pdv_col = cols["pdv_confirme"] or cols["pdv"]
    sub["_pdv"] = sub[pdv_col].fillna(0).astype(float)
    sub[type_col] = normalize_str_series(sub[type_col])
    sub = sub[sub[type_col].astype(str).str.strip() != ""]
    totals = sub.groupby(type_col)["_pdv"].sum()
    total = totals.sum()
    if total <= 0:
        return pd.Series(dtype=float)
    return (100.0 * totals / total).sort_values(ascending=False)


def _season_confirmation_rate(
    df: pd.DataFrame,
    cols: dict,
    season_start: date,
    season_end: date,
) -> float:
    in_season = df[cols["date_op"]].apply(lambda d: date_in_range(d, season_start, season_end))
    sub = df.loc[in_season]
    if sub.empty:
        return 0.0
    cid = cols["client_id"]
    total = sub[cid].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    if total == 0:
        return 0.0
    conf = sub[cols["confirme"]].map(is_confirmed_exact)
    confirmed_n = sub.loc[conf, cid].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    return float(confirmed_n) / float(total)


def _site_season_stats(
    marge_df: pd.DataFrame,
    extract_df: pd.DataFrame,
    cols: dict,
    season_start: date,
    season_end: date,
    top_n: int = 5,
) -> Tuple[List[SiteSeasonRow], pd.Series, pd.Series, float, float, float]:
    """
    Per-site season KPIs + network totals. Top ``top_n`` sites ranked by mean margin % (marge sheet).
    """
    cid_col = cols["client_id"]
    conf_col = cols["confirme"]
    date_op = cols["date_op"]
    pdvc_col = cols.get("pdv_confirme") or cols["pdv"]

    ex = add_site_label_column(extract_df)
    in_season = ex[date_op].apply(lambda d: date_in_range(d, season_start, season_end))
    sub = ex.loc[in_season].copy()
    site_col = "_REPORT_SITE_LABEL"

    extract_by_site = pd.DataFrame()
    if not sub.empty:
        sub = sub[sub[site_col].astype(str).str.strip() != ""]
        conf_mask = sub[conf_col].map(is_confirmed_exact)
        total_clients = sub.groupby(site_col)[cid_col].nunique()
        conf_clients = sub.loc[conf_mask].groupby(site_col)[cid_col].nunique()
        ca_conf = sub.loc[conf_mask].copy()
        ca_conf["_pdvc"] = ca_conf[pdvc_col].fillna(0).astype(float)
        ca_by_site = ca_conf.groupby(site_col)["_pdvc"].sum()
        extract_by_site = pd.DataFrame(
            {
                "taux_confirmation": conf_clients / total_clients.replace(0, pd.NA),
                "ca_confirme_pdv": ca_by_site,
            }
        ).fillna(0.0)

    marge_by_site = pd.DataFrame()
    season_marge_eur = 0.0
    if not marge_df.empty:
        work = marge_df.copy()
        if "Date_opération" in work.columns:
            m = work["Date_opération"].apply(lambda d: date_in_range(d, season_start, season_end))
            work = work.loc[m]
        if not work.empty and "CLIENT_ID" in work.columns:
            site_by_client = (
                ex.groupby(ex[cid_col].astype(str).str.strip(), dropna=False)[site_col]
                .agg(lambda s: next((x for x in s.astype(str) if str(x).strip()), ""))
            )
            work["_cid"] = work["CLIENT_ID"].astype(str).str.strip()
            work = work[work["_cid"] != ""]
            work["_site"] = work["_cid"].map(site_by_client).fillna("").astype(str).str.strip()
            work = work[work["_site"] != ""]
            if not work.empty:
                pdv = work["PDV_DEVIS"].astype(float)
                work["_marge"] = work["MARGE_EVENTS_REELLE"].fillna(0).astype(float)
                work["_mpct"] = 100.0 * work["_marge"] / pdv.replace(0, pd.NA)
                season_marge_eur = float(work["_marge"].sum())
                marge_by_site = work.groupby("_site", as_index=True).agg(
                    marge_confirme_eur=("_marge", "sum"),
                    marge_pct_avg=("_mpct", "mean"),
                )

    all_sites = extract_by_site.index.union(marge_by_site.index).astype(str)
    rows_data = []
    for site in all_sites:
        if not str(site).strip():
            continue
        taux = float(extract_by_site.loc[site, "taux_confirmation"]) if site in extract_by_site.index else 0.0
        ca = float(extract_by_site.loc[site, "ca_confirme_pdv"]) if site in extract_by_site.index else 0.0
        m_eur = (
            float(marge_by_site.loc[site, "marge_confirme_eur"])
            if site in marge_by_site.index
            else 0.0
        )
        m_pct = (
            float(marge_by_site.loc[site, "marge_pct_avg"])
            if site in marge_by_site.index and pd.notna(marge_by_site.loc[site, "marge_pct_avg"])
            else 0.0
        )
        rows_data.append(
            {
                "site": str(site),
                "taux_confirmation": taux,
                "marge_confirme_eur": m_eur,
                "marge_pct_avg": m_pct,
                "ca_confirme_pdv": ca,
            }
        )

    if not rows_data:
        return [], pd.Series(dtype=float), pd.Series(dtype=float), 0.0, season_marge_eur, 0.0

    frame = pd.DataFrame(rows_data)
    # Same top sites as section 4: highest CA confirmé (saison calendaire), not margin-only subset.
    top_frame = frame.sort_values("ca_confirme_pdv", ascending=False).head(top_n)

    table = [
        SiteSeasonRow(
            site=r["site"],
            taux_confirmation=float(r["taux_confirmation"]),
            marge_confirme_eur=float(r["marge_confirme_eur"]),
            marge_pct_avg=float(r["marge_pct_avg"]),
            ca_confirme_pdv=float(r["ca_confirme_pdv"]),
        )
        for _, r in top_frame.iterrows()
    ]

    marge_pct_series = top_frame.set_index("site")["marge_pct_avg"]
    ca_series = top_frame.set_index("site")["ca_confirme_pdv"]

    network_taux = _season_confirmation_rate(extract_df, cols, season_start, season_end)
    network_ca = float(extract_by_site["ca_confirme_pdv"].sum()) if not extract_by_site.empty else 0.0

    return table, marge_pct_series, ca_series, network_taux, season_marge_eur, network_ca


def _season_marge_reelle_eur(
    marge_df: pd.DataFrame,
    season_start: date,
    season_end: date,
) -> float:
    """Σ ``MARGE_EVENTS_REELLE`` on ``Marge_Reelle_Devis`` (ALL_LINES_VALIDE), season ``Date_opération``."""
    if marge_df.empty:
        return 0.0
    work = marge_df.copy()
    if "Date_opération" in work.columns:
        m = work["Date_opération"].apply(
            lambda d: date_in_range(d, season_start, season_end)
        )
        work = work.loc[m]
    if work.empty:
        return 0.0
    return float(work["MARGE_EVENTS_REELLE"].fillna(0).astype(float).sum())


def _global_margin_pct_confirmed(
    marge_df: pd.DataFrame,
    season_start: date,
    season_end: date,
) -> Optional[float]:
    """
    One margin % for confirmed devis in season: 100 × Σ marge réelle € ÷ Σ PDV_DEVIS.
    (Marge_Reelle_Devis, ALL_LINES_VALIDE rows already filtered at load.)
    """
    if marge_df.empty:
        return None
    work = marge_df.copy()
    if "Date_opération" in work.columns:
        m = work["Date_opération"].apply(lambda d: date_in_range(d, season_start, season_end))
        work = work.loc[m]
    if work.empty:
        return None
    pdv_total = float(work["PDV_DEVIS"].astype(float).sum())
    if pdv_total <= 0:
        return None
    marge_total = float(work["MARGE_EVENTS_REELLE"].fillna(0).astype(float).sum())
    return 100.0 * marge_total / pdv_total


def compute_cdp_section3_metrics(
    df: pd.DataFrame,
    kpi: WeeklyKpiResult,
    as_of: date,
    *,
    client_db: pd.DataFrame,
    marge_df: pd.DataFrame,
    list_limit: int = 8,
    agent_top_n: int = 5,
) -> CdpSection3Metrics:
    client_col = _col(df, "CLIENT_ID")
    conf_col = _col(df, "CONFIRME")
    date_op_col = _col(df, "Date_opération")
    date_dem_col = _col(df, "Date_Demande")
    pdv_col = _col(df, "PDV_DEVIS")
    pdvc_col = _col(df, "PDV_DEVIS_CONFIRME")
    nom_client = _col(df, "NOM_CLIENT")
    nom_agent = _col(df, "NOM_AGENT")
    type_col = _col(df, "TYPE_DE_CLIENT")

    if not all([client_col, conf_col, date_op_col, pdv_col]):
        raise ValueError("extract_devis missing required columns for section 3.")

    cols = {
        "client_id": client_col,
        "confirme": conf_col,
        "date_op": date_op_col,
        "date_demande": date_dem_col or date_op_col,
        "pdv": pdv_col,
        "pdv_confirme": pdvc_col,
        "nom_client": nom_client,
        "nom_agent": nom_agent,
        "type_client": type_col,
    }

    season_start = kpi.current_season.start
    season_end = kpi.current_season.end
    base_mask = _en_cours_season_mask(df, cols, season_start, season_end)
    base_agg = _client_level_en_cours(df, base_mask, cols)

    en_cours_clients = len(base_agg)
    en_cours_pdv = float(base_agg["pdv"].sum()) if not base_agg.empty else 0.0

    cutoff_stagnant = as_of - timedelta(days=30)
    if not base_agg.empty and "date_demande" in base_agg.columns:
        stag_mask = base_agg["date_demande"].apply(
            lambda d: (_to_date(d) is not None and _to_date(d) <= cutoff_stagnant)
        )
        stagnant_agg = base_agg.loc[stag_mask]
    else:
        stagnant_agg = base_agg.iloc[0:0]

    stagnant_clients = len(stagnant_agg)

    horizon_end = as_of + timedelta(days=30)
    if not base_agg.empty:
        up_mask = base_agg["date_op"].apply(
            lambda d: _to_date(d) is not None and date_in_range(_to_date(d), as_of, horizon_end)
        )
        upcoming_agg = base_agg.loc[up_mask].sort_values("pdv", ascending=False)
    else:
        upcoming_agg = base_agg

    def _rows_from_agg(agg: pd.DataFrame, *, with_stagnant_days: bool) -> List[ClientAgentRow]:
        out: List[ClientAgentRow] = []
        for _, r in agg.head(list_limit).iterrows():
            days = None
            if with_stagnant_days and r.get("date_demande"):
                dd = r["date_demande"]
                if dd:
                    days = (as_of - dd).days
            out.append(
                ClientAgentRow(
                    client=str(r.get("client") or "—"),
                    agent=str(r.get("agent") or "—"),
                    pdv=float(r.get("pdv") or 0),
                    date_operation=r.get("date_op"),
                    days_stagnant=days,
                )
            )
        return out

    list_upcoming = _rows_from_agg(upcoming_agg, with_stagnant_days=False)
    list_stagnant = _rows_from_agg(
        stagnant_agg.sort_values("pdv", ascending=False), with_stagnant_days=True
    )

    top_agents: List[Tuple[str, int, float]] = []
    if not base_agg.empty and nom_agent:
        agent_grp = base_agg.groupby("agent", as_index=False).agg(
            dossiers=("pdv", "count"),
            pdv_total=("pdv", "sum"),
        )
        agent_grp = agent_grp.sort_values("pdv_total", ascending=False).head(agent_top_n)
        for _, r in agent_grp.iterrows():
            top_agents.append((str(r["agent"]), int(r["dossiers"]), float(r["pdv_total"])))

    cal_start, cal_end = calendar_week_containing(as_of)
    conf = df[cols["confirme"]].map(is_confirmed_exact)
    in_cal = df[cols["date_op"]].apply(lambda d: date_in_range(d, cal_start, cal_end))
    cal_sub = df.loc[conf & in_cal]
    confirmed_cal_week_clients = int(cal_sub[client_col].nunique()) if not cal_sub.empty else 0
    pdv_use = pdvc_col or pdv_col
    confirmed_cal_week_ca = (
        float(cal_sub[pdv_use].fillna(0).astype(float).sum()) if not cal_sub.empty else 0.0
    )

    weekly_cols = resolve_weekly_kpi_columns(df)
    ca_sem_dc = ca_confirme_semaine_by_date_confirme(
        df, weekly_cols, kpi.week_start, kpi.week_end, client_db
    )
    median_sem_dc = median_pdv_confirme_semaine_by_date_confirme(
        df, weekly_cols, kpi.week_start, kpi.week_end, client_db
    )
    median_pdv = _median_pdv_confirmed_period(
        df, kpi.week_start, kpi.week_end, cols
    )
    median_pdv_season = _median_pdv_confirmed_period(
        df, season_start, season_end, cols
    )
    missing_dc, fill_pct = _compute_date_confirme_stats(
        df, client_db, season_start, season_end, cols
    )

    type_mix = _confirmed_type_mix(df, season_start, season_end, cols)
    (
        site_table,
        site_marge_pct_chart,
        site_ca_chart,
        season_taux,
        _season_marge_sheet_eur,
        season_ca_pdv,
    ) = _site_season_stats(marge_df, df, cols, season_start, season_end, top_n=5)
    season_marge_pct = _global_margin_pct_confirmed(marge_df, season_start, season_end)
    season_marge_card_eur = _season_marge_confirme_extract_eur(
        df, cols, season_start, season_end
    )
    season_marge_final_pct = _season_marge_final_pct_ratio(
        df, cols, season_start, season_end
    )
    season_marge_reelle = _season_marge_reelle_eur(
        marge_df, season_start, season_end
    )

    chart_type = render_site_pdv_season_bars(
        type_mix,
        accent="blue",
        xlabel="Part du CA confirmé (%)",
        value_as_percent=True,
    )
    chart_site_marge_pct = render_site_pdv_season_bars(
        site_marge_pct_chart,
        accent="orange",
        xlabel="Marge % moyenne",
        value_as_percent=True,
    )
    chart_site_ca = render_site_pdv_season_bars(
        site_ca_chart,
        accent="blue",
        xlabel="CA confirmé (€ HT)",
    )

    return CdpSection3Metrics(
        en_cours_clients=en_cours_clients,
        en_cours_pdv=en_cours_pdv,
        stagnant_clients=stagnant_clients,
        season_marge_pct_global=season_marge_pct,
        cal_week_start=cal_start,
        cal_week_end=cal_end,
        confirmed_cal_week_clients=confirmed_cal_week_clients,
        confirmed_cal_week_ca=confirmed_cal_week_ca,
        ca_confirme_semaine=ca_sem_dc,
        median_pdv_confirme_semaine=median_sem_dc,
        median_pdv_ref_week=median_pdv,
        median_pdv_season=median_pdv_season,
        date_confirme_missing_count=missing_dc,
        date_confirme_fill_pct=fill_pct,
        season_taux_confirmation=season_taux,
        season_marge_confirme_eur=season_marge_card_eur,
        season_marge_final_pct=season_marge_final_pct,
        season_marge_reelle_eur=season_marge_reelle,
        season_ca_confirme_pdv=season_ca_pdv,
        type_mix_pct=type_mix,
        site_marge_pct_chart=site_marge_pct_chart,
        site_ca_confirme_chart=site_ca_chart,
        site_season_table=site_table,
        list_upcoming=list_upcoming,
        list_stagnant=list_stagnant,
        top_agents_en_cours=top_agents,
        chart_type_mix_uri=chart_type,
        chart_site_marge_pct_uri=chart_site_marge_pct,
        chart_site_ca_confirme_uri=chart_site_ca,
    )

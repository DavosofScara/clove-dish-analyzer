"""
Annual (fiscal year) KPIs for the Evolution2 annual commercial report.

Independent of the weekly pipeline — do not import weekly week windows here.
Fiscal year: 1 October → 30 September. Metrics use ``Date_opération`` unless noted.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .load_data import coerce_number, get_ci_column
from .historical_master import (
    augment_df_for_prior_season,
    load_ete_2025_definitive,
    travail_period_metrics,
)
from .periods import (
    SeasonPeriod,
    date_in_range,
    fiscal_year_containing,
    hiver_and_ete_in_fiscal_year,
    previous_fiscal_year_before,
    previous_season_before,
    season_window_for_metrics,
)
from .status_norm import is_confirmed_exact

logger = logging.getLogger(__name__)

TOP_PRESTATION_N = 10
TOP_CDP_N = 5


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


def _pct_delta(current: float, prior: Optional[float]) -> Optional[float]:
    if prior is None or prior == 0:
        return None
    return (current - prior) / prior


@dataclass
class AnnualKpiResult:
    as_of: date
    fiscal_year: SeasonPeriod
    prior_fiscal_year: SeasonPeriod
    hiver: SeasonPeriod
    ete: SeasonPeriod
    metrics_end: date  # min(as_of, fy.end)

    # Hero cards
    ca_confirme_annee: float
    ca_confirme_annee_yoy: Optional[float]
    dossiers_confirmes: int
    dossiers_confirmes_yoy: Optional[int]
    dossiers_proposes: int
    taux_conversion: float
    taux_conversion_yoy: Optional[float]
    pdv_median_client: float
    pdv_median_client_yoy: Optional[float]
    marge_reelle_moyenne_pct: Optional[float]

    # Season split CA
    ca_hiver: float
    ca_hiver_yoy: Optional[float]
    ca_ete: float
    ca_ete_yoy: Optional[float]

    # Concentration
    top5_client_share: float
    top10_client_share: float

    # Rankings
    top_prestations_by_ca: pd.DataFrame  # Prestation, CA_confirme, Quantite, N_lignes
    top_prestations_by_qty: pd.DataFrame
    top_cdp: pd.DataFrame  # compact CDP table

    insights: List[str] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)


def _resolve_columns(df: pd.DataFrame) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for logical in (
        "CLIENT_ID",
        "DEVIS_ID",
        "Date_opération",
        "CONFIRME",
        "PDV_DEVIS_CONFIRME",
        "PRESTATIONS",
    ):
        c = get_ci_column(df, logical)
        if not c:
            raise ValueError(f"Required column missing: {logical}")
        out[logical] = c
    nb = get_ci_column(df, "Nb_Unite")
    if nb:
        out["Nb_Unite"] = nb
    return out


def _mask_period(df: pd.DataFrame, date_col: str, start: date, end: date) -> pd.Series:
    return df[date_col].apply(lambda d: date_in_range(d, start, end))


def _confirmed_mask(df: pd.DataFrame, cols: Dict[str, str], start: date, end: date) -> pd.Series:
    return _mask_period(df, cols["Date_opération"], start, end) & df[cols["CONFIRME"]].map(
        is_confirmed_exact
    )


def _ca_confirme(df: pd.DataFrame, cols: Dict[str, str], start: date, end: date) -> float:
    m = _confirmed_mask(df, cols, start, end)
    return float(df.loc[m, cols["PDV_DEVIS_CONFIRME"]].map(_to_float).sum())


def _prior_season_ca(
    df: pd.DataFrame,
    cols: Dict[str, str],
    prior_season: SeasonPeriod,
) -> float:
    """
    Prior same-type season CA: ÉTÉ 25 definitive when applicable, else extract,
    else dossier_travail_master (V14 has almost no N-1 ops).
    """
    work = augment_df_for_prior_season(df, prior_season)
    ca = _ca_confirme(work, cols, prior_season.start, prior_season.end)
    if ca > 0:
        return ca
    if prior_season.label == "ÉTÉ 25":
        hist = load_ete_2025_definitive()
        if not hist.empty:
            return float(hist["PDV_DEVIS_CONFIRME"].sum())
    return float(travail_period_metrics(prior_season.start, prior_season.end)["ca_confirme"])


def _prior_year_volume_metrics(
    df: pd.DataFrame,
    cols: Dict[str, str],
    prior: SeasonPeriod,
    *,
    ca_prior_year: float,
) -> Tuple[int, int, Optional[float], float]:
    """
    Dossiers / conversion / PDV médian for N-1.
    Prefer extract; if empty (typical V14 before Oct 2025), use dossier_travail_master.
    """
    conf = _unique_confirmed_clients(df, cols, prior.start, prior.end)
    prop = _unique_clients_any_status(df, cols, prior.start, prior.end)
    med = _median_pdv_per_client(df, cols, prior.start, prior.end)
    extract_ca = _ca_confirme(df, cols, prior.start, prior.end)

    if extract_ca < 1.0 and conf == 0:
        hist = travail_period_metrics(prior.start, prior.end)
        conf = int(hist["dossiers_confirmes"])
        prop = int(hist["dossiers_proposes"])
        med = float(hist["pdv_median_client"])
        logger.info(
            "Prior-year volume KPIs from %s (extract CA=%.0f)",
            hist["source"],
            extract_ca,
        )

    taux: Optional[float] = (conf / prop) if prop else None
    if taux is not None and conf == 0 and ca_prior_year <= 0:
        taux = None
    return conf, prop, taux, med


def _unique_confirmed_clients(
    df: pd.DataFrame, cols: Dict[str, str], start: date, end: date
) -> int:
    m = _confirmed_mask(df, cols, start, end)
    s = df.loc[m, cols["CLIENT_ID"]].astype(str).str.strip()
    return int(s[s != ""].nunique())


def _unique_clients_any_status(
    df: pd.DataFrame, cols: Dict[str, str], start: date, end: date
) -> int:
    m = _mask_period(df, cols["Date_opération"], start, end)
    s = df.loc[m, cols["CLIENT_ID"]].astype(str).str.strip()
    return int(s[s != ""].nunique())


def _median_pdv_per_client(
    df: pd.DataFrame, cols: Dict[str, str], start: date, end: date
) -> float:
    m = _confirmed_mask(df, cols, start, end)
    sub = df.loc[m, [cols["CLIENT_ID"], cols["PDV_DEVIS_CONFIRME"]]].copy()
    if sub.empty:
        return 0.0
    sub["_pdv"] = sub[cols["PDV_DEVIS_CONFIRME"]].map(_to_float)
    sub["_cid"] = sub[cols["CLIENT_ID"]].astype(str).str.strip()
    sub = sub[sub["_cid"] != ""]
    if sub.empty:
        return 0.0
    by_client = sub.groupby("_cid")["_pdv"].sum()
    return float(by_client.median()) if len(by_client) else 0.0


def _client_concentration(
    df: pd.DataFrame, cols: Dict[str, str], start: date, end: date
) -> Tuple[float, float]:
    m = _confirmed_mask(df, cols, start, end)
    sub = df.loc[m, [cols["CLIENT_ID"], cols["PDV_DEVIS_CONFIRME"]]].copy()
    if sub.empty:
        return 0.0, 0.0
    sub["_pdv"] = sub[cols["PDV_DEVIS_CONFIRME"]].map(_to_float)
    sub["_cid"] = sub[cols["CLIENT_ID"]].astype(str).str.strip()
    sub = sub[sub["_cid"] != ""]
    by_client = sub.groupby("_cid")["_pdv"].sum().sort_values(ascending=False)
    total = float(by_client.sum())
    if total <= 0:
        return 0.0, 0.0
    top5 = float(by_client.head(5).sum() / total)
    top10 = float(by_client.head(10).sum() / total)
    return top5, top10


def compute_top_prestations(
    df: pd.DataFrame,
    cols: Dict[str, str],
    start: date,
    end: date,
    *,
    top_n: int = TOP_PRESTATION_N,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Confirmed lines with ``Date_opération`` in [start, end].

    - CA = sum ``PDV_DEVIS_CONFIRME`` (line-level HT)
    - Quantité = sum ``Nb_Unite`` (mixed units — see Définitions)
    """
    empty = pd.DataFrame(columns=["Prestation", "CA_confirme", "Quantite", "N_lignes"])
    m = _confirmed_mask(df, cols, start, end)
    sub = df.loc[m].copy()
    if sub.empty:
        return empty.copy(), empty.copy()

    prest_col = cols["PRESTATIONS"]
    sub["_prest"] = (
        sub[prest_col]
        .astype("string")
        .fillna("")
        .str.strip()
        .replace("", pd.NA)
    )
    sub = sub.dropna(subset=["_prest"])
    if sub.empty:
        return empty.copy(), empty.copy()

    sub["_ca"] = sub[cols["PDV_DEVIS_CONFIRME"]].map(_to_float)
    if "Nb_Unite" in cols:
        sub["_qty"] = sub[cols["Nb_Unite"]].map(
            lambda v: float(coerce_number(v) or 0.0)
        )
    else:
        sub["_qty"] = 0.0

    agg = (
        sub.groupby("_prest", sort=False)
        .agg(CA_confirme=("_ca", "sum"), Quantite=("_qty", "sum"), N_lignes=("_ca", "count"))
        .reset_index()
        .rename(columns={"_prest": "Prestation"})
    )
    by_ca = agg.sort_values("CA_confirme", ascending=False).head(top_n).reset_index(drop=True)
    by_qty = agg.sort_values("Quantite", ascending=False).head(top_n).reset_index(drop=True)
    return by_ca, by_qty


def _average_marge_reelle_pct(
    marge_df: Optional[pd.DataFrame],
    start: date,
    end: date,
) -> Optional[float]:
    """Simple average of 100 × MARGE_EVENTS_REELLE / PDV_DEVIS on ALL_LINES_VALIDE rows."""
    if marge_df is None or marge_df.empty:
        return None
    date_col = get_ci_column(marge_df, "Date_opération")
    pdv_col = get_ci_column(marge_df, "PDV_DEVIS") or get_ci_column(marge_df, "PDV_DEVIS_CONFIRME")
    marge_col = get_ci_column(marge_df, "MARGE_EVENTS_REELLE")
    valid_col = get_ci_column(marge_df, "ALL_LINES_VALIDE")
    if not (date_col and pdv_col and marge_col):
        return None
    work = marge_df.copy()
    if valid_col:
        work = work[work[valid_col].map(lambda v: str(v).strip().lower() in ("true", "1", "yes"))]
    work = work[work[date_col].apply(lambda d: date_in_range(d, start, end))]
    if work.empty:
        return None
    pcts: List[float] = []
    for _, row in work.iterrows():
        pdv = _to_float(row[pdv_col])
        if pdv == 0:
            continue
        pcts.append(100.0 * _to_float(row[marge_col]) / pdv)
    if not pcts:
        return None
    return float(sum(pcts) / len(pcts))


def _build_insights(kpi: "AnnualKpiResult") -> List[str]:
    bullets: List[str] = []
    yoy = _pct_delta(kpi.ca_confirme_annee, kpi.ca_confirme_annee_yoy)
    if yoy is not None:
        sign = "+" if yoy >= 0 else ""
        bullets.append(
            f"CA confirmé HT {kpi.fiscal_year.label} : {sign}{yoy * 100:.1f} % vs {kpi.prior_fiscal_year.label}."
        )
    total_seasons = kpi.ca_hiver + kpi.ca_ete
    if total_seasons > 0:
        share_ete = kpi.ca_ete / total_seasons
        bullets.append(
            f"Répartition saisonnière : ÉTÉ {share_ete * 100:.0f} % / "
            f"HIVER {(1 - share_ete) * 100:.0f} % du CA confirmé de l’année."
        )
    if not kpi.top_prestations_by_ca.empty:
        top = kpi.top_prestations_by_ca.iloc[0]
        share = (
            float(top["CA_confirme"]) / kpi.ca_confirme_annee
            if kpi.ca_confirme_annee
            else 0.0
        )
        bullets.append(
            f"Prestation n°1 en CA : {top['Prestation']} "
            f"({share * 100:.1f} % du CA confirmé annuel)."
        )
    if not kpi.top_prestations_by_qty.empty:
        topq = kpi.top_prestations_by_qty.iloc[0]
        bullets.append(
            f"Prestation n°1 en quantité (Nb_Unite) : {topq['Prestation']} "
            f"({float(topq['Quantite']):,.0f} unités cumulées)."
        )
    bullets.append(
        f"Concentration clients : top 5 = {kpi.top5_client_share * 100:.0f} % du CA, "
        f"top 10 = {kpi.top10_client_share * 100:.0f} %."
    )
    if kpi.taux_conversion_yoy is not None:
        d = kpi.taux_conversion - kpi.taux_conversion_yoy
        sign = "+" if d >= 0 else ""
        bullets.append(
            f"Taux de conversion année : {kpi.taux_conversion * 100:.1f} % "
            f"({sign}{d * 100:.1f} pts vs N-1)."
        )
    return bullets[:6]


def compute_annual_kpis(
    df: pd.DataFrame,
    as_of: date,
    *,
    marge_df: Optional[pd.DataFrame] = None,
    cdp_table: Optional[pd.DataFrame] = None,
) -> AnnualKpiResult:
    """
    Full fiscal-year KPIs capped at ``min(as_of, fy.end)`` for report-to-date counts
    where relevant; CA confirmé uses the full calendar fiscal year through ``metrics_end``
    (on 30/09 = full year).

    N-1: live extract when present; else ÉTÉ 25 definitive + dossier travail for HIVER
    and client counts (V14 is thin before Oct 2025).
    """
    cols = _resolve_columns(df)
    fy = fiscal_year_containing(as_of)
    prior = previous_fiscal_year_before(fy)
    hiver, ete = hiver_and_ete_in_fiscal_year(fy)
    _, metrics_end = season_window_for_metrics(fy, as_of)

    hiver_end = min(hiver.end, metrics_end)
    ete_end = min(ete.end, metrics_end)
    if hiver_end < hiver.start:
        hiver_end = hiver.start
    if ete_end < ete.start:
        ete_end = ete.start

    prior_hiver = previous_season_before(hiver)
    prior_ete = previous_season_before(ete)

    ca_year = _ca_confirme(df, cols, fy.start, metrics_end)
    ca_hiver = _ca_confirme(df, cols, hiver.start, hiver_end)
    ca_ete = _ca_confirme(df, cols, ete.start, ete_end)

    ca_hiver_yoy = _prior_season_ca(df, cols, prior_hiver)
    ca_ete_yoy = _prior_season_ca(df, cols, prior_ete)
    ca_year_yoy_extract = _ca_confirme(df, cols, prior.start, prior.end)
    ca_year_yoy = (
        ca_year_yoy_extract if ca_year_yoy_extract > 0 else (ca_hiver_yoy + ca_ete_yoy)
    )

    dossiers_conf = _unique_confirmed_clients(df, cols, fy.start, metrics_end)
    dossiers_prop = _unique_clients_any_status(df, cols, fy.start, metrics_end)
    taux = (dossiers_conf / dossiers_prop) if dossiers_prop else 0.0
    pdv_med = _median_pdv_per_client(df, cols, fy.start, metrics_end)

    dossiers_conf_yoy, _dossiers_prop_yoy, taux_yoy, pdv_med_yoy = _prior_year_volume_metrics(
        df, cols, prior, ca_prior_year=ca_year_yoy
    )

    top5, top10 = _client_concentration(df, cols, fy.start, metrics_end)
    by_ca, by_qty = compute_top_prestations(df, cols, fy.start, metrics_end)

    marge_avg = _average_marge_reelle_pct(marge_df, fy.start, metrics_end)

    if cdp_table is not None and not cdp_table.empty:
        top_cdp = cdp_table.head(TOP_CDP_N).copy()
    else:
        top_cdp = pd.DataFrame()

    result = AnnualKpiResult(
        as_of=as_of,
        fiscal_year=fy,
        prior_fiscal_year=prior,
        hiver=hiver,
        ete=ete,
        metrics_end=metrics_end,
        ca_confirme_annee=ca_year,
        ca_confirme_annee_yoy=ca_year_yoy,
        dossiers_confirmes=dossiers_conf,
        dossiers_confirmes_yoy=dossiers_conf_yoy,
        dossiers_proposes=dossiers_prop,
        taux_conversion=taux,
        taux_conversion_yoy=taux_yoy,
        pdv_median_client=pdv_med,
        pdv_median_client_yoy=pdv_med_yoy,
        marge_reelle_moyenne_pct=marge_avg,
        ca_hiver=ca_hiver,
        ca_hiver_yoy=ca_hiver_yoy,
        ca_ete=ca_ete,
        ca_ete_yoy=ca_ete_yoy,
        top5_client_share=top5,
        top10_client_share=top10,
        top_prestations_by_ca=by_ca,
        top_prestations_by_qty=by_qty,
        top_cdp=top_cdp,
        validation={
            "fy": fy.label,
            "metrics_end": str(metrics_end),
            "ca_year": ca_year,
            "ca_year_yoy": ca_year_yoy,
            "ca_hiver_yoy": ca_hiver_yoy,
            "ca_ete_yoy": ca_ete_yoy,
            "dossiers_confirmes_yoy": dossiers_conf_yoy,
            "prestations_by_ca": len(by_ca),
            "prestations_by_qty": len(by_qty),
        },
    )
    result.insights = _build_insights(result)
    logger.info(
        "Annual KPIs %s (as_of=%s): CA=%.0f (N-1=%.0f) dossiers_conf=%d (N-1=%d)",
        fy.label,
        as_of,
        ca_year,
        ca_year_yoy,
        dossiers_conf,
        dossiers_conf_yoy,
    )
    return result

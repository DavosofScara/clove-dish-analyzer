"""
Section 3 for the CDP weekly email (EVO2_CDP_WEEKLY_REPORT).

Team-wide pipeline, mix, margin, and named client/agent lists (no CDP column).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

import pandas as pd

from .cdp_section3_metrics import ClientAgentRow, compute_cdp_section3_metrics
from .config import THEME_BORDER, THEME_DARK, THEME_MUTED, THEME_TABLE_DIVIDER, THEME_TEXT
from .email_template import _dossier_metric_card, format_currency, format_int, format_percent
from .weekly_kpis import WeeklyKpiResult


def _fmt_date(d: Optional[date]) -> str:
    if not d:
        return "—"
    return d.strftime("%d/%m/%Y")


def _section_subheader(title: str, period_line: str) -> str:
    """Group title + single date/period line (cards omit repeated dates)."""
    return f"""
              <div style="color:{THEME_MUTED};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;">
                {title}
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">{period_line}</div>"""


def _metric_card_row(
    cards: List[tuple],
    *,
    columns: int,
    uniform_height: bool = False,
) -> str:
    """``cards``: list of (title, value) or (title, value, period_line). Matches section 1 cards."""
    cells = ""
    width = f"{100 / columns:.2f}%"
    for item in cards:
        if len(item) == 2:
            title, value = item
            period = ""
        else:
            title, value, period = item
        cells += _dossier_metric_card(
            title=title,
            value=value,
            period_line=period,
            uniform_height=uniform_height,
        ).replace('width="33.33%"', f'width="{width}"')
    return f"<tr>{cells}</tr>"


def _metric_card_table(rows: List[tuple]) -> str:
    """``rows``: list of (cards, columns) or (cards, columns, uniform_height)."""
    body = ""
    for row in rows:
        if len(row) == 3:
            cards, cols, uniform = row
        else:
            cards, cols = row
            uniform = False
        body += _metric_card_row(cards, columns=cols, uniform_height=uniform)
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="border-collapse:collapse;">{body}</table>'
    )


def _simple_table(
    headers: List[str],
    rows: List[List[str]],
    *,
    right_align_from: int = 1,
) -> str:
    th = (
        f"padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};"
        f"color:{THEME_MUTED};font-size:12px;font-weight:500;"
    )
    head = "<thead><tr>"
    for i, h in enumerate(headers):
        align = "right" if i >= right_align_from else "left"
        head += f'<th align="{align}" style="{th}">{h}</th>'
    head += "</tr></thead><tbody>"
    td_base = f"padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:{THEME_TEXT};"
    body = ""
    for row in rows:
        body += "<tr>"
        for i, cell in enumerate(row):
            align = "right" if i >= right_align_from else "left"
            body += f'<td style="{td_base}text-align:{align};">{cell}</td>'
        body += "</tr>"
    if not rows:
        body += (
            f'<tr><td colspan="{len(headers)}" style="{td_base}text-align:center;color:{THEME_MUTED};">'
            "Aucune donnée</td></tr>"
        )
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="border-radius:10px;background-color:{THEME_DARK};border:1px solid {THEME_BORDER};'
        f'border-collapse:collapse;">{head}{body}</tbody></table>'
    )


def _client_agent_table(
    title: str,
    subtitle: str,
    rows: List[ClientAgentRow],
    *,
    show_date_op: bool,
    show_stagnant_days: bool,
) -> str:
    headers = ["Client", "Agent", "PDV (HT)"]
    if show_date_op:
        headers.append("Date opération")
    if show_stagnant_days:
        headers.append("Jours sans suite")
    data: List[List[str]] = []
    for r in rows:
        line = [r.client, r.agent, format_currency(r.pdv)]
        if show_date_op:
            line.append(_fmt_date(r.date_operation))
        if show_stagnant_days:
            line.append(str(r.days_stagnant) if r.days_stagnant is not None else "—")
        data.append(line)
    return f"""
              <div style="color:{THEME_MUTED};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-top:16px;margin-bottom:4px;">
                {title}
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">{subtitle}</div>
              {_simple_table(headers, data, right_align_from=2)}
    """


def build_cdp_weekly_section3_html(
    df: pd.DataFrame,
    kpi: WeeklyKpiResult,
    as_of: date,
    *,
    client_db: pd.DataFrame,
    marge_df: pd.DataFrame,
) -> str:
    season_label = kpi.current_season.label
    season_period = (
        f"{kpi.current_season.start.strftime('%d/%m/%Y')} – "
        f"{kpi.current_season.end.strftime('%d/%m/%Y')}, {season_label}"
    )
    ref_week = (
        f"{kpi.week_start.strftime('%d/%m/%Y')} – {kpi.week_end.strftime('%d/%m/%Y')}"
    )

    metrics = compute_cdp_section3_metrics(
        df,
        kpi,
        as_of,
        client_db=client_db,
        marge_df=marge_df,
    )

    cards_semaine = _metric_card_table(
        [
            (
                [
                    ("Dossiers confirmés", format_int(kpi.dossiers_confirme_semaine)),
                    ("CA réalisé (HT)", format_currency(kpi.ca_realise_semaine)),
                    (
                        "PDV médian / client",
                        format_currency(metrics.median_pdv_confirme_semaine),
                    ),
                ],
                3,
            ),
        ]
    )

    cards_saison = _metric_card_table(
        [
            (
                [
                    ("Dossiers confirmés", format_int(kpi.dossiers_confirme_saison)),
                    ("Dossiers EN COURS", format_int(metrics.en_cours_clients)),
                    ("EN COURS stagnants", format_int(metrics.stagnant_clients)),
                    ("Taux de confirmation", format_percent(metrics.season_taux_confirmation)),
                ],
                4,
                True,
            ),
            (
                [
                    ("CA confirmé (saison)", format_currency(kpi.ca_realise_saison)),
                    (
                        "Marge confirmée",
                        format_currency(metrics.season_marge_confirme_eur),
                    ),
                    (
                        "Marge finale (%)",
                        format_percent(metrics.season_marge_final_pct)
                        if metrics.season_marge_final_pct is not None
                        else "—",
                    ),
                    (
                        "Marge réelle",
                        format_currency(metrics.season_marge_reelle_eur),
                    ),
                ],
                4,
                True,
            ),
        ]
    )

    upcoming_sub = (
        "EN COURS · Date_opération entre aujourd’hui et J+30 · top par PDV (HT)"
    )
    stagnant_sub = (
        "EN COURS · Date_Demande ≥ 30 j · top par PDV (HT) · sans CDP"
    )

    agent_rows = [
        [name, format_int(n), format_currency(pdv)]
        for name, n, pdv in metrics.top_agents_en_cours
    ]
    agents_html = f"""
              <div style="margin-top:16px;">
              {_section_subheader("Top agents — PDV EN COURS", season_period)}
              </div>
              {_simple_table(["Agent", "Dossiers", "PDV total (HT)"], agent_rows, right_align_from=1)}
    """

    site_table_rows = [
        [
            r.site,
            format_percent(r.taux_confirmation),
            format_currency(r.marge_confirme_eur),
            f"{r.marge_pct_avg:.1f} %",
            format_currency(r.ca_confirme_pdv),
        ]
        for r in metrics.site_season_table
    ]

    return f"""
          <tr>
            <td style="padding-top:4px;padding-bottom:8px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">
                3. Indicateurs commerciaux
              </div>

              {_section_subheader("Semaine", ref_week)}
              {cards_semaine}

              <div style="margin-top:14px;">
              {_section_subheader("Saison", season_period)}
              </div>
              {cards_saison}

              {_client_agent_table(
                  "Gros dossiers EN COURS — échéance sous 30 jours",
                  upcoming_sub,
                  metrics.list_upcoming,
                  show_date_op=True,
                  show_stagnant_days=False,
              )}

              {_client_agent_table(
                  "Gros dossiers EN COURS — stagnants",
                  stagnant_sub,
                  metrics.list_stagnant,
                  show_date_op=True,
                  show_stagnant_days=True,
              )}

              {agents_html}

              <div style="margin-top:20px;">
              {_section_subheader("Mix CA confirmé par type de client (%)", season_period)}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{metrics.chart_type_mix_uri}" alt="Mix type de client" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>

              <div style="margin-top:18px;">
              {_section_subheader(
                  "Top 5 sites — marge % (moyenne)",
                  f"{season_period} · Marge_Reelle_Devis · SITE (extract)",
              )}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{metrics.chart_site_marge_pct_uri}" alt="Marge % par site" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>

              <div style="margin-top:18px;">
              {_section_subheader(
                  "Chiffre d'affaires (PDV_DEVIS_CONFIRME) par site",
                  f"Mêmes 5 sites · {season_label}",
              )}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{metrics.chart_site_ca_confirme_uri}" alt="CA confirmé par site" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
              <div style="margin-top:10px;">
                {_simple_table(
                    [
                        "Site",
                        "Taux conf.",
                        "Marge confirmée (€)",
                        "Marge % moy.",
                        "CA confirmé (HT)",
                    ],
                    site_table_rows,
                    right_align_from=1,
                )}
              </div>
            </td>
          </tr>"""


def cdp_weekly_section3_definitions_html(kpi: WeeklyKpiResult) -> str:
    """HTML fragment for the email « Définitions » block (section 3)."""
    ss = kpi.current_season.start.strftime("%d/%m/%Y")
    se = kpi.current_season.end.strftime("%d/%m/%Y")
    return (
        f"<strong>3. Indicateurs commerciaux.</strong> "
        f"<em>Semaine</em> : semaine KPI section 1 ; confirmés = DATE CONFIRME Clients dans la semaine ; "
        f"<em>CA réalisé</em> = somme <code>PDV_DEVIS_CONFIRME</code> (CONFIRMÉ) avec "
        f"<code>Date_opération</code> dans la semaine (événements de la semaine) ; "
        f"PDV médian = médiane du PDV confirmé par <code>CLIENT_ID</code> pour les clients confirmés "
        f"cette semaine (DATE CONFIRME). "
        f"<em>Saison</em> — ligne 1 : confirmés (saison, <code>Date_opération</code>), "
        f"dossiers <strong>EN COURS</strong> ({ss} – {se}), stagnants "
        f"(<code>Date_Demande</code> ≥ 30 j), taux de confirmation ; ligne 2 : "
        f"<em>CA confirmé (saison)</em> = somme <code>PDV_DEVIS_CONFIRME</code> (CONFIRMÉ), "
        f"<code>Date_opération</code> sur toute la saison calendaire ({ss} – {se}) ; "
        f"<em>Marge confirmée</em> = Σ <code>MARGE_FINAL_EVENTS</code> (extract, CONFIRMÉ) ; "
        f"<em>Marge finale (%)</em> = 100 × Σ <code>MARGE_FINAL_EVENTS</code> ÷ "
        f"Σ <code>PDV_DEVIS_CONFIRME</code> (même périmètre) ; "
        f"<em>Marge réelle</em> = Σ <code>MARGE_EVENTS_REELLE</code> "
        f"(<code>Marge_Reelle_Devis</code>, <code>ALL_LINES_VALIDE</code>, saison calendaire). "
        f"<em>Top 5 sites</em> (graphiques &amp; tableau) : classés par CA confirmé saison "
        f"(comme section 4), pas par marge % seule. "
        f"Échéance sous 30 j = <code>Date_opération</code> entre la date du rapport et J+30. "
        f"Listes nommées : client + agent uniquement (pas de CDP). "
        f"Top agents : <code>NOM_AGENT</code>, PDV EN COURS agrégé. "
        f"<em>Taux de confirmation (saison)</em> : total puis par site ; "
        f"<code>CLIENT_ID</code> distincts avec <code>Date_opération</code> en saison — confirmés ÷ actifs. "
        f"<em>Marge confirmée (€) par site</em> (tableau / graphiques) : "
        f"<code>Marge_Reelle_Devis</code> (<code>ALL_LINES_VALIDE</code>), par site. "
        f"<em>Marge % moyenne</em> : moyenne simple des % marge ÷ PDV par ligne, par site "
        f"(sites sans ligne marge : 0 %). "
        f"<em>CA confirmé par site</em> : somme <code>PDV_DEVIS_CONFIRME</code> "
        f"(CONFIRMÉ, <code>Date_opération</code> sur la saison calendaire), regroupement <code>SITE</code>. "
        f"Graphiques site : mêmes 5 sites que le tableau.<br/><br/>"
    )

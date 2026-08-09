from __future__ import annotations

import base64
from pathlib import Path
from typing import List, Optional, Tuple

from .config import (
    CLOVE_GREEN_DARK,
    THEME_BORDER,
    THEME_DARK,
    THEME_MUTED,
    THEME_TABLE_DIVIDER,
    THEME_TEXT,
)
from .weekly_kpis import WeeklyKpiResult

# Placeholder until historical YoY series; week-row confirmés still not shown.
_KPI_PLACEHOLDER = "-"


def _load_logo_base64(path: Path) -> str | None:
    if not path or not path.exists():
        return None
    data = path.read_bytes()
    return base64.b64encode(data).decode("utf-8")


def format_currency(value: float) -> str:
    if value is None:
        return "0 €"
    return f"{int(round(value)):,} €".replace(",", " ")


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_int(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _table_rows(rows: List[List[Tuple[str, Optional[float]]]]) -> str:
    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    max_values = [None] * col_count
    for idx in range(col_count):
        nums = [r[idx][1] for r in rows if idx < len(r) and r[idx][1] is not None]
        max_values[idx] = max(nums) if nums else None

    out = ""
    for row in rows:
        out += "<tr>"
        for i, cell in enumerate(row):
            align = "left" if i == 0 else "right"
            text, num = cell
            if num is None:
                color = THEME_TEXT
            else:
                max_val = max_values[i]
                color = THEME_TEXT if (max_val is not None and num == max_val and max_val != 0) else "#e2e5eb"
            out += (
                f'<td style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};'
                f'color:{color};text-align:{align};">{text}</td>'
            )
        out += "</tr>"
    return out


def _kpi_metric_table(rows: List[Tuple[str, str, str, str]]) -> str:
    """
    Sections 1–2: Libellé | Période actuelle | N-1 (YoY) | Écart.
    YoY/Écart use _KPI_PLACEHOLDER until historical data is available.
    """
    th = (
        f'padding:8px 10px;border-bottom:1px solid {THEME_TABLE_DIVIDER};'
        f"color:{THEME_MUTED};font-size:12px;font-weight:500;"
    )
    head = (
        "<thead><tr>"
        f'<th align="left" style="{th}">Libellé</th>'
        f'<th align="right" style="{th}">Période actuelle</th>'
        f'<th align="right" style="{th}">N-1 (YoY)</th>'
        f'<th align="right" style="{th}">Écart</th>'
        "</tr></thead><tbody>"
    )
    td_l = (
        f"padding:10px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:#e2e5eb;"
    )
    td_cur = (
        f"padding:10px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};"
        f"text-align:right;font-weight:600;color:{THEME_TEXT};"
    )
    td_ph = (
        f"padding:10px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};"
        f"text-align:right;color:{THEME_MUTED};"
    )
    parts = [head]
    for label, cur, yoy, delta in rows:
        parts.append(
            "<tr>"
            f'<td style="{td_l}">{label}</td>'
            f'<td style="{td_cur}">{cur}</td>'
            f'<td style="{td_ph}">{yoy}</td>'
            f'<td style="{td_ph}">{delta}</td>'
            "</tr>"
        )
    parts.append("</tbody>")
    return "".join(parts)


def _dossier_metric_card(
    *,
    title: str,
    value: str,
    period_line: str,
) -> str:
    """Single metric card for the dossier grid (French client-facing labels)."""
    return f"""
                <td width="33.33%" valign="top" style="padding:4px;">
                  <div style="background-color:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:14px 12px;text-align:center;">
                    <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;line-height:1.3;">{title}</div>
                    <div style="color:{THEME_TEXT};font-size:26px;font-weight:700;margin-top:8px;line-height:1.2;">{value}</div>
                    <div style="color:{THEME_MUTED};font-size:10px;margin-top:8px;line-height:1.35;">{period_line}</div>
                  </div>
                </td>"""


def build_dossier_kpi_cards_html(kpi: WeeklyKpiResult, week_range_label: str) -> str:
    """
    2×3 grid: row Semaine = réalisés / propositions envoyées / confirmés; row Saison = same.
    Reading down a column compares week vs season for one category.
    """
    season_report_start = kpi.current_season.start.strftime("%d/%m/%Y")
    season_report_end = kpi.season_metrics_end.strftime("%d/%m/%Y")
    season_full_start = kpi.current_season.start.strftime("%d/%m/%Y")
    season_full_end = kpi.current_season.end.strftime("%d/%m/%Y")

    period_semaine = f"Semaine: {week_range_label}"
    period_saison_real = f"Saison: {season_report_start} – {season_report_end}"
    period_saison_prop = f"Saison: {season_full_start} – {season_full_end}"
    period_saison_conf = f"Saison: {season_full_start} – {season_full_end}"

    row_sem = (
        "<tr>"
        + _dossier_metric_card(
            title="Dossiers réalisés",
            value=format_int(kpi.dossiers_realise_semaine),
            period_line=period_semaine,
        )
        + _dossier_metric_card(
            title="Propositions envoyées",
            value=format_int(kpi.dossiers_propose_semaine),
            period_line=period_semaine,
        )
        + _dossier_metric_card(
            title="Dossiers confirmés",
            value=format_int(kpi.dossiers_confirme_semaine),
            period_line=period_semaine,
        )
        + "</tr>"
    )

    row_sai = (
        "<tr>"
        + _dossier_metric_card(
            title="Dossiers réalisés",
            value=format_int(kpi.dossiers_realise_saison),
            period_line=period_saison_real,
        )
        + _dossier_metric_card(
            title="Propositions envoyées",
            value=format_int(kpi.dossiers_propose_saison),
            period_line=period_saison_prop,
        )
        + _dossier_metric_card(
            title="Dossiers confirmés",
            value=format_int(kpi.dossiers_confirme_saison),
            period_line=period_saison_conf,
        )
        + "</tr>"
    )

    return f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                <tr>
                  <td colspan="3" style="padding:0 4px 8px 4px;color:{THEME_MUTED};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;">Semaine</td>
                </tr>
                {row_sem}
                <tr>
                  <td colspan="3" style="padding:16px 4px 8px 4px;color:{THEME_MUTED};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;">Saison</td>
                </tr>
                {row_sai}
              </table>"""


def _kpi_ca_rows(kpi: WeeklyKpiResult) -> str:
    d = _KPI_PLACEHOLDER
    rows = [
        ("Chiffre d'affaires réalisé HT (semaine)", format_currency(kpi.ca_realise_semaine), d, d),
        ("Chiffre d'affaires confirmé HT (saison en cours)", format_currency(kpi.ca_realise_saison), d, d),
        (
            f"CA prévisionnel HT — {kpi.current_season.label} (En cours)",
            format_currency(kpi.ca_provisionnel_saison_cours),
            d,
            d,
        ),
        (
            f"CA prévisionnel HT — {kpi.next_season.label} (saison suivante)",
            format_currency(kpi.ca_provisionnel_saison_suivante),
            d,
            d,
        ),
    ]
    return _kpi_metric_table(rows)


def _cdp_conversion_section_html(
    *,
    section_id: str,
    scope_label: str,
    period_label: str,
    cdp_tbody: str,
    chart_scatter_uri: str,
    chart_margin_uri: str,
) -> str:
    return f"""
          <tr>
            <td style="padding-top:4px;padding-bottom:8px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">
                {section_id}. Conversion par CDP — {scope_label}
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">
                {period_label}
              </div>
              <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">
                Tableau conversion par CDP — {scope_label}
              </div>
              <table width="100%" cellspacing="0" cellpadding="0" style="border-radius:10px;background-color:{THEME_DARK};border:1px solid {THEME_BORDER};border-collapse:collapse;">
                <thead>
                  <tr>
                    <th align="left" style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:{THEME_MUTED};font-size:12px;font-weight:500;">CDP</th>
                    <th align="right" style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:{THEME_MUTED};font-size:12px;font-weight:500;">Clients</th>
                    <th align="right" style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:{THEME_MUTED};font-size:12px;font-weight:500;">Taux conf.</th>
                    <th align="right" style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:{THEME_MUTED};font-size:12px;font-weight:500;">PDV conf.</th>
                    <th align="right" style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:{THEME_MUTED};font-size:12px;font-weight:500;">PDV médian</th>
                  </tr>
                </thead>
                <tbody>
                  {cdp_tbody}
                </tbody>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding-top:6px;padding-bottom:14px;">
              <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">
                Conversion vs valeur par CDP — {scope_label}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{chart_scatter_uri}" alt="Conversion vs valeur par CDP — {scope_label}" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:6px;padding-bottom:18px;">
              <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">
                Marge budget vs réelle par CDP — {scope_label}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{chart_margin_uri}" alt="Marge budget vs réelle par CDP — {scope_label}" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>"""


def build_weekly_email_html(
    clove_logo_path: Path | None,
    evo2_logo_path: Path | None,
    kpi: WeeklyKpiResult,
    cdp_season_rows: List[List[Tuple[str, Optional[float]]]],
    cdp_season_period_label: str,
    chart_scatter_season_uri: str,
    chart_margin_season_uri: str,
    cdp_year_rows: List[List[Tuple[str, Optional[float]]]],
    cdp_year_period_label: str,
    fiscal_year_start: str,
    fiscal_year_end: str,
    chart_scatter_year_uri: str,
    chart_margin_year_uri: str,
    chart_cumulative_yoy_uri: str,
    chart_site_bars_uri: str,
    site_chart_period_label: str,
    chart_site_bars_next_uri: str,
    site_chart_next_period_label: str,
    dropbox_url: str,
    week_range_label: str,
) -> str:
    clove_logo = _load_logo_base64(clove_logo_path) if clove_logo_path else None
    evo2_logo = _load_logo_base64(evo2_logo_path) if evo2_logo_path else None

    clove_img_html = (
        f'<img src="data:image/png;base64,{clove_logo}" alt="" style="height:32px;" />'
        if clove_logo
        else ""
    )
    evo2_img_html = (
        f'<img src="data:image/png;base64,{evo2_logo}" alt="Evolution2" style="height:32px;" />'
        if evo2_logo
        else '<span style="color:#f5f5f5;font-weight:600;">Evolution2</span>'
    )

    dossier_cards_html = build_dossier_kpi_cards_html(kpi, week_range_label)
    ca_table = _kpi_ca_rows(kpi)
    cdp_season_tbody = _table_rows(cdp_season_rows)
    cdp_year_tbody = _table_rows(cdp_year_rows)
    cdp_season_html = _cdp_conversion_section_html(
        section_id="3.1",
        scope_label="Saison en cours",
        period_label=cdp_season_period_label,
        cdp_tbody=cdp_season_tbody,
        chart_scatter_uri=chart_scatter_season_uri,
        chart_margin_uri=chart_margin_season_uri,
    )
    cdp_year_html = _cdp_conversion_section_html(
        section_id="3.2",
        scope_label="Année en cours",
        period_label=cdp_year_period_label,
        cdp_tbody=cdp_year_tbody,
        chart_scatter_uri=chart_scatter_year_uri,
        chart_margin_uri=chart_margin_year_uri,
    )

    proposed_season_start = kpi.current_season.start.strftime("%d/%m/%Y")
    proposed_season_end = kpi.current_season.end.strftime("%d/%m/%Y")
    next_season_start = kpi.next_season.start.strftime("%d/%m/%Y")
    next_season_end = kpi.next_season.end.strftime("%d/%m/%Y")

    sm_start = kpi.current_season.start.strftime("%d/%m/%Y")
    sm_end = kpi.season_metrics_end.strftime("%d/%m/%Y")
    report_date_label = kpi.season_metrics_end.strftime("%d/%m/%Y")
    week_end_label = kpi.week_end.strftime("%d/%m/%Y")

    definitions_html = f"""
                <div style="font-size:11px;line-height:1.65;color:#e2e5eb;">
                  <strong>Source.</strong> Feuille <code>extract_devis</code> (Evolution2_Report_V13.xlsm) ; enrichissement <code>TYPE_DE_CLIENT</code> et <code>DATE CONFIRME</code> via la base Clients (feuille Excel configurée côté pipeline, ex. <code>CLIENTS</code>), jointure NOM_CLIENT + NOM_AGENT.<br/><br/>

                  <strong>Semaine de référence.</strong> Lundi–dimanche, celle qui se termine au <strong>dernier dimanche ≤ date du rapport</strong> (un lundi matin = dimanche d’hier ; un dimanche = ce même dimanche, pas la semaine d’avant).<br/><br/>

                  <strong>Saisons (calendrier fiscal).</strong> HIVER : 01/10–30/04. ÉTÉ : 01/05–30/09.<br/><br/>

                  <strong>1. Dossiers.</strong> Un dossier = un <code>CLIENT_ID</code> distinct.
                  <em>Réalisés (saison)</em> : confirmés, <code>Date_opération</code> du début de saison au <strong>min(date du rapport, fin de saison)</strong> ({sm_start} – {sm_end} pour ce rapport).
                  <em>Confirmés (saison)</em> : confirmés, <code>Date_opération</code> sur toute la <strong>saison calendaire</strong> ({proposed_season_start} – {proposed_season_end}) — approximation en l’absence d’une date de confirmation dédiée.
                  <em>Semaine</em> : <em>réalisés</em> = confirmés, <code>Date_opération</code> dans la semaine de référence ; <em>confirmés (semaine)</em> = <code>CLIENT_ID</code> distincts sur l’extract dont la clé <strong>NOM_CLIENT + NOM_AGENT</strong> correspond à <strong>au moins une ligne</strong> de la feuille Clients avec <strong>DATE CONFIRME</strong> dans la même semaine (toutes les lignes Clients comptent, pas seulement une ligne « représentative »).
                  <em>Propositions envoyées (semaine)</em> : <code>Date_Demande</code> dans la semaine de référence, tous statuts.
                  <em>Propositions envoyées (saison)</em> : <code>Date_opération</code> sur toute la saison calendaire.
                  <em>N-1 / Écart</em> : « - » en attente d’historique.<br/><br/>

                  <strong>2. Chiffre d’affaires HT.</strong> Tous les montants du tableau (section 2) sont <strong>hors taxes (HT)</strong>. <em>CA réalisé (semaine)</em> : somme <code>PDV_DEVIS_CONFIRME</code> sur lignes confirmées ; <code>Date_opération</code> dans la semaine de référence. <em>CA confirmé (saison en cours)</em> : même somme sur la <strong>saison calendaire complète</strong> ({proposed_season_start} – {proposed_season_end}).
                  <em>CA prévisionnel (En cours)</em> — ligne « {kpi.current_season.label} (En cours) » : <strong>(1)</strong> même base confirmée que le CA confirmé saison (saison calendaire entière).
                  <strong>(2)</strong> + complément pipeline : lignes <strong>EN COURS</strong> (hors annulés), <code>Date_opération</code> du <strong>lendemain</strong> de <code>min(dimanche semaine terminée, fin de saison)</code> jusqu’à la <strong>fin de saison</strong> ; par <code>CLIENT_ID</code> : somme <code>PDV_DEVIS</code> ÷ <code>DEVIS_ID</code> distincts, puis somme des clients.
                  <em>CA prévisionnel (saison suivante)</em> — ligne « {kpi.next_season.label} (saison suivante) » : mêmes règles sur ({next_season_start} – {next_season_end}).
                  <em>Coupe des dates</em> : le CA prévisionnel utilise le <strong>dimanche de fin de semaine de référence</strong> ({week_end_label}) pour la fenêtre EN COURS ; les dossiers réalisés (saison) et la <strong>ligne épaisse</strong> du graphique CA cumulé utilisent la <strong>date du rapport</strong> ({report_date_label}) — ces deux dates peuvent différer si le rapport est produit en milieu de semaine.<br/><br/>

                  <strong>Graphique — CA cumulé (sous le tableau, section 2).</strong> Trois courbes, toutes en <strong>CA confirmé HT</strong> cumulé par <code>Date_opération</code> (<code>PDV_DEVIS_CONFIRME</code>, CONFIRMÉ). Axe = calendrier de la <strong>saison en cours</strong> ({proposed_season_start} – {proposed_season_end}).
                  <strong>Ligne épaisse (vert)</strong> — <em>réalisé à date du rapport</em> ({report_date_label}) : événements déjà datés jusqu’à cette date (aligné avec les dossiers réalisés saison).
                  <strong>Ligne fine (vert clair)</strong> — <em>confirmé saison entière</em> : même base que la ligne du tableau « CA confirmé (saison en cours) » ({proposed_season_start} – {proposed_season_end}, y compris <code>Date_opération</code> futures dans l’extract).
                  <strong>Ligne grise</strong> — N-1 de <strong>même type</strong> (HIVER vs HIVER, ÉTÉ vs ÉTÉ), saison précédente entière, <strong>alignée</strong> sur le calendrier relatif de la saison en cours. Pour <strong>ÉTÉ 25</strong>, N-1 provient de <code>ete_2025_definitive.csv</code> ; les autres saisons N-1 restent sur l’extract V13.<br/><br/>

                  <strong>3. Conversion CDP.</strong> Même métriques pour 3.1 et 3.2 : lignes de l’extract filtrées par <code>Date_opération</code> dans la période indiquée ; par CDP (top 8 par PDV confirmé) : clients uniques, taux de confirmation, somme <code>PDV_DEVIS</code> sur lignes confirmées (« PDV conf. »), PDV médian par client ; le nuage (X = taux, Y = médian, surface ∝ PDV confirmé) reprend ces agrégats.
                  <strong>3.1 — Saison en cours</strong> : <code>Date_opération</code> sur la <strong>saison calendaire complète</strong> ({proposed_season_start} – {proposed_season_end}).
                  <strong>3.2 — Année en cours</strong> : <code>Date_opération</code> sur l’<strong>année fiscale complète</strong> 01/10–30/09 ({fiscal_year_start} – {fiscal_year_end}).
                  <strong>Graphique marge budget vs réelle</strong> (3.1 et 3.2) : feuille <code>Marge_Reelle_Devis</code> (lignes <code>ALL_LINES_VALIDE = True</code>, filtrées par <code>Date_opération</code> sur la même période) ; par CDP, <strong>moyenne simple</strong> de <code>100 × marge € ÷ PDV_DEVIS</code> — budget = <code>MARGE_EVENTS_FINAL_BUDGET</code>, réelle = <code>MARGE_EVENTS_REELLE</code> (marge avant commission partenaire site EVO2). Les graphiques 3.2 utilisent le même vert avec une légère transparence pour les distinguer de 3.1.<br/><br/>

                  <strong>4. PDV par site.</strong> Les statistiques de ces graphiques reposent <strong>uniquement sur les dossiers confirmés</strong> (devis <code>CONFIRME</code> = CONFIRMÉ dans l’extract) — <strong>pas sur les dossiers EN COURS</strong> (contrairement au CA prévisionnel de la section 2). Montant = somme <code>PDV_DEVIS_CONFIRME</code> (HT) par site. Regroupement par la colonne <code>SITE</code> de l’extract (<strong>pas</strong> <code>SITE_EVOLUTION</code>, <code>SITE_EVO2</code> ni CDP). Graphique bleu — <em>Saison en cours</em> : <code>Date_opération</code> sur toute la <strong>saison calendaire</strong> ({proposed_season_start} – {proposed_season_end}). Graphique orange — <em>Saison suivante</em> : <code>Date_opération</code> sur toute la saison suivante ({next_season_start} – {next_season_end}), p. ex. {kpi.next_season.label}.
                </div>
"""

    html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Rapport hebdomadaire – Evolution2</title>
</head>
<body style="margin:0;padding:0;background:#0b0d12;color:{THEME_TEXT};font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0d12;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="700" cellspacing="0" cellpadding="0" style="background:#0f121a;border-radius:14px;padding:22px;border:1px solid {THEME_BORDER};">
          <tr>
            <td style="padding-bottom:12px;border-bottom:1px solid {THEME_BORDER};">
              <table role="presentation" width="100%">
                <tr>
                  <td align="left">{evo2_img_html}</td>
                  <td align="right">{clove_img_html}</td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding-top:16px;padding-bottom:12px;">
              <div style="font-size:20px;font-weight:700;color:{THEME_TEXT};">
                Rapport hebdomadaire – Evolution2
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:8px;padding-bottom:14px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">
                1. Nombre de dossiers
              </div>
              <div style="border-radius:10px;border:1px solid {THEME_BORDER};background-color:#0f121a;padding:12px 4px;">
                  {dossier_cards_html}
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:16px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">
                2. Chiffre d'affaires HT
              </div>
              <table width="100%" cellspacing="0" cellpadding="0" style="border-radius:10px;background-color:{THEME_DARK};border:1px solid {THEME_BORDER};border-collapse:collapse;">
                  {ca_table}
              </table>
              <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-top:14px;margin-bottom:6px;">
                CA réalisé cumulé — réalisé vs confirmé (saison) vs N-1
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{chart_cumulative_yoy_uri}" alt="CA cumulé confirmé — comparaison saison" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          {cdp_season_html}

          {cdp_year_html}

          <tr>
            <td style="padding-top:4px;padding-bottom:12px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                4. PDV confirmé par site
              </div>
              <div style="color:{THEME_MUTED};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">
                Saison en cours
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">
                {site_chart_period_label}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{chart_site_bars_uri}" alt="PDV confirmé par site — saison en cours" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:18px;">
              <div style="color:{THEME_MUTED};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">
                Saison suivante
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">
                {site_chart_next_period_label}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{chart_site_bars_next_uri}" alt="PDV confirmé par site — saison suivante" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:2px;padding-bottom:16px;">
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:12px;color:{THEME_TEXT};">
                <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                  Définitions
                </div>
                {definitions_html}
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:8px;">
              <table role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <a href="{dropbox_url}" target="_blank" style="display:inline-block;background:{THEME_DARK};color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;padding:10px 20px;border-radius:8px;border:2px solid {CLOVE_GREEN_DARK};">
                      Ouvrir le rapport complet
                    </a>
                  </td>
                </tr>
              </table>
              <div style="color:{THEME_MUTED};font-size:11px;margin-top:12px;line-height:1.45;max-width:520px;">
                <strong>Transfert / réponse :</strong> Gmail et d’autres messageries peuvent modifier l’affichage du corps du message.
                Une copie du rapport est jointe au format HTML — ouvrez la pièce jointe dans Chrome, Safari ou Edge pour retrouver la mise en forme et les logos d’origine.
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

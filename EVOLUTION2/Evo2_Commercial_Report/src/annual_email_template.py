"""
French HTML email for the Evolution2 annual commercial report.

Same dark Clove theme as the weekly report; separate template so weekly stays untouched.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import List, Optional, Tuple

from .annual_kpis import AnnualKpiResult
from .config import (
    CLOVE_GREEN_DARK,
    THEME_BORDER,
    THEME_DARK,
    THEME_MUTED,
    THEME_TABLE_DIVIDER,
    THEME_TEXT,
    THEME_TREND_DOWN,
    THEME_TREND_UP,
)
from .email_template import format_currency, format_int, format_percent, _table_rows


def _load_logo_base64(path: Path) -> str | None:
    if not path or not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _format_yoy_cell(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return format_currency(value)


def _pct_delta(current: float, prior: Optional[float]) -> Optional[float]:
    """Relative change (current − prior) / prior. None if prior missing or ~0."""
    if prior is None or abs(prior) < 1e-9:
        return None
    return (current - prior) / prior


def _yoy_delta_html(
    current: float,
    prior: Optional[float],
    *,
    as_points: bool = False,
    suffix: str = "vs N-1",
) -> str:
    """
    Colored YoY line for cards / table.
    - Relative % for amounts & counts (``as_points=False``).
    - Percentage-point delta for rates (``as_points=True``), e.g. conversion.
    """
    if as_points:
        if prior is None:
            return f'<span style="color:{THEME_MUTED};">—</span>'
        delta = (current - prior) * 100.0
        if abs(delta) < 0.05:
            return f'<span style="color:{THEME_MUTED};">0.0 pts {suffix}</span>'.rstrip()
        color = THEME_TREND_UP if delta > 0 else THEME_TREND_DOWN
        sign = "+" if delta > 0 else "−"
        text = f"{sign}{abs(delta):.1f} pts {suffix}".rstrip()
        return f'<span style="color:{color};font-weight:600;">{text}</span>'

    pct = _pct_delta(current, prior)
    if pct is None:
        return f'<span style="color:{THEME_MUTED};">—</span>'
    if abs(pct) < 0.0005:
        text = f"0.0 % {suffix}".rstrip()
        return f'<span style="color:{THEME_MUTED};">{text}</span>'
    color = THEME_TREND_UP if pct > 0 else THEME_TREND_DOWN
    sign = "+" if pct > 0 else "−"
    text = f"{sign}{abs(pct) * 100:.1f} % {suffix}".rstrip()
    return f'<span style="color:{color};font-weight:600;">{text}</span>'


def _format_ecart_cell(current: float, prior: Optional[float]) -> str:
    """€ gap + colored % YoY (same trend colours as cards)."""
    if prior is None:
        return "—"
    delta = current - prior
    if abs(delta) < 0.5:
        euro = format_currency(0)
    else:
        sign = "+" if delta > 0 else "−"
        euro = f"{sign}{format_currency(abs(delta))}"
    pct_html = _yoy_delta_html(current, prior, suffix="")
    # Strip trailing space from empty suffix helper output
    return f"{euro}<br/>{pct_html}"


def _metric_card(*, title: str, value: str, subtitle_html: str) -> str:
    return f"""
                <td width="33.33%" valign="top" style="padding:4px;">
                  <div style="background-color:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:14px 12px;text-align:center;">
                    <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;line-height:1.3;">{title}</div>
                    <div style="color:{THEME_TEXT};font-size:24px;font-weight:700;margin-top:8px;line-height:1.2;">{value}</div>
                    <div style="font-size:12px;margin-top:8px;line-height:1.35;">{subtitle_html}</div>
                  </div>
                </td>"""


def _hero_cards_html(kpi: AnnualKpiResult) -> str:
    marge_val = (
        f"{kpi.marge_reelle_moyenne_pct:.1f} %"
        if kpi.marge_reelle_moyenne_pct is not None
        else "—"
    )

    # YoY on cards where N-1 is meaningful. No YoY for marge (data uncertain) or concentration.
    row1 = (
        "<tr>"
        + _metric_card(
            title="CA confirmé HT",
            value=format_currency(kpi.ca_confirme_annee),
            subtitle_html=_yoy_delta_html(kpi.ca_confirme_annee, kpi.ca_confirme_annee_yoy),
        )
        + _metric_card(
            title="Dossiers confirmés",
            value=format_int(kpi.dossiers_confirmes),
            subtitle_html=_yoy_delta_html(
                float(kpi.dossiers_confirmes),
                float(kpi.dossiers_confirmes_yoy)
                if kpi.dossiers_confirmes_yoy is not None
                else None,
            ),
        )
        + _metric_card(
            title="Taux de conversion",
            value=format_percent(kpi.taux_conversion),
            subtitle_html=_yoy_delta_html(
                kpi.taux_conversion,
                kpi.taux_conversion_yoy,
                as_points=True,
            ),
        )
        + "</tr>"
    )
    row2 = (
        "<tr>"
        + _metric_card(
            title="PDV médian / client",
            value=format_currency(kpi.pdv_median_client),
            subtitle_html=_yoy_delta_html(
                kpi.pdv_median_client, kpi.pdv_median_client_yoy
            ),
        )
        + _metric_card(
            title="Marge réelle moyenne",
            value=marge_val,
            subtitle_html=f'<span style="color:{THEME_MUTED};">Année en cours</span>',
        )
        + _metric_card(
            title="Concentration top 5",
            value=format_percent(kpi.top5_client_share),
            subtitle_html=(
                f'<span style="color:{THEME_MUTED};">'
                f"Top 10 : {format_percent(kpi.top10_client_share)}</span>"
            ),
        )
        + "</tr>"
    )
    return f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                {row1}
                {row2}
              </table>"""


def _ca_table_html(kpi: AnnualKpiResult) -> str:
    th = (
        f"padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};"
        f"color:{THEME_MUTED};font-size:12px;font-weight:500;"
    )
    rows = [
        (
            f"CA confirmé HT — {kpi.fiscal_year.label}",
            kpi.ca_confirme_annee,
            kpi.ca_confirme_annee_yoy,
        ),
        (
            f"CA confirmé HT — {kpi.hiver.label}",
            kpi.ca_hiver,
            kpi.ca_hiver_yoy,
        ),
        (
            f"CA confirmé HT — {kpi.ete.label}",
            kpi.ca_ete,
            kpi.ca_ete_yoy,
        ),
    ]
    body = ""
    for label, cur, yoy in rows:
        body += (
            "<tr>"
            f'<td style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:#f5f5f5;text-align:left;">{label}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:{THEME_TEXT};text-align:right;white-space:nowrap;">{format_currency(cur)}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:#e2e5eb;text-align:right;white-space:nowrap;">{_format_yoy_cell(yoy)}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};color:#e2e5eb;text-align:right;white-space:nowrap;line-height:1.45;">{_format_ecart_cell(cur, yoy)}</td>'
            "</tr>"
        )
    return f"""
              <table width="100%" cellspacing="0" cellpadding="0" style="border-radius:10px;background-color:{THEME_DARK};border:1px solid {THEME_BORDER};border-collapse:collapse;">
                <thead><tr>
                  <th align="left" style="{th}">Libellé</th>
                  <th align="right" style="{th}">Période actuelle</th>
                  <th align="right" style="{th}">N-1</th>
                  <th align="right" style="{th}">Écart</th>
                </tr></thead>
                <tbody>{body}</tbody>
              </table>"""


def _insights_html(insights: List[str]) -> str:
    if not insights:
        return ""
    items = "".join(
        f'<li style="margin:0 0 8px 0;color:#e2e5eb;font-size:13px;line-height:1.45;">{t}</li>'
        for t in insights
    )
    return f"""
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:14px 16px 6px 16px;">
                <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">
                  Points clés
                </div>
                <ul style="margin:0;padding-left:18px;">{items}</ul>
              </div>"""


def _prestation_table_html(rows: List[List[Tuple[str, Optional[float]]]]) -> str:
    tbody = _table_rows(rows)
    th = (
        f"padding:8px 12px;border-bottom:1px solid {THEME_TABLE_DIVIDER};"
        f"color:{THEME_MUTED};font-size:12px;font-weight:500;"
    )
    return f"""
              <table width="100%" cellspacing="0" cellpadding="0" style="border-radius:10px;background-color:{THEME_DARK};border:1px solid {THEME_BORDER};border-collapse:collapse;">
                <thead><tr>
                  <th align="left" style="{th}">Prestation</th>
                  <th align="right" style="{th}">CA conf. HT</th>
                  <th align="right" style="{th}">Quantité</th>
                  <th align="right" style="{th}">Lignes</th>
                </tr></thead>
                <tbody>{tbody}</tbody>
              </table>"""


def build_annual_email_html(
    *,
    clove_logo_path: Path | None,
    evo2_logo_path: Path | None,
    kpi: AnnualKpiResult,
    chart_cumulative_uri: str,
    chart_prestation_ca_uri: str,
    chart_prestation_qty_uri: str,
    chart_site_uri: str,
    site_period_label: str,
    cdp_rows: List[List[Tuple[str, Optional[float]]]],
    dropbox_url: str,
) -> str:
    clove_logo = _load_logo_base64(clove_logo_path) if clove_logo_path else None
    evo2_logo = _load_logo_base64(evo2_logo_path) if evo2_logo_path else None
    clove_img = (
        f'<img src="data:image/png;base64,{clove_logo}" alt="" style="height:32px;" />'
        if clove_logo
        else ""
    )
    evo2_img = (
        f'<img src="data:image/png;base64,{evo2_logo}" alt="Evolution2" style="height:32px;" />'
        if evo2_logo
        else '<span style="color:#f5f5f5;font-weight:600;">Evolution2</span>'
    )

    fy_start = kpi.fiscal_year.start.strftime("%d/%m/%Y")
    fy_end = kpi.fiscal_year.end.strftime("%d/%m/%Y")
    metrics_end = kpi.metrics_end.strftime("%d/%m/%Y")

    from .email_template import format_currency as fc

    def _prest_rows(df) -> List[List[Tuple[str, Optional[float]]]]:
        out: List[List[Tuple[str, Optional[float]]]] = []
        for _, r in df.iterrows():
            out.append(
                [
                    (str(r["Prestation"]), None),
                    (fc(float(r["CA_confirme"])), float(r["CA_confirme"])),
                    (f"{float(r['Quantite']):,.0f}".replace(",", " "), float(r["Quantite"])),
                    (format_int(int(r["N_lignes"])), float(r["N_lignes"])),
                ]
            )
        return out

    prest_ca_table = _prestation_table_html(_prest_rows(kpi.top_prestations_by_ca))
    prest_qty_table = _prestation_table_html(_prest_rows(kpi.top_prestations_by_qty))
    cdp_tbody = _table_rows(cdp_rows)

    cdp_block = ""
    if cdp_rows:
        cdp_block = f"""
          <tr>
            <td style="padding-top:4px;padding-bottom:18px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                6. Conversion par CDP (aperçu)
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">
                Top 5 par PDV confirmé — {kpi.fiscal_year.label}
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
                <tbody>{cdp_tbody}</tbody>
              </table>
            </td>
          </tr>"""

    definitions = f"""
                <div style="font-size:11px;line-height:1.65;color:#e2e5eb;">
                  <strong>Période.</strong> Année fiscale 01/10–30/09 ({fy_start} – {fy_end}).
                  Indicateurs arrêtés au <strong>{metrics_end}</strong> (date du rapport).
                  HIVER : 01/10–30/04 · ÉTÉ : 01/05–30/09.<br/><br/>

                  <strong>1. Cartes.</strong> CA confirmé = somme <code>PDV_DEVIS_CONFIRME</code> (HT) sur lignes CONFIRMÉ,
                  <code>Date_opération</code> dans l’année. Un dossier = un <code>CLIENT_ID</code> distinct.
                  Taux de conversion = dossiers confirmés ÷ dossiers avec <code>Date_opération</code> dans l’année (tous statuts).
                  PDV médian = médiane du CA confirmé agrégé par client.
                  Concentration = part du CA confirmé des 5 / 10 premiers clients.<br/><br/>

                  <strong>2. CA &amp; graphique.</strong> N-1 = année fiscale précédente ({kpi.prior_fiscal_year.label}).
                  Si l’extract V14 n’a pas de lignes N-1 : <strong>ÉTÉ 25</strong> = <code>ete_2025_definitive.csv</code> ;
                  <strong>HIVER</strong> et volumes dossiers = <code>dossier_travail_master.csv</code> (confirmés EC/C/A = C).
                  Courbe verte = cumul confirmé à date du rapport ; courbe grise N-1 = même règle Date opération,
                  alignée sur le calendrier relatif 01/10–30/09. Pas de YoY sur les prestations.<br/><br/>

                  <strong>3–4. Prestations.</strong> Lignes confirmées, <code>Date_opération</code> dans l’année.
                  CA = somme <code>PDV_DEVIS_CONFIRME</code> par <code>PRESTATIONS</code>.
                  Quantité = somme <code>Nb_Unite</code> (unités hétérogènes : Personne(s), Unité(s), Heure(s), etc.).<br/><br/>

                  <strong>5. Sites.</strong> Somme <code>PDV_DEVIS_CONFIRME</code> par colonne <code>SITE</code> (confirmés uniquement).<br/><br/>

                  <strong>6. CDP.</strong> Aperçu top 5 seulement (détail dans le rapport hebdomadaire).
                </div>"""

    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Rapport annuel – Evolution2</title>
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
                  <td align="left">{evo2_img}</td>
                  <td align="right">{clove_img}</td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding-top:16px;padding-bottom:4px;">
              <div style="font-size:20px;font-weight:700;color:{THEME_TEXT};">
                Rapport annuel – Evolution2
              </div>
              <div style="color:{THEME_MUTED};font-size:13px;margin-top:6px;">
                {kpi.fiscal_year.label} · clos au {metrics_end}
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:14px;padding-bottom:14px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">
                1. Vue d’ensemble
              </div>
              <div style="border-radius:10px;border:1px solid {THEME_BORDER};background-color:#0f121a;padding:12px 4px;">
                {_hero_cards_html(kpi)}
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:14px;">
              {_insights_html(kpi.insights)}
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:16px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">
                2. Chiffre d’affaires HT
              </div>
              {_ca_table_html(kpi)}
              <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-top:14px;margin-bottom:6px;">
                CA confirmé cumulé — année vs N-1
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{chart_cumulative_uri}" alt="CA cumulé annuel" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:16px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                3. Top prestations — CA confirmé
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">
                Confirmé · Date opération · {kpi.fiscal_year.label}
              </div>
              {prest_ca_table}
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;margin-top:12px;">
                <img src="{chart_prestation_ca_uri}" alt="Top prestations CA" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:16px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                4. Top prestations — quantité
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">
                Somme Nb_Unite · confirmé · Date opération · {kpi.fiscal_year.label}
              </div>
              {prest_qty_table}
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;margin-top:12px;">
                <img src="{chart_prestation_qty_uri}" alt="Top prestations quantité" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:4px;padding-bottom:16px;">
              <div style="color:{THEME_MUTED};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                5. PDV confirmé par site
              </div>
              <div style="color:{THEME_MUTED};font-size:12px;margin-bottom:8px;">
                {site_period_label}
              </div>
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:10px;text-align:center;">
                <img src="{chart_site_uri}" alt="PDV par site" style="max-width:100%;height:auto;border-radius:6px;" />
              </div>
            </td>
          </tr>

          {cdp_block}

          <tr>
            <td style="padding-top:2px;padding-bottom:16px;">
              <div style="background:{THEME_DARK};border:1px solid {THEME_BORDER};border-radius:10px;padding:12px;color:{THEME_TEXT};">
                <div style="color:{THEME_MUTED};font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">
                  Définitions
                </div>
                {definitions}
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
                <strong>Envoi manuel.</strong> Ce rapport annuel est indépendant du rapport hebdomadaire.
                Une copie HTML est jointe — ouvrez-la dans un navigateur pour la mise en forme complète.
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

"""
CDP weekly commercial email — same pipeline as ``src.main`` except section 3
(no « Conversion par CDP »). Recipients: ``CDP_RECIPIENT_EMAILS`` in ``.env``.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List

from .cdp_section3 import (
    build_cdp_weekly_section3_html,
    cdp_weekly_section3_definitions_html,
)
from .charts import (
    add_site_label_column,
    compute_site_confirmed_pdv_by_season,
    render_site_pdv_season_bars,
)
from .config import (
    CDP_CC_EMAILS,
    CDP_RECIPIENT_EMAILS,
    CLOVE_LOGO_CANDIDATES,
    DROPBOX_REPORT_URL,
    EMAIL_FROM,
    EVO2_LOGO_CANDIDATES,
    LOG_DIR,
    OUTPUTS_DIR,
    RESEND_API_KEY,
)
from .cumulative_season_yoy import render_cumulative_season_yoy_data_uri
from .email_template import build_cdp_weekly_email_html
from .load_data import (
    enrich_with_client_type,
    load_client_database,
    load_excel_data,
    load_marge_reelle_devis,
)
from .send_email import send_email
from .weekly_kpis import compute_weekly_kpis


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "evo2_cdp_weekly_report.log"
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        root.addHandler(ch)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)


def _pick_logo(candidates: List[Path]) -> Path | None:
    for p in candidates:
        if p and p.exists():
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evolution2 weekly CDP email (KPI report without CDP conversion section)."
    )
    parser.add_argument("--send", action="store_true", help="Send email via Resend")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write HTML preview to outputs/ (default behaviour if --send is not used)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Reference date YYYY-MM-DD (default: today). Week KPIs = Mon–Sun ending on the last Sunday ≤ this date.",
    )
    args = parser.parse_args()

    setup_logging()

    as_of: date
    if args.as_of:
        as_of = date.fromisoformat(args.as_of)
    else:
        as_of = date.today()

    df = load_excel_data()
    client_db = load_client_database()
    df = enrich_with_client_type(df, client_db)

    kpis = compute_weekly_kpis(df, as_of=as_of, client_db=client_db)
    logging.info("Validation KPI: %s", kpis.validation)

    chart_cumulative_yoy_uri = render_cumulative_season_yoy_data_uri(df, as_of)

    df_site = add_site_label_column(df)
    site_totals = compute_site_confirmed_pdv_by_season(
        df_site, kpis.current_season.start, kpis.current_season.end
    )
    chart_site_uri = render_site_pdv_season_bars(site_totals, accent="blue")
    site_totals_next = compute_site_confirmed_pdv_by_season(
        df_site, kpis.next_season.start, kpis.next_season.end
    )
    chart_site_next_uri = render_site_pdv_season_bars(site_totals_next, accent="orange")
    logging.info(
        "Site PDV bar charts: current season %d sites, next season %d sites",
        len(site_totals),
        len(site_totals_next),
    )

    week_label = f"{kpis.week_start.strftime('%d/%m/%Y')} – {kpis.week_end.strftime('%d/%m/%Y')}"
    site_period_label = (
        f"Période : du {kpis.current_season.start.strftime('%d/%m/%Y')} au "
        f"{kpis.current_season.end.strftime('%d/%m/%Y')}, {kpis.current_season.label}"
    )
    site_next_period_label = (
        f"Période : du {kpis.next_season.start.strftime('%d/%m/%Y')} au "
        f"{kpis.next_season.end.strftime('%d/%m/%Y')}, {kpis.next_season.label}"
    )

    marge_df = load_marge_reelle_devis()
    section_3_html = build_cdp_weekly_section3_html(
        df, kpis, as_of, client_db=client_db, marge_df=marge_df
    )
    section_3_definitions_html = cdp_weekly_section3_definitions_html(kpis)

    clove_logo = _pick_logo(CLOVE_LOGO_CANDIDATES)
    evo2_logo = _pick_logo(EVO2_LOGO_CANDIDATES)

    html = build_cdp_weekly_email_html(
        clove_logo_path=clove_logo,
        evo2_logo_path=evo2_logo,
        kpi=kpis,
        section_3_html=section_3_html,
        section_3_definitions_html=section_3_definitions_html,
        chart_cumulative_yoy_uri=chart_cumulative_yoy_uri,
        chart_site_bars_uri=chart_site_uri,
        site_chart_period_label=site_period_label,
        chart_site_bars_next_uri=chart_site_next_uri,
        site_chart_next_period_label=site_next_period_label,
        dropbox_url=DROPBOX_REPORT_URL,
        week_range_label=week_label,
    )

    subject = f"Evolution2 – Rapport hebdomadaire CDP – {datetime.now().strftime('%d/%m/%Y')}"

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / "cdp_weekly_report_preview.html"
    out_path.write_text(html, encoding="utf-8")
    logging.info("HTML preview written to %s", out_path)

    if args.send:
        if not (RESEND_API_KEY and EMAIL_FROM and CDP_RECIPIENT_EMAILS):
            raise RuntimeError(
                "Missing configuration: set RESEND_API_KEY, EMAIL_FROM, and at least one address in "
                "CDP_RECIPIENT_EMAIL or CDP_RECIPIENT_EMAILS in .env"
            )
        send_email(
            subject,
            html,
            RESEND_API_KEY,
            EMAIL_FROM,
            CDP_RECIPIENT_EMAILS,
            cc=CDP_CC_EMAILS or None,
            html_attachment_filename="rapport_evolution2_hebdomadaire_cdp.html",
        )
    else:
        logging.info("Preview mode: no email sent. Use --send to deliver via Resend.")


if __name__ == "__main__":
    main()

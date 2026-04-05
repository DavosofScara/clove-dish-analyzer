from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from .charts import (
    add_site_label_column,
    compute_site_confirmed_pdv_by_season,
    render_cdp_scatter,
    render_site_pdv_season_bars,
)
from .config import (
    OUTPUTS_DIR,
    LOG_DIR,
    RESEND_API_KEY,
    EMAIL_FROM,
    RECIPIENT_EMAILS,
    DROPBOX_REPORT_URL,
    CLOVE_LOGO_CANDIDATES,
    EVO2_LOGO_CANDIDATES,
)
from .email_template import build_weekly_email_html, format_currency, format_percent
from .load_data import load_excel_data, load_client_database, enrich_with_client_type
from .metrics import compute_section1_cdp
from .send_email import send_email
from .weekly_kpis import compute_weekly_kpis


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "evo2_commercial_report.log"
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


def build_section_rows(
    df: pd.DataFrame,
    columns: List[str],
    formatters: List,
    numeric_flags: List[bool],
) -> List[List[Tuple[str, Optional[float]]]]:
    rows: List[List[Tuple[str, Optional[float]]]] = []
    for _, row in df.iterrows():
        out_row: List[Tuple[str, Optional[float]]] = []
        for col, fmt, is_num in zip(columns, formatters, numeric_flags):
            val = row[col]
            if is_num and (pd.isna(val) or val is None):
                num = 0.0
            elif is_num:
                num = float(val)
            else:
                num = None
            out_row.append((fmt(val), num))
        rows.append(out_row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evolution2 weekly commercial email (automated KPI report + CDP section)."
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
        help="Reference date YYYY-MM-DD (default: today). Week KPIs use the prior completed Mon–Sun.",
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

    kpis = compute_weekly_kpis(df, as_of=as_of)
    cdp_df, sanity = compute_section1_cdp(df)

    logging.info("Sanity CDP: %s", sanity)
    logging.info("Validation KPI: %s", kpis.validation)

    chart_scatter_uri = render_cdp_scatter(cdp_df)

    df_site = add_site_label_column(df)
    site_totals = compute_site_confirmed_pdv_by_season(
        df_site, kpis.current_season.start, kpis.season_metrics_end
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

    section_cdp = cdp_df.head(8)
    cdp_rows = build_section_rows(
        section_cdp,
        ["CDP", "Clients_uniques", "Taux_confirmation", "PDV_confirme", "PDV_median_client"],
        [str, lambda v: f"{int(v)}", format_percent, format_currency, format_currency],
        [False, True, True, True, True],
    )

    week_label = f"{kpis.week_start.strftime('%d/%m/%Y')} – {kpis.week_end.strftime('%d/%m/%Y')}"
    site_period_label = (
        f"Période : du {kpis.current_season.start.strftime('%d/%m/%Y')} au "
        f"{kpis.season_metrics_end.strftime('%d/%m/%Y')}, {kpis.current_season.label}"
    )
    site_next_period_label = (
        f"Période : du {kpis.next_season.start.strftime('%d/%m/%Y')} au "
        f"{kpis.next_season.end.strftime('%d/%m/%Y')}, {kpis.next_season.label}"
    )

    clove_logo = _pick_logo(CLOVE_LOGO_CANDIDATES)
    evo2_logo = _pick_logo(EVO2_LOGO_CANDIDATES)

    html = build_weekly_email_html(
        clove_logo_path=clove_logo,
        evo2_logo_path=evo2_logo,
        kpi=kpis,
        cdp_section_rows=cdp_rows,
        chart_scatter_uri=chart_scatter_uri,
        chart_site_bars_uri=chart_site_uri,
        site_chart_period_label=site_period_label,
        chart_site_bars_next_uri=chart_site_next_uri,
        site_chart_next_period_label=site_next_period_label,
        dropbox_url=DROPBOX_REPORT_URL,
        week_range_label=week_label,
    )

    subject = f"Evolution2 – Rapport hebdomadaire – {datetime.now().strftime('%d/%m/%Y')}"

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / "commercial_report_preview.html"
    out_path.write_text(html, encoding="utf-8")
    logging.info("HTML preview written to %s", out_path)

    if args.send:
        if not (RESEND_API_KEY and EMAIL_FROM and RECIPIENT_EMAILS):
            raise RuntimeError(
                "Missing configuration: set RESEND_API_KEY, EMAIL_FROM, and at least one address in "
                "RECIPIENT_EMAIL or RECIPIENT_EMAILS in .env"
            )
        send_email(subject, html, RESEND_API_KEY, EMAIL_FROM, RECIPIENT_EMAILS)
    else:
        logging.info("Preview mode: no email sent. Use --send to deliver via Resend.")


if __name__ == "__main__":
    main()

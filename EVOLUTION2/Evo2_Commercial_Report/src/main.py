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
    render_cdp_margin_bars,
    render_cdp_scatter,
    render_site_pdv_season_bars,
)
from .cumulative_season_yoy import render_cumulative_season_yoy_data_uri
from .config import (
    OUTPUTS_DIR,
    LOG_DIR,
    RESEND_API_KEY,
    EMAIL_FROM,
    RECIPIENT_EMAILS,
    CC_EMAILS,
    DROPBOX_REPORT_URL,
    CLOVE_LOGO_CANDIDATES,
    EVO2_LOGO_CANDIDATES,
)
from .email_template import build_weekly_email_html, format_currency, format_percent
from .load_data import (
    load_excel_data,
    load_client_database,
    load_marge_reelle_devis,
    enrich_with_client_type,
)
from .metrics import compute_cdp_margin_pct_averages, compute_section1_cdp
from .send_email import send_email
from .periods import fiscal_year_containing
from .weekly_kpis import compute_weekly_kpis

# Section 3.2 charts: softer greens so 3.1 vs 3.2 are visually distinct.
CDP_FISCAL_YEAR_GREEN_ALPHA = 0.52
CDP_FISCAL_YEAR_BUDGET_ALPHA = 0.34


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
    current_season = kpis.current_season
    current_fiscal_year = fiscal_year_containing(as_of)

    cdp_season_df, sanity_season = compute_section1_cdp(
        df, period_start=current_season.start, period_end=current_season.end
    )
    cdp_year_df, sanity_year = compute_section1_cdp(
        df, period_start=current_fiscal_year.start, period_end=current_fiscal_year.end
    )

    logging.info("Sanity CDP (saison): %s", sanity_season)
    logging.info("Sanity CDP (année): %s", sanity_year)
    logging.info("Validation KPI: %s", kpis.validation)

    chart_scatter_season_uri = render_cdp_scatter(cdp_season_df)
    chart_scatter_year_uri = render_cdp_scatter(
        cdp_year_df, green_alpha=CDP_FISCAL_YEAR_GREEN_ALPHA
    )
    marge_df = load_marge_reelle_devis()
    margin_season_df = compute_cdp_margin_pct_averages(
        marge_df, period_start=current_season.start, period_end=current_season.end
    )
    margin_year_df = compute_cdp_margin_pct_averages(
        marge_df,
        period_start=current_fiscal_year.start,
        period_end=current_fiscal_year.end,
    )
    chart_margin_season_uri = render_cdp_margin_bars(margin_season_df)
    chart_margin_year_uri = render_cdp_margin_bars(
        margin_year_df,
        green_alpha=CDP_FISCAL_YEAR_GREEN_ALPHA,
        budget_alpha=CDP_FISCAL_YEAR_BUDGET_ALPHA,
    )
    logging.info(
        "CDP margin charts: saison %d CDPs (%d source rows), année %d CDPs",
        len(margin_season_df),
        len(marge_df),
        len(margin_year_df),
    )
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

    cdp_season_rows = build_section_rows(
        cdp_season_df.head(8),
        ["CDP", "Clients_uniques", "Taux_confirmation", "PDV_confirme", "PDV_median_client"],
        [str, lambda v: f"{int(v)}", format_percent, format_currency, format_currency],
        [False, True, True, True, True],
    )
    cdp_year_rows = build_section_rows(
        cdp_year_df.head(8),
        ["CDP", "Clients_uniques", "Taux_confirmation", "PDV_confirme", "PDV_median_client"],
        [str, lambda v: f"{int(v)}", format_percent, format_currency, format_currency],
        [False, True, True, True, True],
    )

    week_label = f"{kpis.week_start.strftime('%d/%m/%Y')} – {kpis.week_end.strftime('%d/%m/%Y')}"
    cdp_season_period_label = (
        f"Période : du {current_season.start.strftime('%d/%m/%Y')} au "
        f"{current_season.end.strftime('%d/%m/%Y')}, {current_season.label}"
    )
    cdp_year_period_label = (
        f"Période : du {current_fiscal_year.start.strftime('%d/%m/%Y')} au "
        f"{current_fiscal_year.end.strftime('%d/%m/%Y')}, {current_fiscal_year.label}"
    )
    site_period_label = (
        f"Période : du {kpis.current_season.start.strftime('%d/%m/%Y')} au "
        f"{kpis.current_season.end.strftime('%d/%m/%Y')}, {kpis.current_season.label}"
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
        cdp_season_rows=cdp_season_rows,
        cdp_season_period_label=cdp_season_period_label,
        chart_scatter_season_uri=chart_scatter_season_uri,
        chart_margin_season_uri=chart_margin_season_uri,
        cdp_year_rows=cdp_year_rows,
        cdp_year_period_label=cdp_year_period_label,
        fiscal_year_start=current_fiscal_year.start.strftime("%d/%m/%Y"),
        fiscal_year_end=current_fiscal_year.end.strftime("%d/%m/%Y"),
        chart_scatter_year_uri=chart_scatter_year_uri,
        chart_margin_year_uri=chart_margin_year_uri,
        chart_cumulative_yoy_uri=chart_cumulative_yoy_uri,
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
        send_email(
            subject,
            html,
            RESEND_API_KEY,
            EMAIL_FROM,
            RECIPIENT_EMAILS,
            cc=CC_EMAILS or None,
        )
    else:
        logging.info("Preview mode: no email sent. Use --send to deliver via Resend.")


if __name__ == "__main__":
    main()

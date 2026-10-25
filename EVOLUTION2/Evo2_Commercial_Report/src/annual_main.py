"""
Evolution2 annual commercial report (fiscal year 01/10–30/09).

Separate from the weekly pipeline — schedule / LaunchAgent unchanged.
Typical close: ``python -m src.annual_main --as-of 2026-09-30 --dry-run``
then tweak and ``--send`` on 01/10.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from .annual_cumulative import render_cumulative_fiscal_yoy_data_uri
from .annual_email_template import build_annual_email_html
from .annual_kpis import compute_annual_kpis
from .charts import (
    add_site_label_column,
    compute_site_confirmed_pdv_by_season,
    render_ranked_horizontal_bars,
    render_site_pdv_season_bars,
)
from .config import (
    CC_EMAILS,
    CLOVE_LOGO_CANDIDATES,
    DROPBOX_REPORT_URL,
    EMAIL_FROM,
    EVO2_LOGO_CANDIDATES,
    LOG_DIR,
    OUTPUTS_DIR,
    RECIPIENT_EMAILS,
    RESEND_API_KEY,
)
from .email_template import format_currency, format_percent
from .load_data import (
    enrich_with_client_type,
    load_client_database,
    load_excel_data,
    load_marge_reelle_devis,
)
from .metrics import compute_section1_cdp
from .send_email import send_email


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "evo2_annual_report.log"
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
        description="Evolution2 annual commercial email (fiscal year KPIs). Does not affect the weekly report."
    )
    parser.add_argument("--send", action="store_true", help="Send email via Resend")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write HTML preview to outputs/ (default if --send is not used)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Reference date YYYY-MM-DD (default: today). Use YYYY-09-30 for fiscal year close.",
    )
    args = parser.parse_args()
    setup_logging()

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    df = load_excel_data()
    client_db = load_client_database()
    df = enrich_with_client_type(df, client_db)
    marge_df = load_marge_reelle_devis()

    from .periods import fiscal_year_containing

    fy = fiscal_year_containing(as_of)
    cdp_df, sanity = compute_section1_cdp(df, period_start=fy.start, period_end=min(as_of, fy.end))
    logging.info("Sanity CDP (année): %s", sanity)

    kpi = compute_annual_kpis(df, as_of, marge_df=marge_df, cdp_table=cdp_df)
    logging.info("Validation annual KPI: %s", kpi.validation)

    chart_cumulative = render_cumulative_fiscal_yoy_data_uri(df, as_of)

    ca_df = kpi.top_prestations_by_ca
    chart_prest_ca = render_ranked_horizontal_bars(
        ca_df["Prestation"].astype(str).tolist() if not ca_df.empty else [],
        ca_df["CA_confirme"].astype(float).tolist() if not ca_df.empty else [],
        xlabel="CA confirmé HT (€)",
        accent="green",
    )
    qty_df = kpi.top_prestations_by_qty
    chart_prest_qty = render_ranked_horizontal_bars(
        qty_df["Prestation"].astype(str).tolist() if not qty_df.empty else [],
        qty_df["Quantite"].astype(float).tolist() if not qty_df.empty else [],
        xlabel="Quantité (Nb_Unite)",
        accent="blue",
    )

    df_site = add_site_label_column(df)
    site_totals = compute_site_confirmed_pdv_by_season(
        df_site, fy.start, min(as_of, fy.end)
    )
    chart_site = render_site_pdv_season_bars(site_totals, accent="blue")
    site_period_label = (
        f"Période : du {fy.start.strftime('%d/%m/%Y')} au "
        f"{min(as_of, fy.end).strftime('%d/%m/%Y')}, {fy.label}"
    )

    cdp_rows = build_section_rows(
        cdp_df.head(5),
        ["CDP", "Clients_uniques", "Taux_confirmation", "PDV_confirme", "PDV_median_client"],
        [str, lambda v: f"{int(v)}", format_percent, format_currency, format_currency],
        [False, True, True, True, True],
    )

    html = build_annual_email_html(
        clove_logo_path=_pick_logo(CLOVE_LOGO_CANDIDATES),
        evo2_logo_path=_pick_logo(EVO2_LOGO_CANDIDATES),
        kpi=kpi,
        chart_cumulative_uri=chart_cumulative,
        chart_prestation_ca_uri=chart_prest_ca,
        chart_prestation_qty_uri=chart_prest_qty,
        chart_site_uri=chart_site,
        site_period_label=site_period_label,
        cdp_rows=cdp_rows,
        dropbox_url=DROPBOX_REPORT_URL or "#",
    )

    subject = (
        f"Evolution2 – Rapport annuel – {kpi.fiscal_year.label} "
        f"({kpi.metrics_end.strftime('%d/%m/%Y')})"
    )

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / "annual_report_preview.html"
    out_path.write_text(html, encoding="utf-8")
    logging.info("Annual HTML preview written to %s", out_path)

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
            html_attachment_filename="rapport_evolution2_annuel.html",
        )
    else:
        logging.info(
            "Preview mode: no email sent. Use --send to deliver via Resend. "
            "Weekly report unchanged."
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Lightspeed cleaner for the Mumma project.

This utility scans configured directories for Lightspeed Transactions/Product CSV
exports, normalizes the data, and writes an appendable revenue ledger that can be
consumed by Excel models or uploaded into the Clove ingestion API.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lightspeed_mapper import LightspeedMapper

DEFAULT_RAW_TRANSACTIONS = REPO_ROOT / "data" / "mumma" / "raw" / "transactions"
DEFAULT_RAW_PRODUCTS = REPO_ROOT / "data" / "mumma" / "raw" / "products"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "mumma" / "processed" / "revenue_ledger.csv"
DEFAULT_METADATA = DEFAULT_OUTPUT.with_suffix(".metadata.json")
DEFAULT_DAILY_SUMMARY_XLSX = REPO_ROOT / "data" / "mumma" / "processed" / "daily_sales_summary.xlsx"
DEFAULT_PRODUCT_INSIGHTS_XLSX = REPO_ROOT / "data" / "mumma" / "processed" / "product_insights.xlsx"
DEFAULT_PRODUCT_INSIGHTS_DETAILED = REPO_ROOT / "data" / "mumma" / "processed" / "product_insights_detailed.csv"
DEFAULT_DROPBOX = Path(
    "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/Lightspeed_Reports/Processed/revenue_ledger.csv"
)


@dataclass
class SourceSummary:
    """Track per-file stats for debugging recurring weekly runs."""

    path: str
    rows: int
    last_modified: str
    report_type: str


def discover_csvs(directory: Path) -> List[Path]:
    """Return a sorted list of CSV files within directory."""
    if not directory.exists():
        return []
    files = list(directory.glob("*.csv")) + list(directory.glob("*.CSV"))
    return sorted(p for p in files if p.is_file())


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    """Attempt to read CSV with multiple encodings."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "iso-8859-1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", b"", 0, 1, f"Unable to decode {path}")


def normalize_numeric(series: pd.Series) -> pd.Series:
    """Convert Lightspeed numeric strings to floats."""
    def _convert(value) -> float:
        if value is None:
            return 0.0
        try:
            if pd.isna(value):
                return 0.0
        except TypeError:
            pass
        return LightspeedMapper.normalize_number(value)

    return series.apply(_convert)


def normalize_sku(series: pd.Series) -> pd.Series:
    """Coerce SKU values to clean, comparable strings.

    Lightspeed exports sometimes come through as floats (e.g. 12345.0) in one
    report and as strings in another. To make joins reliable we:
    - cast everything to string
    - strip whitespace
    - drop any trailing `.0` that comes from numeric parsing
    """
    as_str = series.astype(str).str.strip()
    # Remove a single trailing ".0" (e.g. "12345.0" -> "12345")
    return as_str.str.replace(r"\.0$", "", regex=True)


def write_daily_summary(df: pd.DataFrame, output_path: Path) -> None:
    """Write daily sales XLSX with tax and category splits for Excel linkage.

    Columns:
      - Date
      - Location  (Shack / Mumma)
      - Total Sales
      - 10% Sales
      - 20% Sales
      - Food Sales
      - Drink Sales
    """
    required_cols = {"transaction_date", "net_revenue"}
    if not required_cols.issubset(df.columns):
        return

    working = df.copy()

    # Location should already be set in clean_transactions() based on filename
    # If not present, derive from source_file column (fallback)
    if "location" not in working.columns:
        if "source_file" in working.columns:
            working["location"] = working["source_file"].astype(str).str.lower().apply(
                lambda s: "Shack" if "shack" in s else "Mumma"
            )
        else:
            working["location"] = "Mumma"

    # Tax band flags (10% vs 20%) based on tax_rate and tax_name.
    tax_name = working.get("tax_name") if "tax_name" in working.columns else None
    rate = working.get("tax_rate") if "tax_rate" in working.columns else None

    def _is_band(target: float) -> pd.Series:
        cond = pd.Series(False, index=working.index)
        if rate is not None:
            cond |= rate.round(1).fillna(0).eq(target)
        if tax_name is not None:
            cond |= tax_name.astype(str).str.contains(f"{int(target)}%", case=False, na=False)
        return cond

    is_10 = _is_band(10.0)
    is_20 = _is_band(20.0)

    # Food vs drink heuristics from category/stat_group.
    cat = working.get("category").astype(str).str.lower() if "category" in working.columns else None
    stat = working.get("stat_group").astype(str).str.lower() if "stat_group" in working.columns else None

    def _contains_any(series: Optional[pd.Series], keywords) -> pd.Series:
        if series is None:
            return pd.Series(False, index=working.index)
        pattern = "|".join(keywords)
        return series.str.contains(pattern, case=False, na=False)

    is_food = _contains_any(cat, ["cuisine", "food", "kitchen", "dessert"])
    is_drink = _contains_any(cat, ["boissons", "alcool", "bar", "drink"]) | _contains_any(
        stat, ["boissons", "alcohol", "bar", "drink"]
    )

    # Build conditional sales columns.
    nr = working["net_revenue"].fillna(0.0)
    working["total_sales"] = nr
    working["sales_10"] = nr.where(is_10, 0.0)
    working["sales_20"] = nr.where(is_20, 0.0)
    working["food_sales"] = nr.where(is_food, 0.0)
    working["drink_sales"] = nr.where(is_drink, 0.0)

    grouped = (
        working.groupby(["transaction_date", "location"], as_index=False)[
            ["total_sales", "sales_10", "sales_20", "food_sales", "drink_sales"]
        ]
        .sum()
        .rename(
            columns={
                "transaction_date": "Date",
                "location": "Location",
                "total_sales": "Total Sales",
                "sales_10": "10% Sales",
                "sales_20": "20% Sales",
                "food_sales": "Food Sales",
                "drink_sales": "Drink Sales",
            }
        )
        .sort_values(["Date", "Location"])
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_excel(output_path, index=False)

def write_product_insights(df: pd.DataFrame, output_path: Path) -> None:
    """Write product-level insights (top/bottom and weekly KPIs) to an XLSX file."""
    if not {"sku", "item_name", "quantity", "net_revenue", "iso_year", "iso_week"}.issubset(df.columns):
        return

    working = df.copy()
    nr = working["net_revenue"].fillna(0.0)
    qty = working["quantity"].fillna(0.0)

    # Overall per-product stats
    per_product = (
        working.groupby(["sku", "item_name"], as_index=False)[["quantity", "net_revenue"]]
        .sum()
        .rename(
            columns={
                "quantity": "Total Units",
                "net_revenue": "Total Revenue",
            }
        )
    )

    # Top 10 by revenue (also shows units)
    top10 = per_product.sort_values("Total Revenue", ascending=False).head(10)

    # Bottom 5 by revenue, excluding zero-sales items
    non_zero = per_product[per_product["Total Revenue"] != 0]
    bottom5 = non_zero.sort_values("Total Revenue", ascending=True).head(5)

    # Weekly KPIs per product
    weekly = (
        working.groupby(["iso_year", "iso_week", "sku", "item_name"], as_index=False)[
            ["quantity", "net_revenue"]
        ]
        .sum()
        .rename(
            columns={
                "quantity": "Weekly Units",
                "net_revenue": "Weekly Revenue",
            }
        )
        .sort_values(["iso_year", "iso_week", "sku"])
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        per_product.sort_values("Total Revenue", ascending=False).to_excel(
            writer, sheet_name="All Products", index=False
        )
        top10.to_excel(writer, sheet_name="Top 10", index=False)
        bottom5.to_excel(writer, sheet_name="Bottom 5", index=False)
        weekly.to_excel(writer, sheet_name="Weekly KPIs", index=False)


def write_product_insights_detailed(df: pd.DataFrame, output_path: Path) -> None:
    """Write detailed product-period insights to CSV for downstream analysis."""
    required = {
        "sku",
        "item_name",
        "category",
        "location",
        "transaction_datetime",
        "transaction_date",
        "quantity",
        "net_revenue",
    }
    if not required.issubset(df.columns):
        return

    working = df.copy()
    working["transaction_datetime"] = pd.to_datetime(working["transaction_datetime"])

    # Period start date: Monday of each ISO week
    working["period_start_date"] = (
        working["transaction_datetime"].dt.to_period("W-MON").dt.start_time.dt.date
    )

    # Base aggregates per product / location / period
    grouped = (
        working.groupby(
            ["sku", "item_name", "category", "location", "period_start_date"],
            as_index=False,
        )
        .agg(
            total_units=("quantity", "sum"),
            total_revenue=("net_revenue", "sum"),
            active_days_count=("transaction_date", "nunique"),
        )
        .sort_values(["sku", "location", "period_start_date"])
    )

    # Derived metrics
    grouped["avg_daily_sales"] = grouped["total_units"] / grouped["active_days_count"].replace(0, pd.NA)
    grouped["avg_daily_sales"] = grouped["avg_daily_sales"].fillna(0.0)

    # Active weeks count per product + location (over full history)
    grouped["active_weeks_count"] = (
        grouped.groupby(["sku", "location"])["period_start_date"]
        .transform("nunique")
        .astype(int)
    )

    # Period-on-period comparison within sku + location
    grouped = grouped.sort_values(["sku", "location", "period_start_date"])
    group_key = ["sku", "location"]
    grouped["units_last_period"] = grouped.groupby(group_key)["total_units"].shift(1)
    grouped["revenue_last_period"] = grouped.groupby(group_key)["total_revenue"].shift(1)

    def _pct_change(current: pd.Series, last: pd.Series) -> pd.Series:
        return ((current - last) / last.where(last != 0)).replace([pd.NA, pd.NaT], 0.0)

    grouped["units_change_pct"] = _pct_change(grouped["total_units"], grouped["units_last_period"])
    grouped["revenue_change_pct"] = _pct_change(grouped["total_revenue"], grouped["revenue_last_period"])

    # Season tagging from period_start_date
    def _season(d) -> str:
        # Summer: 1 May – 30 Oct, Winter: 1 Nov – 30 Apr
        if d is pd.NaT or d is None:
            return "Unknown"
        month = d.month
        if 5 <= month <= 10:
            return "Summer"
        return "Winter"

    grouped["season"] = grouped["period_start_date"].apply(_season)

    # New product flag: first period for this sku + location
    grouped["period_index"] = grouped.groupby(group_key).cumcount()
    grouped["is_new_product"] = grouped["period_index"] == 0

    # Rising / declining flags based on units_change_pct
    grouped["is_rising"] = (grouped["units_change_pct"] >= 0.20) & (
        grouped["units_last_period"].fillna(0) > 0
    )
    grouped["is_declining"] = (grouped["units_change_pct"] <= -0.20) & (
        grouped["units_last_period"].fillna(0) > 0
    )

    # Seasonal peak: season where this SKU historically sells more units
    season_means = (
        grouped.groupby(["sku", "season"])["total_units"]
        .mean()
        .reset_index(name="season_mean_units")
    )
    peak_season = (
        season_means.sort_values(["sku", "season_mean_units"], ascending=[True, False])
        .drop_duplicates("sku")[["sku", "season"]]
        .rename(columns={"season": "peak_season"})
    )
    grouped = grouped.merge(peak_season, on="sku", how="left")
    grouped["is_seasonal_peak"] = grouped["season"] == grouped["peak_season"]
    grouped = grouped.drop(columns=["peak_season"])

    # Calculate seasonal revenue averages (for seasonal insight metrics)
    season_revenue_means = (
        grouped.groupby(["sku", "season"])["total_revenue"]
        .mean()
        .reset_index(name="season_mean_revenue")
    )
    # Merge seasonal revenue averages back
    grouped = grouped.merge(season_revenue_means, on=["sku", "season"], how="left")

    # Reorder & select columns for export
    export_cols = [
        "period_start_date",
        "sku",
        "item_name",
        "category",
        "location",
        "season",
        "total_units",
        "total_revenue",
        "avg_daily_sales",
        "active_days_count",
        "active_weeks_count",
        "units_last_period",
        "units_change_pct",
        "revenue_last_period",
        "revenue_change_pct",
        "season_mean_revenue",
        "is_new_product",
        "is_rising",
        "is_declining",
        "is_seasonal_peak",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    grouped[export_cols].to_csv(output_path, index=False)

def parse_transaction_dates(series: pd.Series) -> pd.Series:
    """Parse Lightspeed Date field which uses DD/MM/YY HH:MM format."""
    return pd.to_datetime(series, errors="coerce", dayfirst=True, utc=False, infer_datetime_format=True)


def clean_transactions(df: pd.DataFrame, source_file: Path) -> pd.DataFrame:
    """Normalize Lightspeed transactions export."""
    mapping = LightspeedMapper.map_transactions_headers(df.columns.tolist())
    missing = LightspeedMapper.validate_critical_columns(mapping, "transactions")
    if missing:
        raise ValueError(f"{source_file.name}: missing critical Lightspeed columns: {missing}")

    rename_plan = {
        "transaction_datetime": mapping.get("date"),
        "sku": mapping.get("sku"),
        "item_name": mapping.get("item_name"),
        "category": mapping.get("group"),
        "stat_group": mapping.get("stat_group"),
        "staff": mapping.get("staff"),
        "account_name": mapping.get("account_name"),
        "account": mapping.get("account"),
        "mode": mapping.get("mode"),
        "reference": mapping.get("reference"),
        "profile": mapping.get("profile"),
        "quantity": mapping.get("qty"),
        "unit_price": mapping.get("unit_price"),
        "gross_revenue": mapping.get("final_price"),
        "discount_amount": mapping.get("discount_amount"),
        "loss_amount": mapping.get("loss_amount"),
        "comp_amount": mapping.get("comp_amount"),
        "charge_amount": mapping.get("charge_amount"),
        "pretax_amount": mapping.get("pretax_amount"),
        "tax_amount": mapping.get("tax_amount"),
        "tax_rate": mapping.get("tax_rate"),
        "tax_name": mapping.get("tax_name"),
    }

    cleaned = df.copy()
    rename_dict = {original: alias for alias, original in rename_plan.items() if original}
    cleaned = cleaned.rename(columns=rename_dict)

    # Ensure SKU is always a normalized string for safe joins
    if "sku" in cleaned.columns:
        cleaned["sku"] = normalize_sku(cleaned["sku"])

    # Derive location from Device_Name column in CSV data (more reliable than filename)
    # Device names like "Shack 24(904716)" indicate Shack, "M-Bar-26(1057165)" indicates Mumma
    # Fall back to filename if Device_Name is not available
    if "Device_Name" in df.columns:
        device_names = df["Device_Name"].astype(str).str.lower()
        cleaned["location"] = device_names.apply(
            lambda x: "Shack" if "shack" in x else "Mumma"
        )
    else:
        # Fallback to filename-based logic for older files
        filename_lower = source_file.name.lower()
        if "shack" in filename_lower:
            cleaned["location"] = "Shack"
        else:
            # Default to "Mumma" (covers "mumma" and any other filenames)
            cleaned["location"] = "Mumma"

    # Ensure SKU is always a normalized string for safe joins
    if "sku" in cleaned.columns:
        cleaned["sku"] = normalize_sku(cleaned["sku"])

    cleaned["transaction_datetime"] = parse_transaction_dates(cleaned["transaction_datetime"])
    cleaned["transaction_date"] = cleaned["transaction_datetime"].dt.date
    cleaned["transaction_time"] = cleaned["transaction_datetime"].dt.time
    cleaned["iso_year"] = cleaned["transaction_datetime"].dt.isocalendar().year
    cleaned["iso_week"] = cleaned["transaction_datetime"].dt.isocalendar().week
    cleaned["month"] = cleaned["transaction_datetime"].dt.to_period("M").astype(str)

    number_columns = [
        "quantity",
        "unit_price",
        "gross_revenue",
        "discount_amount",
        "loss_amount",
        "comp_amount",
        "charge_amount",
        "pretax_amount",
        "tax_amount",
        "tax_rate",
    ]
    for column in number_columns:
        if column in cleaned.columns:
            cleaned[column] = normalize_numeric(cleaned[column])

    cleaned["net_revenue"] = cleaned["quantity"].fillna(0) * cleaned["unit_price"].fillna(0)
    cleaned["net_revenue"] = cleaned["net_revenue"].where(cleaned["net_revenue"] > 0, cleaned["gross_revenue"])
    cleaned["source_file"] = source_file.name
    cleaned["source_path"] = str(source_file)
    cleaned["source_modified_at"] = datetime.fromtimestamp(source_file.stat().st_mtime).isoformat()
    cleaned["source_type"] = "transactions"
    if "Identifier" in cleaned.columns:
        cleaned["row_uid"] = cleaned["Identifier"].astype(str)
    else:
        index_series = cleaned.index.to_series().astype(str)
        cleaned["row_uid"] = cleaned["source_file"].astype(str) + ":" + index_series

    essential_cols = [
        "row_uid",
        "transaction_datetime",
        "transaction_date",
        "transaction_time",
        "iso_year",
        "iso_week",
        "month",
        "sku",
        "item_name",
        "category",
        "stat_group",
        "quantity",
        "unit_price",
        "gross_revenue",
        "net_revenue",
        "pretax_amount",
        "tax_amount",
        "tax_rate",
        "discount_amount",
        "loss_amount",
        "comp_amount",
        "charge_amount",
        "staff",
        "mode",
        "account",
        "account_name",
        "reference",
        "profile",
        "tax_name",
        "location",
        "source_file",
        "source_path",
        "source_modified_at",
        "source_type",
    ]

    # Keep known columns; drop duplicates automatically.
    cleaned = cleaned[[col for col in essential_cols if col in cleaned.columns]].dropna(subset=["transaction_datetime"])
    cleaned = cleaned.drop_duplicates(subset=["row_uid"])
    return cleaned


def clean_products(df: pd.DataFrame, source_file: Path) -> pd.DataFrame:
    """Normalize Lightspeed product/category export."""
    mapping = LightspeedMapper.map_products_headers(df.columns.tolist())
    missing = LightspeedMapper.validate_critical_columns(mapping, "products")
    if missing:
        raise ValueError(f"{source_file.name}: missing critical Lightspeed columns: {missing}")

    rename_plan = {
        "sku": mapping.get("sku"),
        "product_total_revenue": mapping.get("total_revenue"),
        "product_total_quantity": mapping.get("total_quantity"),
        "product_total_transactions": mapping.get("total_transactions"),
        "product_discount_amount": mapping.get("discount_amount"),
        "product_loss_amount": mapping.get("loss_amount"),
        "product_return_amount": mapping.get("return_amount"),
        "product_transaction_amount": mapping.get("transaction_amount"),
        "product_margin": mapping.get("margin"),
        "product_costs": mapping.get("costs"),
    }

    cleaned = df.copy()
    rename_dict = {original: alias for alias, original in rename_plan.items() if original}
    cleaned = cleaned.rename(columns=rename_dict)

    # Ensure SKU is always a normalized string for safe joins
    if "sku" in cleaned.columns:
        cleaned["sku"] = normalize_sku(cleaned["sku"])

    # Ensure SKU is always a normalized string for safe joins
    if "sku" in cleaned.columns:
        cleaned["sku"] = normalize_sku(cleaned["sku"])

    number_columns = [col for col in rename_plan.keys() if col != "sku" and col in cleaned.columns]
    for column in number_columns:
        cleaned[column] = normalize_numeric(cleaned[column])

    cleaned["source_file"] = source_file.name
    cleaned["source_path"] = str(source_file)
    cleaned["source_modified_at"] = datetime.fromtimestamp(source_file.stat().st_mtime).isoformat()
    cleaned["source_type"] = "products"
    cleaned["report_date"] = infer_date_from_name(source_file)
    return cleaned[["sku", "report_date", *number_columns, "source_file", "source_path", "source_modified_at", "source_type"]]


def infer_date_from_name(path: Path) -> Optional[str]:
    """Extract YYYYMMDD-like token from filename."""
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", path.stem)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            return None
    return None


def merge_with_products(transactions: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Enrich transactions with the latest product metrics by SKU."""
    if products.empty:
        return transactions
    products = products.sort_values(by=["sku", "report_date", "source_modified_at"])
    latest_by_sku = products.groupby("sku").tail(1)
    merged = transactions.merge(
        latest_by_sku[
            [
                "sku",
                "product_total_revenue",
                "product_total_quantity",
                "product_total_transactions",
                "product_margin",
                "product_costs",
            ]
        ],
        on="sku",
        how="left",
    )
    return merged


def write_outputs(df: pd.DataFrame, output_path: Path, dropbox_path: Optional[Path]) -> None:
    """Persist the ledger locally and optionally in Dropbox."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    if dropbox_path:
        dropbox_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(dropbox_path, index=False)


def build_metadata(
    transactions: Iterable[SourceSummary], products: Iterable[SourceSummary], ledger_path: Path
) -> Dict[str, object]:
    """Return JSON metadata that describes the run."""
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "ledger_path": str(ledger_path),
        "transaction_sources": [asdict(item) for item in transactions],
        "product_sources": [asdict(item) for item in products],
    }


def summarize_sources(files: List[Path], kind: str) -> List[SourceSummary]:
    """Summaries for metadata file."""
    summaries: List[SourceSummary] = []
    for path in files:
        rows = sum(1 for _ in path.open())
        summaries.append(
            SourceSummary(
                path=str(path),
                rows=max(rows - 1, 0),
                last_modified=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                report_type=kind,
            )
        )
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean Lightspeed CSV exports and build revenue_ledger.csv")
    parser.add_argument("--raw-transactions", type=Path, default=DEFAULT_RAW_TRANSACTIONS, help="Folder with Lightspeed Transactions CSVs")
    parser.add_argument("--raw-products", type=Path, default=DEFAULT_RAW_PRODUCTS, help="Folder with Lightspeed Product CSVs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination for revenue_ledger.csv")
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA, help="Destination for ledger metadata JSON")
    parser.add_argument(
        "--daily-summary-xlsx",
        type=Path,
        default=DEFAULT_DAILY_SUMMARY_XLSX,
        help="Destination for daily sales summary XLSX (Date, Sales)",
    )
    parser.add_argument(
        "--product-insights-xlsx",
        type=Path,
        default=DEFAULT_PRODUCT_INSIGHTS_XLSX,
        help="Destination for product insights XLSX (top/bottom/weekly KPIs)",
    )
    parser.add_argument(
        "--product-insights-detailed",
        type=Path,
        default=DEFAULT_PRODUCT_INSIGHTS_DETAILED,
        help="Destination for detailed product-period insights CSV",
    )
    parser.add_argument("--dropbox-output", type=Path, default=DEFAULT_DROPBOX, help="Optional Dropbox copy location")
    parser.add_argument("--skip-dropbox", action="store_true", help="Do not mirror to Dropbox (overrides --dropbox-output)")
    args = parser.parse_args()

    transaction_files = discover_csvs(args.raw_transactions)
    product_files = discover_csvs(args.raw_products)

    if not transaction_files:
        raise SystemExit(f"No transaction CSVs found in {args.raw_transactions}")

    all_transactions: List[pd.DataFrame] = []
    for file_path in transaction_files:
        df = read_csv_with_fallback(file_path)
        cleaned = clean_transactions(df, file_path)
        all_transactions.append(cleaned)

    transactions_df = pd.concat(all_transactions, ignore_index=True)
    
    # Global deduplication across all files
    # Use Identifier if available (unique per line item), otherwise use Reference, 
    # or create composite key from transaction details
    print(f"📊 Total transactions after per-file processing: {len(transactions_df):,}")
    
    # Build deduplication key: prefer Identifier > Reference > composite key
    transactions_df["dedup_key"] = None
    
    if "Identifier" in transactions_df.columns:
        has_identifier = transactions_df["Identifier"].notna().sum()
        print(f"   Transactions with Identifier: {has_identifier:,} ({has_identifier/len(transactions_df)*100:.1f}%)")
        # Use Identifier where available
        transactions_df.loc[transactions_df["Identifier"].notna(), "dedup_key"] = (
            transactions_df.loc[transactions_df["Identifier"].notna(), "Identifier"].astype(str)
        )
    
    # For rows without Identifier, try Reference (might be transaction-level ID)
    missing_key_mask = transactions_df["dedup_key"].isna()
    if "reference" in transactions_df.columns and missing_key_mask.any():
        has_reference = transactions_df.loc[missing_key_mask, "reference"].notna().sum()
        if has_reference > 0:
            print(f"   Transactions with Reference (no Identifier): {has_reference:,}")
            # Use Reference + additional fields to make it unique per line item
            transactions_df.loc[missing_key_mask & transactions_df["reference"].notna(), "dedup_key"] = (
                transactions_df.loc[missing_key_mask & transactions_df["reference"].notna(), "reference"].astype(str) + "_" +
                transactions_df.loc[missing_key_mask & transactions_df["reference"].notna(), "sku"].astype(str) + "_" +
                transactions_df.loc[missing_key_mask & transactions_df["reference"].notna(), "net_revenue"].round(2).astype(str)
            )
            missing_key_mask = transactions_df["dedup_key"].isna()  # Update mask
    
    # For remaining rows without Identifier or Reference, create composite key
    if missing_key_mask.any():
        remaining_count = missing_key_mask.sum()
        print(f"   Transactions without Identifier/Reference: {remaining_count:,} - using composite key")
        # Composite key: datetime + location + sku + quantity + net_revenue (more specific than before)
        transactions_df.loc[missing_key_mask, "dedup_key"] = (
            transactions_df.loc[missing_key_mask, "transaction_datetime"].astype(str) + "_" +
            transactions_df.loc[missing_key_mask, "location"].astype(str) + "_" +
            transactions_df.loc[missing_key_mask, "sku"].astype(str) + "_" +
            transactions_df.loc[missing_key_mask, "quantity"].astype(str) + "_" +
            transactions_df.loc[missing_key_mask, "net_revenue"].round(2).astype(str)
        )
    
    # Deduplicate globally - keep the first occurrence (prefer newer files if processed in order)
    before_dedup = len(transactions_df)
    transactions_df = transactions_df.drop_duplicates(subset=["dedup_key"], keep="first")
    after_dedup = len(transactions_df)
    duplicates_removed = before_dedup - after_dedup
    
    if duplicates_removed > 0:
        print(f"   ⚠️  Removed {duplicates_removed:,} duplicate transactions across files ({duplicates_removed/before_dedup*100:.1f}%)")
        print(f"   This suggests the same transactions appeared in multiple CSV files")
    else:
        print(f"   ✅ No duplicate transactions found across files")
    
    print(f"📊 Final transaction count after global deduplication: {len(transactions_df):,}")
    
    # Remove the temporary dedup_key column
    transactions_df = transactions_df.drop(columns=["dedup_key"], errors="ignore")

    all_products: List[pd.DataFrame] = []
    for file_path in product_files:
        df = read_csv_with_fallback(file_path)
        cleaned = clean_products(df, file_path)
        all_products.append(cleaned)

    products_df = pd.concat(all_products, ignore_index=True) if all_products else pd.DataFrame()
    ledger_df = merge_with_products(transactions_df, products_df)
    ledger_df = ledger_df.sort_values(by=["transaction_datetime", "sku"]).reset_index(drop=True)

    dropbox_destination = None if args.skip_dropbox else args.dropbox_output
    write_outputs(ledger_df, args.output, dropbox_destination)

    # Also write a simple daily sales summary XLSX for Excel linkage.
    write_daily_summary(ledger_df, args.daily_summary_xlsx)

    # And write product-level insight tables (top/bottom and weekly KPIs).
    write_product_insights(ledger_df, args.product_insights_xlsx)

    # Finally, emit a detailed product-period insights CSV for downstream analysis.
    write_product_insights_detailed(ledger_df, args.product_insights_detailed)

    transaction_summaries = summarize_sources(transaction_files, "transactions")
    product_summaries = summarize_sources(product_files, "products")
    metadata = build_metadata(transaction_summaries, product_summaries, args.output)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(metadata, indent=2))

    print(f"✅ Wrote ledger with {len(ledger_df):,} rows to {args.output}")
    if dropbox_destination:
        print(f"☁️  Synced a copy to {dropbox_destination}")
    print(f"ℹ️  Metadata saved to {args.metadata}")


if __name__ == "__main__":
    main()


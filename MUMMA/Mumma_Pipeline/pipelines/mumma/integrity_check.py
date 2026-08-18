"""Data integrity checks for the Mumma revenue ledger.

Run after any pipeline change or manual backfill, before trusting the numbers
in a report. Exits non-zero if a blocking check fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "data" / "mumma" / "processed" / "revenue_ledger.csv"
RAW_TRANSACTIONS = REPO_ROOT / "data" / "mumma" / "raw" / "transactions"
RAW_PRODUCTS = REPO_ROOT / "data" / "mumma" / "raw" / "products"

LEDGER_COLUMNS = [
    "row_uid",
    "transaction_datetime",
    "transaction_date",
    "month",
    "sku",
    "item_name",
    "category",
    "stat_group",
    "quantity",
    "unit_price",
    "gross_revenue",
    "net_revenue",
    "tax_rate",
    "tax_name",
    "discount_amount",
    "comp_amount",
    "profile",
    "account",
    "staff",
    "location",
    "source_file",
]

# Canonical fields the mapper is supposed to populate from every export.
MAPPED_FIELDS = ["stat_group", "profile", "discount_amount", "comp_amount"]

failures: list[str] = []
warnings: list[str] = []


def heading(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


def load_ledger() -> pd.DataFrame:
    df = pd.read_csv(
        LEDGER,
        usecols=lambda c: c in LEDGER_COLUMNS,
        parse_dates=["transaction_datetime"],
        low_memory=False,
    )
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    return df


def check_row_uid_uniqueness(df: pd.DataFrame) -> None:
    heading("1. Duplicate line items (row_uid must be unique)")
    dupes = df["row_uid"].duplicated().sum()
    print(f"Total rows          : {len(df):,}")
    print(f"Distinct row_uid    : {df['row_uid'].nunique():,}")
    print(f"Duplicate row_uid   : {dupes:,}")
    if dupes:
        failures.append(f"{dupes:,} duplicate row_uid values in the ledger")
        worst = df[df["row_uid"].duplicated(keep=False)]
        print("\nSource files involved in duplicates:")
        print(worst["source_file"].value_counts().head(10).to_string())


def check_overlapping_reingest(df: pd.DataFrame) -> None:
    heading("2. Re-ingested periods (27 Jul - 3 Aug 2026 was delivered twice)")
    window = df[
        (df["transaction_date"] >= "2026-07-27") & (df["transaction_date"] < "2026-08-03")
    ]
    print(f"Rows in 27 Jul - 2 Aug window: {len(window):,}")
    print("\nRows contributed per source file:")
    print(window["source_file"].value_counts().to_string())
    revenue = window["net_revenue"].sum()
    print(f"\nNet revenue in window: EUR {revenue:,.0f}")
    if len(window) > 9000:
        failures.append(
            f"27 Jul-2 Aug window holds {len(window):,} rows; a single week is ~8.5k, "
            "suggesting the double delivery was not deduplicated"
        )


def check_date_integrity(df: pd.DataFrame) -> None:
    heading("3. Date parsing (coerced dates vanish from every aggregate)")
    nat = df["transaction_datetime"].isna().sum()
    print(f"Rows with unparseable datetime (NaT): {nat:,}")
    if nat:
        failures.append(f"{nat:,} rows have NaT transaction_datetime")

    latest = df["transaction_date"].max()
    future = (df["transaction_date"] > "2026-08-17").sum()
    print(f"Latest transaction_date            : {latest.date()}")
    print(f"Rows dated after 17 Aug 2026       : {future:,}")
    if future:
        failures.append(
            f"{future:,} rows dated in the future - likely a DD/MM vs MM/DD flip "
            "moving August revenue into later months"
        )

    print("\nMonthly row counts and revenue, Jun 2026 onward:")
    recent = df[df["transaction_date"] >= "2026-06-01"]
    monthly = recent.groupby("month").agg(
        rows=("row_uid", "size"),
        revenue=("net_revenue", "sum"),
        first_day=("transaction_date", "min"),
        last_day=("transaction_date", "max"),
    )
    print(monthly.to_string())


def check_silent_zeroing(df: pd.DataFrame) -> None:
    heading("4. Silent numeric coercion (normalize_number returns 0.0 on failure)")
    recent = df[df["transaction_date"] >= "2026-05-01"].copy()
    recent["ym"] = recent["transaction_date"].dt.to_period("M").astype(str)
    stats = recent.groupby("ym").apply(
        lambda g: pd.Series(
            {
                "rows": len(g),
                "unit_price_zero_pct": (g["unit_price"].fillna(0) == 0).mean() * 100,
                "net_revenue_zero_pct": (g["net_revenue"].fillna(0) == 0).mean() * 100,
                "net_revenue_neg_pct": (g["net_revenue"].fillna(0) < 0).mean() * 100,
                "mean_line_value": g["net_revenue"].mean(),
            }
        ),
        include_groups=False,
    )
    print(stats.to_string(float_format=lambda v: f"{v:,.2f}"))
    print(
        "\nA jump in the zero percentages after the July export change would mean "
        "revenue is being parsed away rather than genuinely lost."
    )


def check_mapped_fields(df: pd.DataFrame) -> None:
    heading("5. Mapper coverage (French export headers are not in the mapping table)")
    recent = df[df["transaction_date"] >= "2026-01-01"].copy()
    recent["ym"] = recent["transaction_date"].dt.to_period("M").astype(str)
    null_pct = recent.groupby("ym")[MAPPED_FIELDS].apply(lambda g: g.isna().mean() * 100)
    print("Percent NULL by month:")
    print(null_pct.to_string(float_format=lambda v: f"{v:,.1f}"))

    latest = recent[recent["transaction_date"] >= "2026-08-01"]
    for field in MAPPED_FIELDS:
        if latest[field].isna().mean() > 0.99:
            warnings.append(
                f"'{field}' is ~100% NULL for August 2026 - mapper did not match the "
                "French column name in the emailed export"
            )


def check_location_split(df: pd.DataFrame) -> None:
    heading("6. Location split (derived from a 'shack' substring in Device_Name)")
    recent = df[df["transaction_date"] >= "2026-06-01"].copy()
    recent["ym"] = recent["transaction_date"].dt.to_period("M").astype(str)
    pivot = recent.pivot_table(
        index="ym", columns="location", values="net_revenue", aggfunc="sum"
    )
    print("Net revenue by location:")
    print(pivot.to_string(float_format=lambda v: f"{v:,.0f}"))
    if "Shack" not in pivot.columns or pivot.get("Shack", pd.Series()).fillna(0).eq(0).any():
        failures.append("Shack revenue missing for at least one recent month")

    # A location that goes dark for a day is either a genuine closure or a partial
    # export. Either way it must be explained before a YoY number is published.
    recent_30 = df[df["transaction_date"] >= df["transaction_date"].max() - pd.Timedelta(days=30)]
    traded = recent_30.pivot_table(
        index=recent_30["transaction_date"].dt.date,
        columns="location",
        values="net_revenue",
        aggfunc="sum",
    )
    dark = traded[traded.isna().any(axis=1)]
    print(f"\nDays in the last 30 where a location recorded no sales: {len(dark)}")
    if not dark.empty:
        print(dark.to_string(float_format=lambda v: f"{v:,.0f}"))
        warnings.append(
            f"{len(dark)} day(s) in the last 30 have no sales for one location "
            f"({', '.join(str(d) for d in dark.index)}) - confirm closure vs missing export"
        )


def check_august_comparison(df: pd.DataFrame) -> None:
    heading("7. Like-for-like August 1-16, by year")
    aug = df[(df["transaction_date"].dt.month == 8) & (df["transaction_date"].dt.day <= 16)].copy()
    aug["year"] = aug["transaction_date"].dt.year
    summary = aug.groupby("year").agg(
        rows=("row_uid", "size"),
        tickets=("account", "nunique"),
        revenue=("net_revenue", "sum"),
        trading_days=("transaction_date", "nunique"),
    )
    summary["avg_ticket"] = summary["revenue"] / summary["tickets"]
    summary["revenue_per_day"] = summary["revenue"] / summary["trading_days"]
    summary["yoy_pct"] = summary["revenue"].pct_change() * 100
    print(summary.to_string(float_format=lambda v: f"{v:,.2f}"))

    print("\nBy location:")
    loc = aug.pivot_table(index="year", columns="location", values="net_revenue", aggfunc="sum")
    print(loc.to_string(float_format=lambda v: f"{v:,.0f}"))

    print("\nDaily revenue, August 2026 vs 2025:")
    daily = aug[aug["year"].isin([2025, 2026])].copy()
    daily["day"] = daily["transaction_date"].dt.day
    print(
        daily.pivot_table(index="day", columns="year", values="net_revenue", aggfunc="sum")
        .to_string(float_format=lambda v: f"{v:,.0f}")
    )


def check_raw_transaction_types() -> None:
    heading("8. Raw export 'Type' distribution ('Type' is dropped from the ledger)")
    files = sorted(RAW_TRANSACTIONS.glob("2026*transactions*.csv"))[-6:]
    for path in files:
        try:
            raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        except Exception as exc:  # noqa: BLE001
            print(f"{path.name}: unreadable ({exc})")
            continue
        final_price = pd.to_numeric(raw.get("FinalPrice"), errors="coerce")
        grouped = raw.assign(_fp=final_price).groupby("Type")["_fp"].agg(["size", "sum"])
        print(f"\n{path.name}")
        print(grouped.to_string(float_format=lambda v: f"{v:,.0f}"))


# The product breakdown export covers a trailing ~21 days despite the weekly date
# range in its filename. Verified empirically: the product/ledger ratio sits at
# ~3.0 for a 7-day window and ~1.0 for a 21-day window across every week tested.
PRODUCT_EXPORT_WINDOW_DAYS = 21


def check_product_reconciliation(df: pd.DataFrame) -> None:
    heading("9. Independent reconciliation against the product breakdown exports")
    files = sorted(RAW_PRODUCTS.glob("2026*product_breakdown*.csv"))[-3:]
    for path in files:
        prod = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        amount_col = next(
            (c for c in prod.columns if c.strip().lower() == "total montant"), None
        )
        if amount_col is None:
            print(f"{path.name}: no amount column found")
            continue
        # Filename tail is ..._<start>_<end>.csv
        end = pd.Timestamp(path.stem.split("_")[-1])
        start = end - pd.Timedelta(days=PRODUCT_EXPORT_WINDOW_DAYS)

        product_total = pd.to_numeric(prod[amount_col], errors="coerce").sum()
        window = df[(df["transaction_date"] >= start) & (df["transaction_date"] < end)]
        ledger_total = window["net_revenue"].sum()
        pct = ((ledger_total - product_total) / product_total * 100) if product_total else float("nan")
        print(f"\n{start.date()} -> {end.date()} ({PRODUCT_EXPORT_WINDOW_DAYS}d)")
        print(f"  product export ({amount_col}): EUR {product_total:,.0f}")
        print(f"  ledger net_revenue          : EUR {ledger_total:,.0f}")
        print(f"  delta                       : {pct:+.1f}%")
        if product_total and abs(pct) > 10:
            failures.append(
                f"Ledger and product export disagree by {pct:+.1f}% for the "
                f"{PRODUCT_EXPORT_WINDOW_DAYS}d window ending {end.date()}"
            )


def main() -> int:
    print(f"Ledger: {LEDGER}")
    df = load_ledger()

    check_row_uid_uniqueness(df)
    check_overlapping_reingest(df)
    check_date_integrity(df)
    check_silent_zeroing(df)
    check_mapped_fields(df)
    check_location_split(df)
    check_august_comparison(df)
    check_raw_transaction_types()
    check_product_reconciliation(df)

    heading("RESULT")
    for warning in warnings:
        print(f"WARN  {warning}")
    for failure in failures:
        print(f"FAIL  {failure}")
    if not failures and not warnings:
        print("All checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

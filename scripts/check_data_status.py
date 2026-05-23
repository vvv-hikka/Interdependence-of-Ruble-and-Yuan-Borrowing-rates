"""
Print status of all base tables: shape, date range, and null fraction.
No pipeline or network calls. Run from project root: python scripts/check_data_status.py
"""

try:
    from config import BASE_TABLES_FOR_COMBINED_VIEW, WEEKLY_BASE_TABLES
except ImportError:
    BASE_TABLES_FOR_COMBINED_VIEW = [
        'cbr_key_rate', 'cbr_gcurve', 'currency_rates', 'russian_bond_yields',
        'russian_macro', 'pboc_lpr', 'chinese_bond_yields', 'chinese_macro',
        'global_indicators', 'business_activity',
        'risk_sentiment', 'commodities', 'russia_money_markets', 'china_money_markets',
    ]
    WEEKLY_BASE_TABLES = [
        'russian_bond_yields_weekly', 'cbr_gcurve_weekly', 'currency_rates_weekly',
        'chinese_bond_yields_weekly', 'global_indicators_weekly', 'risk_sentiment_weekly',
    ]

from src.database import DatabaseManager


def _report_tables(db, tables, label):
    existing = set(db.list_tables())
    total = len(tables)
    present = 0
    print(f"\n{label}")
    print("=" * 60)
    for table in tables:
        if table not in existing:
            print(f"{table}: MISSING")
            continue
        df = db.load_dataframe(table)
        if df.empty:
            print(f"{table}: EMPTY")
            continue
        present += 1
        rows, cols = df.shape
        date_range = ""
        if 'date' in df.columns:
            df['date'] = df['date'].astype('datetime64[ns]')
            date_range = f"{df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}"
        null_pct = (df.isna().sum().sum() / (rows * cols) * 100) if rows and cols else 0
        print(f"{table}: {rows} rows, {cols} cols, {null_pct:.1f}% null")
        if date_range:
            print(f"  date range: {date_range}")
    coverage = (present / total * 100) if total else 0.0
    print(f"Coverage: {present}/{total} tables present ({coverage:.1f}%)")
    print("=" * 60)


def main():
    db = DatabaseManager()
    _report_tables(db, BASE_TABLES_FOR_COMBINED_VIEW, "Monthly base tables")
    _report_tables(db, WEEKLY_BASE_TABLES, "Weekly base tables")


if __name__ == "__main__":
    main()

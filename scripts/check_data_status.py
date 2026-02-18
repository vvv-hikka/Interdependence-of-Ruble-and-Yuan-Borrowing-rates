"""
Print status of all base tables: shape, date range, and null fraction.
No pipeline or network calls. Run from project root: python scripts/check_data_status.py
"""

try:
    from config import BASE_TABLES_FOR_COMBINED_VIEW
except ImportError:
    BASE_TABLES_FOR_COMBINED_VIEW = [
        'cbr_key_rate', 'cbr_gcurve', 'currency_rates', 'russian_bond_yields',
        'russian_macro', 'pboc_lpr', 'chinese_bond_yields', 'chinese_macro',
        'global_indicators', 'business_activity',
    ]

from src.database import DatabaseManager


def main():
    db = DatabaseManager()
    print("Data status (base tables)")
    print("=" * 60)
    for table in BASE_TABLES_FOR_COMBINED_VIEW:
        df = db.load_dataframe(table)
        if df.empty:
            print(f"{table}: no data")
            continue
        rows, cols = df.shape
        date_range = ""
        if 'date' in df.columns:
            df['date'] = df['date'].astype('datetime64[ns]')
            date_range = f"{df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}"
        null_pct = (df.isna().sum().sum() / (rows * cols) * 100) if rows and cols else 0
        print(f"{table}: {rows} rows, {cols} cols, {null_pct:.1f}% null")
        if date_range:
            print(f"  date range: {date_range}")
    print("=" * 60)


if __name__ == "__main__":
    main()

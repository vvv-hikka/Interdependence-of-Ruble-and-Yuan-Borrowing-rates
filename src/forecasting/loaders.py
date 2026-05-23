"""
Load yield curves and macro indicators from the database.
"""

import pandas as pd
from pathlib import Path
from typing import Optional

try:
    from config import DB_PATH, WEEKLY_BASE_TABLES
except ImportError:
    DB_PATH = Path(__file__).parent.parent.parent / "bond_rates_database.db"
    WEEKLY_BASE_TABLES = [
        'russian_bond_yields_weekly', 'cbr_gcurve_weekly', 'currency_rates_weekly',
        'chinese_bond_yields_weekly', 'global_indicators_weekly', 'risk_sentiment_weekly',
    ]

try:
    from src.database import DatabaseManager
except ImportError:
    DatabaseManager = None


def _normalise_to_month_end(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise the 'date' column to month-end and keep the last row per month."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]) + pd.offsets.MonthEnd(0)
    # If multiple source rows fall in the same month-end, combine_first them
    df = df.set_index("date")
    df = df.groupby(level=0).last()  # keep row with most-recent data per month
    return df.reset_index()


def _load_ru_yields(db: "DatabaseManager") -> pd.DataFrame:
    """Load Russian yields from cbr_gcurve + russian_bond_yields."""
    gcurve = db.load_dataframe("cbr_gcurve")
    ofz = db.load_dataframe("russian_bond_yields")
    if gcurve.empty and ofz.empty:
        return pd.DataFrame()
    if gcurve.empty:
        return _normalise_to_month_end(ofz)
    if ofz.empty:
        return _normalise_to_month_end(gcurve)
    # Normalise each table to month-end before merging so dates align properly
    gcurve = _normalise_to_month_end(gcurve)
    ofz = _normalise_to_month_end(ofz)
    result = gcurve.merge(ofz, on="date", how="outer", suffixes=("", "_dup"))
    for dup in [c for c in result.columns if c.endswith("_dup")]:
        base = dup.replace("_dup", "")
        if base in result.columns:
            result[base] = result[base].combine_first(result[dup])
        result = result.drop(columns=[dup])
    return result.sort_values("date")


def _coalesce_cn_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Merge duplicate CN_* columns (e.g. CN_1Y_x, CN_1Y_y) into single CN_*."""
    import re
    base_to_cols = {}
    for c in df.columns:
        if not c.startswith("CN_"):
            continue
        base = re.sub(r"_(x|y|dup)$", "", c)
        base_to_cols.setdefault(base, []).append(c)
    result = df.copy()
    for base, cols in base_to_cols.items():
        if len(cols) == 1 and cols[0] == base:
            continue
        if len(cols) == 1:
            result = result.rename(columns={cols[0]: base})
            continue
        # Prefer base if present, else first column
        first = base if base in cols else cols[0]
        result[base] = result[first].copy()
        for col in cols:
            if col != base:
                result[base] = result[base].combine_first(result[col])
        drop = [c for c in cols if c != base]
        if drop:
            result = result.drop(columns=drop)
    return result


def _load_cn_yields(db: "DatabaseManager") -> pd.DataFrame:
    """Load Chinese yields from chinese_bond_yields (coalesce duplicate CN_* columns)."""
    df = db.load_dataframe("chinese_bond_yields")
    if df.empty:
        return df
    return _coalesce_cn_columns(df)


def load_russian_yield_curve(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load Russian yield curve from DB.
    
    Returns:
        DataFrame with date index and RU_* columns (e.g. RU_1Y, RU_2Y).
    """
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = _load_ru_yields(db)
    if df.empty:
        return pd.DataFrame()
    yield_cols = [c for c in df.columns if c.startswith("RU_")]
    df = df[["date"] + yield_cols].copy()
    df["date"] = pd.to_datetime(df["date"])
    # Month-end normalisation already done in _load_ru_yields; dates are clean here
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    df = df.set_index("date")
    return df[yield_cols]


def load_chinese_yield_curve(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load Chinese yield curve from DB.
    
    Returns:
        DataFrame with date index and CN_* columns.
    """
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = _load_cn_yields(db)
    if df.empty:
        return pd.DataFrame()
    yield_cols = sorted([c for c in df.columns if c.startswith("CN_")])
    if not yield_cols:
        return pd.DataFrame()
    df = df[["date"] + yield_cols].copy()
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    df = df.set_index("date")
    return df[yield_cols]


def load_global_indicators(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load FRED global indicators (US rates, oil, USD index) for yield-forecasting context.
    """
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = db.load_dataframe("global_indicators")
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    return df.set_index("date")


def load_macro_indicators(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load FRED-backed macro tables (global_indicators, russian_macro, chinese_macro).
    
    Returns:
        DataFrame with date index and all macro columns.
    """
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    tables = ["global_indicators", "russian_macro", "chinese_macro"]
    combined = None
    for t in tables:
        df = db.load_dataframe(t)
        if df.empty or "date" not in df.columns:
            continue
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        cols = [c for c in df.columns if c != "date"]
        df = df.rename(columns={c: f"{t}_{c}" for c in cols})
        if combined is None:
            combined = df
        else:
            combined = combined.merge(df, on="date", how="outer")
    if combined is None:
        return pd.DataFrame()
    combined = combined.sort_values("date")
    if start_date:
        combined = combined[combined["date"] >= pd.to_datetime(start_date)]
    if end_date:
        combined = combined[combined["date"] <= pd.to_datetime(end_date)]
    return combined.set_index("date")


# =============================================================================
# WEEKLY LOADERS
# =============================================================================

def _load_ru_yields_weekly(db: "DatabaseManager") -> pd.DataFrame:
    """Load Russian weekly yields: cbr_gcurve_weekly filled with russian_bond_yields_weekly."""
    gcurve = db.load_dataframe("cbr_gcurve_weekly")
    ofz = db.load_dataframe("russian_bond_yields_weekly")
    if gcurve.empty and ofz.empty:
        return pd.DataFrame()
    if gcurve.empty:
        return ofz
    if ofz.empty:
        return gcurve
    result = gcurve.merge(ofz, on="date", how="outer", suffixes=("", "_dup"))
    for dup in [c for c in result.columns if c.endswith("_dup")]:
        base = dup.replace("_dup", "")
        if base in result.columns:
            result[base] = result[base].combine_first(result[dup])
        result = result.drop(columns=[dup])
    return result.sort_values("date")


def load_russian_yield_curve_weekly(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load Russian weekly yield curve from DB.

    Returns:
        DataFrame with date index and RU_* columns.
    """
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = _load_ru_yields_weekly(db)
    if df.empty:
        return pd.DataFrame()
    yield_cols = [c for c in df.columns if c.startswith("RU_")]
    df = df[["date"] + yield_cols].copy()
    df["date"] = pd.to_datetime(df["date"])
    # Normalise to week-end (already W-FRI) — keep consistent with monthly fix
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    return df.set_index("date")[yield_cols]


def load_chinese_yield_curve_weekly(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load Chinese weekly yield curve from DB.

    Returns:
        DataFrame with date index and CN_* columns.
    """
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = db.load_dataframe("chinese_bond_yields_weekly")
    if df.empty:
        return pd.DataFrame()
    df = _coalesce_cn_columns(df)
    yield_cols = sorted([c for c in df.columns if c.startswith("CN_")])
    if not yield_cols:
        return pd.DataFrame()
    df = df[["date"] + yield_cols].copy()
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    return df.set_index("date")[yield_cols]


def load_currency_rates_weekly(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load weekly currency rates (USD/RUB, CNY/RUB, EUR/RUB).
    """
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = db.load_dataframe("currency_rates_weekly")
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    cols = [c for c in ["usd_rub", "cny_rub", "eur_rub"] if c in df.columns]
    if not cols:
        return pd.DataFrame()
    return df.set_index("date")[cols].sort_index()


def load_combined_weekly(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Load the combined_weekly view from DB."""
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = db.load_dataframe("combined_weekly")
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    return df.set_index("date")

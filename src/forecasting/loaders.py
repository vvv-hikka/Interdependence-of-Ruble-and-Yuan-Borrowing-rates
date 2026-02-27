"""
Load yield curves and macro indicators from the database.
"""

import pandas as pd
from pathlib import Path
from typing import Optional

try:
    from config import DB_PATH
except ImportError:
    DB_PATH = Path(__file__).parent.parent.parent / "bond_rates_database.db"

try:
    from src.database import DatabaseManager
except ImportError:
    DatabaseManager = None


def _load_ru_yields(db: "DatabaseManager") -> pd.DataFrame:
    """Load Russian yields from cbr_gcurve + russian_bond_yields."""
    gcurve = db.load_dataframe("cbr_gcurve")
    ofz = db.load_dataframe("russian_bond_yields")
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


def _load_cn_yields(db: "DatabaseManager") -> pd.DataFrame:
    """Load Chinese yields from chinese_bond_yields."""
    return db.load_dataframe("chinese_bond_yields")


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
    yield_cols = [c for c in df.columns if c.startswith("CN_")]
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

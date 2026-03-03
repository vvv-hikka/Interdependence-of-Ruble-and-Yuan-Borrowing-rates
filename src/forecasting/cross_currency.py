"""
RUB–CNY yield spread construction at matched maturities.
"""

import re
import numpy as np
import pandas as pd
from typing import Optional, Tuple

# Maturity mapping: RU uses RU_1Y, CN uses CN_1Y
MATURITY_ALIAS = {
    "1Y": ("RU_1Y", "CN_1Y"),
    "2Y": ("RU_2Y", "CN_2Y"),
    "3Y": ("RU_3Y", "CN_3Y"),
    "5Y": ("RU_5Y", "CN_5Y"),
    "7Y": ("RU_7Y", "CN_7Y"),
    "10Y": ("RU_10Y", "CN_10Y"),
}


def _parse_mat_num(m: str) -> float:
    """Extract numeric part for sorting (1Y->1, 6M->0.5)."""
    n = re.search(r"(\d+)", m)
    if not n:
        return 0
    val = float(n.group(1))
    return val / 12.0 if "M" in m.upper() else val


def _normalize_maturity(col: str, prefix: str) -> str:
    """Extract maturity from column, stripping _x/_y suffixes (e.g. CN_1Y_x -> 1Y)."""
    import re
    if not col.startswith(prefix):
        return ""
    mat = col.replace(prefix, "", 1)
    mat = re.sub(r"_(x|y|dup)$", "", mat)
    return mat


def _common_maturities(ru_cols: list, cn_cols: list) -> list:
    """Return maturities where both curves have data. Normalizes CN_1Y_x -> 1Y for matching."""
    ru_set = set(_normalize_maturity(c, "RU_") for c in ru_cols if c.startswith("RU_"))
    cn_set = set(_normalize_maturity(c, "CN_") for c in cn_cols if c.startswith("CN_"))
    ru_set.discard("")
    cn_set.discard("")
    common = sorted(ru_set & cn_set, key=lambda m: _parse_mat_num(m))
    return common


def build_spreads(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build RUB–CNY spread series at matched maturities.
    
    Spread = RU yield - CN yield (RUB - CNY).
    
    Returns:
        DataFrame with date index and columns like spread_1Y, spread_5Y.
    """
    # Coerce to numeric (RU may have object/None from DB)
    ru_yields = ru_yields.copy()
    cn_yields = cn_yields.copy()
    for c in ru_yields.columns:
        ru_yields[c] = pd.to_numeric(ru_yields[c], errors="coerce")
    for c in cn_yields.columns:
        cn_yields[c] = pd.to_numeric(cn_yields[c], errors="coerce")

    # Merge on month (RU uses 1st-of-month, CN uses end-of-month - align to month-end)
    ru = ru_yields.reset_index()
    cn = cn_yields.reset_index()
    ru = ru.rename(columns={ru.columns[0]: "date"})
    cn = cn.rename(columns={cn.columns[0]: "date"})
    ru["date"] = pd.to_datetime(ru["date"])
    cn["date"] = pd.to_datetime(cn["date"])
    # Align to month-end so 2019-02-01 (RU) matches 2019-02-28 (CN)
    ru["month"] = ru["date"].dt.to_period("M").dt.to_timestamp("M")
    cn["month"] = cn["date"].dt.to_period("M").dt.to_timestamp("M")
    merged = ru.merge(cn, on="month", how="inner", suffixes=("_ru", "_cn"))
    if merged.empty:
        return pd.DataFrame()
    # Use month (month-end) as index; drop duplicate date columns
    merged = merged.drop(columns=[c for c in merged.columns if c in ("date_ru", "date_cn", "date")], errors="ignore")
    common_dates = merged["month"]
    ru_a = merged[[c for c in merged.columns if c.startswith("RU_")]].set_index(common_dates)
    cn_a = merged[[c for c in merged.columns if c.startswith("CN_")]].set_index(common_dates)
    
    maturities = _common_maturities(ru_yields.columns.tolist(), cn_yields.columns.tolist())
    if not maturities:
        return pd.DataFrame()
    
    def _find_col(df: pd.DataFrame, prefix: str, mat: str) -> Optional[str]:
        """Find column for maturity (e.g. CN_1Y or CN_1Y_x)."""
        cand = f"{prefix}{mat}"
        if cand in df.columns:
            return cand
        for suffix in ("_x", "_y"):
            if f"{cand}{suffix}" in df.columns:
                return f"{cand}{suffix}"
        return None

    spreads = pd.DataFrame(index=common_dates)
    for mat in maturities:
        ru_col = _find_col(ru_a, "RU_", mat)
        cn_col = _find_col(cn_a, "CN_", mat)
        if ru_col is not None and cn_col is not None:
            s = ru_a[ru_col] - cn_a[cn_col]
            spreads[f"spread_{mat}"] = s

    return spreads.dropna(how="all")


def flag_abnormal_spreads(
    spreads_df: pd.DataFrame,
    z_threshold: float = 2.0,
    roll_window: int = 12,
) -> pd.DataFrame:
    """
    Add Z-score based flags for abnormal spreads.
    
    Returns:
        spreads_df with additional columns *_abnormal (bool).
    """
    result = spreads_df.copy()
    for col in spreads_df.columns:
        if not col.startswith("spread_"):
            continue
        roll = spreads_df[col].rolling(roll_window, min_periods=3)
        mean = roll.mean()
        std = roll.std()
        z = np.abs((spreads_df[col] - mean) / std.replace(0, np.nan))
        result[f"{col}_abnormal"] = z > z_threshold
    return result

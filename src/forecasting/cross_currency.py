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


def _common_maturities(ru_cols: list, cn_cols: list) -> list:
    """Return maturities where both curves have data."""
    ru_set = set(c.replace("RU_", "") for c in ru_cols if c.startswith("RU_"))
    cn_set = set(c.replace("CN_", "") for c in cn_cols if c.startswith("CN_"))
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
    # Align on date
    common_dates = ru_yields.index.intersection(cn_yields.index)
    if len(common_dates) == 0:
        return pd.DataFrame()
    
    ru_a = ru_yields.loc[common_dates]
    cn_a = cn_yields.loc[common_dates]
    
    maturities = _common_maturities(ru_yields.columns.tolist(), cn_yields.columns.tolist())
    if not maturities:
        return pd.DataFrame()
    
    spreads = pd.DataFrame(index=common_dates)
    for mat in maturities:
        ru_col = f"RU_{mat}"
        cn_col = f"CN_{mat}"
        if ru_col in ru_a.columns and cn_col in cn_a.columns:
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

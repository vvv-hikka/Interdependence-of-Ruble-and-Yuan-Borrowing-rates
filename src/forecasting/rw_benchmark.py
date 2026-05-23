"""
Random Walk benchmark for yield curve forecasting.

For each maturity, the h-step-ahead forecast equals the last observed yield.
This is the standard baseline in the yield curve forecasting literature —
any model that cannot beat it should not be used in practice.
"""

from __future__ import annotations

import pandas as pd
from typing import Dict, Optional


def forecast_random_walk(
    yields_df: pd.DataFrame,
    horizon: int = 1,
    last_row: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Random walk forecast for a single yield curve.

    Args:
        yields_df: DataFrame with date index and yield columns.
        horizon: Number of periods to forecast.
        last_row: Override the starting observation. If None, uses the last row.

    Returns:
        DataFrame indexed by horizon step (1..horizon), same columns as yields_df.
        Every row is identical to the last observed yield.
    """
    if last_row is None:
        last_row = yields_df.iloc[-1]

    records = []
    for h in range(1, horizon + 1):
        row = last_row.copy()
        row['horizon'] = h
        records.append(row)

    return pd.DataFrame(records).set_index('horizon')


def forecast_random_walk_both(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    horizon: int = 1,
) -> Dict[str, pd.DataFrame]:
    """
    Random walk forecast for both RU and CN yield curves.

    Returns:
        Dict with keys 'ru' and 'cn'.
    """
    return {
        'ru': forecast_random_walk(ru_yields, horizon),
        'cn': forecast_random_walk(cn_yields, horizon),
    }

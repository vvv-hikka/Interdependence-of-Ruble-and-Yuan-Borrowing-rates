"""
Portfolio and risk layer for RUB/CNY strategy integration.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_signal_score(snapshot_df: pd.DataFrame) -> float:
    """
    Convert signal snapshot rows into a bounded score in [-1, 1].
    """
    if snapshot_df is None or snapshot_df.empty:
        return 0.0
    weighted = snapshot_df["direction"].astype(float) * snapshot_df["confidence"].astype(float)
    score = float(weighted.mean()) if len(weighted) else 0.0
    return float(np.clip(score, -1.0, 1.0))


def signal_to_weights(
    score: float,
    prev_weights: dict | None = None,
    max_turnover: float = 0.30,
    liquidity_cap: float = 0.80,
) -> dict:
    """
    Map signal score into RUB/CNY allocation with turnover and liquidity constraints.
    """
    prev = prev_weights or {"RUB": 0.5, "CNY": 0.5}
    target_rub = 0.5 + 0.3 * score
    target_rub = float(np.clip(target_rub, 1.0 - liquidity_cap, liquidity_cap))
    target_cny = 1.0 - target_rub

    # Turnover cap (L1 half-turnover approximation for two assets)
    delta = target_rub - prev["RUB"]
    delta = float(np.clip(delta, -max_turnover / 2.0, max_turnover / 2.0))
    rub = prev["RUB"] + delta
    cny = 1.0 - rub
    return {"RUB": round(rub, 6), "CNY": round(cny, 6)}


def portfolio_var_95(weights: dict, vol_rub: float, vol_cny: float, corr: float = 0.0) -> float:
    """
    1-period parametric VaR(95%) for two-asset basket (normal approximation).
    """
    w1, w2 = float(weights["RUB"]), float(weights["CNY"])
    var_p = (
        w1 ** 2 * vol_rub ** 2
        + w2 ** 2 * vol_cny ** 2
        + 2.0 * w1 * w2 * corr * vol_rub * vol_cny
    )
    sigma = float(np.sqrt(max(var_p, 0.0)))
    z95 = 1.645
    return z95 * sigma


def apply_var_limit(weights: dict, var_95: float, var_limit: float) -> dict:
    """
    If VaR exceeds limit, shrink from active weights toward 50/50 baseline.
    """
    if var_95 <= var_limit or var_95 <= 0:
        return weights
    shrink = float(np.clip(var_limit / var_95, 0.0, 1.0))
    rub = 0.5 + (weights["RUB"] - 0.5) * shrink
    cny = 1.0 - rub
    return {"RUB": round(rub, 6), "CNY": round(cny, 6)}


"""
Portfolio and risk layer for RUB/CNY strategy integration.
"""

from __future__ import annotations

import numpy as np


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

    delta = target_rub - prev["RUB"]
    delta = float(np.clip(delta, -max_turnover / 2.0, max_turnover / 2.0))
    rub = prev["RUB"] + delta
    cny = 1.0 - rub
    return {"RUB": round(rub, 6), "CNY": round(cny, 6)}


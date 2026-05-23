"""
AER (Gao & Hyndman style) – placeholder for future implementation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.forecasting.ns_baseline import get_fitted_curves, compute_residuals


def run_aer(yields_df: pd.DataFrame, lambda_aer: float = 0.1) -> dict:
    """
    Minimal AER-style proxy:
      1) Fit baseline NS (fitted, residuals)
      2) Penalize curvature instability via second-difference smoothness term
      3) Return adjusted score and diagnostics

    This is NOT a full HJM-consistent neural filter, but provides a reproducible
    benchmark-compatible placeholder for experimentation and report comparison.
    """
    if yields_df is None or yields_df.empty:
        return {"error": "Empty yields_df"}

    fitted = get_fitted_curves(yields_df)
    residuals = compute_residuals(yields_df)
    if fitted.empty or residuals.empty:
        return {"error": "NS fit failed"}

    # Arbitrage-proxy penalty: second differences across maturities for each date
    # (large oscillations imply implausible local forward-curve shape).
    penalty_rows = []
    fit_cols = [c for c in fitted.columns if c.startswith(("RU_", "CN_"))]
    for _, row in fitted[fit_cols].iterrows():
        vals = row.dropna().values.astype(float)
        if len(vals) < 3:
            penalty_rows.append(np.nan)
            continue
        second_diff = np.diff(vals, n=2)
        penalty_rows.append(float(np.nanmean(second_diff ** 2)))
    penalty = pd.Series(penalty_rows, index=fitted.index, name="aer_penalty")

    mse = (residuals[fit_cols] ** 2).mean(axis=1, skipna=True)
    objective = mse + lambda_aer * penalty

    return {
        "lambda_aer": lambda_aer,
        "mse_mean": float(np.nanmean(mse)),
        "penalty_mean": float(np.nanmean(penalty)),
        "objective_mean": float(np.nanmean(objective)),
        "penalty_series": penalty,
        "objective_series": objective,
    }

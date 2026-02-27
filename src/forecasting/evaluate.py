"""
Evaluation helpers for NS fit and cross-currency spreads.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any


def evaluate_ns_fit(
    observed: pd.DataFrame,
    fitted: pd.DataFrame,
    residuals: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Compute MAE, RMSE, and residual stats for Nelson-Siegel fit.
    
    Returns:
        Dict with MAE, RMSE by maturity and overall, residual mean/std/max_abs.
    """
    results = {"by_maturity": {}, "overall": {}}
    valid_cols = [c for c in observed.columns if c in fitted.columns and c in residuals.columns]
    if not valid_cols:
        return results
    
    all_mae = []
    all_rmse = []
    all_resid = []
    for col in valid_cols:
        o = observed[col]
        f = fitted[col]
        r = residuals[col]
        valid = o.notna() & f.notna() & r.notna()
        if valid.sum() == 0:
            continue
        diff = (o - f).loc[valid]
        mae = diff.abs().mean()
        rmse = np.sqrt((diff ** 2).mean())
        results["by_maturity"][col] = {"MAE": float(mae), "RMSE": float(rmse)}
        all_mae.append(float(mae))
        all_rmse.append(float(rmse))
        all_resid.extend(r.loc[valid].tolist())
    
    if all_mae:
        all_resid = [x for x in all_resid if pd.notna(x)]
        results["overall"] = {
            "MAE_mean": float(np.nanmean(all_mae)),
            "RMSE_mean": float(np.nanmean(all_rmse)),
            "residual_mean": float(np.nanmean(all_resid)) if all_resid else 0,
            "residual_std": float(np.nanstd(all_resid)) if all_resid else 0,
            "residual_max_abs": float(np.nanmax(np.abs(all_resid))) if all_resid else 0,
        }
    return results


def evaluate_spreads(
    spreads_df: pd.DataFrame,
    flagged_df: pd.DataFrame = None,
) -> Dict[str, Any]:
    """
    Summary stats of spread distribution and frequency of abnormal flags.
    """
    results = {"spread_stats": {}, "abnormal_counts": {}}
    spread_cols = [c for c in spreads_df.columns if c.startswith("spread_")]
    for col in spread_cols:
        s = spreads_df[col].dropna()
        if len(s) > 0:
            results["spread_stats"][col] = {
                "mean": s.mean(),
                "std": s.std(),
                "min": s.min(),
                "max": s.max(),
                "count": len(s),
            }
    
    if flagged_df is not None:
        for col in flagged_df.columns:
            if col.endswith("_abnormal"):
                results["abnormal_counts"][col] = flagged_df[col].sum()
    return results

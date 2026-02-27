"""
Nelson-Siegel yield curve fitting.
"""

import re
import numpy as np
import pandas as pd
from typing import Tuple, Optional
from scipy.optimize import minimize


def _parse_maturity(col: str) -> Optional[float]:
    """Extract maturity in years from column name (e.g. RU_1Y -> 1, CN_6M -> 0.5)."""
    col = str(col).upper()
    m = re.search(r"(\d+)\s*Y", col)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)\s*M", col)
    if m:
        return float(m.group(1)) / 12.0
    return None


def _ns_curve(tau: np.ndarray, beta: np.ndarray, lam: float) -> np.ndarray:
    """Nelson-Siegel curve: y(tau) = beta0 + beta1*f1 + beta2*f2."""
    x = np.where(tau > 1e-8, tau / lam, 1e-8)
    f1 = (1 - np.exp(-x)) / x
    f2 = f1 - np.exp(-x)
    return beta[0] + beta[1] * f1 + beta[2] * f2


def _ns_objective(params: np.ndarray, tau: np.ndarray, y_obs: np.ndarray,
                  lam: float) -> float:
    """Objective for NS fit: sum of squared residuals."""
    beta = params[:3]
    y_fit = _ns_curve(tau, beta, lam)
    return np.nansum((y_obs - y_fit) ** 2)


def fit_nelson_siegel(row: pd.Series, lam: float = 2.0) -> Tuple[dict, dict]:
    """
    Fit Nelson-Siegel to a row of yields by maturity.
    
    Args:
        row: Series with yield columns (e.g. RU_1Y, RU_2Y)
        lam: Decay parameter (default 2.0)
    
    Returns:
        (fitted_dict, residuals_dict) mapping column -> value for each valid maturity.
    """
    cols_used = []
    tau_list = []
    y_list = []
    for col in row.index:
        t = _parse_maturity(col)
        if t is not None and pd.notna(row[col]):
            cols_used.append(col)
            tau_list.append(t)
            y_list.append(float(row[col]))
    if len(tau_list) < 4:
        return {}, {}
    tau = np.array(tau_list)
    y_obs = np.array(y_list)
    
    # Initial guess: level=mean, slope=-0.5, curvature=0
    x0 = np.array([np.nanmean(y_obs), -0.5, 0.0])
    bounds = [(0, 20), (-10, 10), (-10, 10)]
    res = minimize(_ns_objective, x0, args=(tau, y_obs, lam),
                   method="L-BFGS-B", bounds=bounds)
    beta = res.x[:3]
    y_fit = _ns_curve(tau, beta, lam)
    residuals = y_obs - y_fit
    fitted_dict = dict(zip(cols_used, y_fit))
    resid_dict = dict(zip(cols_used, residuals))
    return fitted_dict, resid_dict


def compute_residuals(
    yields_df: pd.DataFrame,
    lam: float = 2.0,
) -> pd.DataFrame:
    """
    Fit NS to each date and return residuals by date and maturity.
    
    Args:
        yields_df: DataFrame with date index and yield columns (RU_* or CN_*)
        lam: NS decay parameter
    
    Returns:
        DataFrame of residuals, same shape as yields_df (NaN where no fit).
    """
    residuals = yields_df.copy()
    residuals[:] = np.nan
    yield_cols = [c for c in yields_df.columns if _parse_maturity(c) is not None]
    
    for idx, row in yields_df.iterrows():
        _, resid_dict = fit_nelson_siegel(row[yield_cols], lam=lam)
        for col, val in resid_dict.items():
            residuals.loc[idx, col] = val
    return residuals


def get_fitted_curves(
    yields_df: pd.DataFrame,
    lam: float = 2.0,
) -> pd.DataFrame:
    """
    Fit NS to each date and return fitted yields (same structure as input).
    """
    fitted = yields_df.copy()
    fitted[:] = np.nan
    yield_cols = [c for c in yields_df.columns if _parse_maturity(c) is not None]
    
    for idx, row in yields_df.iterrows():
        fitted_dict, _ = fit_nelson_siegel(row[yield_cols], lam=lam)
        for col, val in fitted_dict.items():
            fitted.loc[idx, col] = val
    return fitted

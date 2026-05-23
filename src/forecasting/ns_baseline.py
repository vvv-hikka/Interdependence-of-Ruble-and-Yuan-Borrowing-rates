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


def fit_nelson_siegel_with_params(
    row: pd.Series, lam: float = 2.0
) -> Tuple[Optional[np.ndarray], dict, dict]:
    """
    Fit Nelson-Siegel and return (beta, fitted_dict, residuals_dict).

    Args:
        row: Series with yield columns (e.g. RU_1Y, CN_5Y)
        lam: Decay parameter

    Returns:
        (beta, fitted_dict, resid_dict) where beta is ndarray([beta0, beta1, beta2])
        or (None, {}, {}) if fewer than 4 valid maturities.
    """
    cols_used, tau_list, y_list = [], [], []
    for col in row.index:
        t = _parse_maturity(col)
        if t is not None and pd.notna(row[col]):
            cols_used.append(col)
            tau_list.append(t)
            y_list.append(float(row[col]))
    if len(tau_list) < 4:
        return None, {}, {}
    tau = np.array(tau_list)
    y_obs = np.array(y_list)
    x0 = np.array([np.nanmean(y_obs), -0.5, 0.0])
    bounds = [(0, 20), (-10, 10), (-10, 10)]
    res = minimize(_ns_objective, x0, args=(tau, y_obs, lam),
                   method="L-BFGS-B", bounds=bounds)
    beta = res.x[:3]
    y_fit = _ns_curve(tau, beta, lam)
    residuals = y_obs - y_fit
    fitted_dict = dict(zip(cols_used, y_fit))
    resid_dict = dict(zip(cols_used, residuals))
    return beta, fitted_dict, resid_dict


def fit_nelson_siegel(row: pd.Series, lam: float = 2.0) -> Tuple[dict, dict]:
    """
    Fit Nelson-Siegel to a row of yields by maturity.

    Returns:
        (fitted_dict, residuals_dict) mapping column -> value for each valid maturity.
    """
    _, fitted_dict, resid_dict = fit_nelson_siegel_with_params(row, lam)
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


def extract_ns_factors(
    yields_df: pd.DataFrame,
    lam: float = 2.0,
) -> pd.DataFrame:
    """
    Fit NS to each date and return the factor time series.

    Args:
        yields_df: DataFrame with date index and yield columns (RU_* or CN_*)
        lam: NS decay parameter

    Returns:
        DataFrame with date index and columns [beta0, beta1, beta2].
        Rows where fewer than 4 maturities are available are dropped.
    """
    yield_cols = [c for c in yields_df.columns if _parse_maturity(c) is not None]
    records = []
    for idx, row in yields_df.iterrows():
        beta, _, _ = fit_nelson_siegel_with_params(row[yield_cols], lam=lam)
        if beta is not None:
            records.append({'date': idx, 'beta0': beta[0], 'beta1': beta[1], 'beta2': beta[2]})
    if not records:
        return pd.DataFrame(columns=['beta0', 'beta1', 'beta2'])
    df = pd.DataFrame(records).set_index('date')
    return df


def reconstruct_yield_curve(
    factors: pd.Series,
    maturities: list,
    lam: float = 2.0,
    prefix: str = "RU_",
) -> pd.Series:
    """
    Reconstruct yields at specified maturities from NS factors.

    Args:
        factors: Series with beta0, beta1, beta2
        maturities: List of maturity floats in years (e.g. [1, 2, 5, 10])
        lam: NS decay parameter
        prefix: Column prefix for output (e.g. 'RU_' or 'CN_')

    Returns:
        Series indexed by maturity column names.
    """
    beta = np.array([factors['beta0'], factors['beta1'], factors['beta2']])
    tau = np.array(maturities)
    y = _ns_curve(tau, beta, lam)
    cols = []
    for t in maturities:
        if t < 1:
            cols.append(f"{prefix}{int(round(t * 12))}M")
        else:
            cols.append(f"{prefix}{int(t)}Y")
    return pd.Series(y, index=cols)

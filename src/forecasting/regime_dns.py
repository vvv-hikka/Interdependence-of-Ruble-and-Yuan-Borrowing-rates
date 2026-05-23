"""
Dynamic Nelson-Siegel (DNS) yield curve model — Diebold & Li (2006).

Approach:
  1. Fix lambda, fit NS to each period → extract factor time series (beta0, beta1, beta2).
  2. Model each factor as AR(1): beta_i,t = mu_i + phi_i * beta_i,t-1 + eps_i,t.
  3. Forecast h periods ahead analytically.
  4. Reconstruct yield curve from forecasted factors.

This module works for a single curve (RU or CN). For cross-currency joint
forecasting use var_factors.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List

from src.forecasting.ns_baseline import (
    extract_ns_factors,
    reconstruct_yield_curve,
    _parse_maturity,
)


@dataclass
class DNSModel:
    """Fitted DNS model for one yield curve."""
    lam: float
    # AR(1) params per factor: shape (3,) each
    mu: np.ndarray          # long-run mean
    phi: np.ndarray         # AR(1) coefficient
    sigma: np.ndarray       # residual std
    # In-sample factor series (date-indexed DataFrame with beta0/beta1/beta2)
    factors: pd.DataFrame = field(repr=False)
    # Original maturity columns seen during fit (for reconstruction)
    maturity_cols: List[str] = field(default_factory=list)
    # Maturities in years corresponding to maturity_cols
    maturities: List[float] = field(default_factory=list)
    prefix: str = "RU_"


@dataclass
class RegimeDNSModel:
    """
    Lightweight macro-threshold regime DNS:
    - low regime DNS model
    - high regime DNS model
    - threshold for switching
    - macro column used for split
    """
    macro_col: str
    threshold: float
    low_model: DNSModel
    high_model: DNSModel
    low_count: int
    high_count: int


def fit_dns(
    yields_df: pd.DataFrame,
    lam: float = 2.0,
) -> Optional[DNSModel]:
    """
    Fit a DNS model to a yield curve time series.

    Args:
        yields_df: DataFrame with date index and yield columns (e.g. RU_1Y, RU_5Y).
                   Must have at least 20 observations with 4+ maturities.
        lam: NS decay parameter (default 2.0, ~30-month hump).

    Returns:
        Fitted DNSModel, or None if insufficient data.
    """
    yield_cols = [c for c in yields_df.columns if _parse_maturity(c) is not None]
    maturities = [_parse_maturity(c) for c in yield_cols]

    # Infer prefix (RU_ or CN_) from columns
    prefix = "RU_"
    for c in yield_cols:
        if c.startswith("CN_"):
            prefix = "CN_"
            break

    factors = extract_ns_factors(yields_df, lam=lam)
    if len(factors) < 20:
        print(f"  [DNS] Too few observations ({len(factors)}) to fit DNS.")
        return None

    mu = np.zeros(3)
    phi = np.zeros(3)
    sigma = np.zeros(3)

    for i, col in enumerate(['beta0', 'beta1', 'beta2']):
        y = factors[col].dropna().values
        if len(y) < 10:
            continue
        # OLS: y_t = mu*(1 - phi) + phi*y_{t-1}
        y_t = y[1:]
        y_lag = y[:-1]
        X = np.column_stack([np.ones_like(y_lag), y_lag])
        try:
            coef, res, _, _ = np.linalg.lstsq(X, y_t, rcond=None)
        except np.linalg.LinAlgError:
            continue
        intercept, phi_i = coef
        # phi saturated at [-0.999, 0.999] for stationarity
        phi_i = float(np.clip(phi_i, -0.999, 0.999))
        mu_i = intercept / (1 - phi_i) if abs(1 - phi_i) > 1e-6 else float(np.mean(y))
        resid = y_t - (intercept + phi_i * y_lag)
        sigma_i = float(np.std(resid, ddof=2)) if len(resid) > 2 else 0.0
        mu[i] = mu_i
        phi[i] = phi_i
        sigma[i] = sigma_i

    return DNSModel(
        lam=lam,
        mu=mu,
        phi=phi,
        sigma=sigma,
        factors=factors,
        maturity_cols=yield_cols,
        maturities=maturities,
        prefix=prefix,
    )


def forecast_dns(
    model: DNSModel,
    horizon: int = 1,
    last_factors: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Forecast yield curves h periods ahead using the fitted DNS model.

    Args:
        model: Fitted DNSModel from fit_dns().
        horizon: Number of periods to forecast.
        last_factors: Override the starting factor values (Series with
                      beta0/beta1/beta2). If None, uses the last in-sample date.

    Returns:
        DataFrame indexed by forecast step (1..horizon) with yield columns
        matching model.maturity_cols.
    """
    if last_factors is None:
        last_factors = model.factors.iloc[-1]

    beta_now = np.array([
        last_factors['beta0'],
        last_factors['beta1'],
        last_factors['beta2'],
    ], dtype=float)

    records = []
    for h in range(1, horizon + 1):
        # h-step ahead forecast: beta_{t+h} = mu + phi^h * (beta_t - mu)
        beta_h = model.mu + (model.phi ** h) * (beta_now - model.mu)
        factor_series = pd.Series(
            {'beta0': beta_h[0], 'beta1': beta_h[1], 'beta2': beta_h[2]}
        )
        curve = reconstruct_yield_curve(
            factor_series,
            maturities=model.maturities,
            lam=model.lam,
            prefix=model.prefix,
        )
        curve['horizon'] = h
        records.append(curve)

    result = pd.DataFrame(records).set_index('horizon')
    return result


def run_regime_dns(yields_df: pd.DataFrame, macro_df=None) -> Optional[DNSModel]:
    """
    Convenience wrapper: fit DNS and print a summary.
    macro_df is accepted for API compatibility but currently unused.
    """
    print("Fitting Dynamic Nelson-Siegel model...")
    model = fit_dns(yields_df)
    if model is None:
        return None

    print(f"  lambda = {model.lam:.3f}")
    factor_names = ['beta0 (level)', 'beta1 (slope)', 'beta2 (curvature)']
    for i, name in enumerate(factor_names):
        print(f"  {name}: mu={model.mu[i]:.4f}, phi={model.phi[i]:.4f}, sigma={model.sigma[i]:.4f}")

    return model


def fit_regime_dns(
    yields_df: pd.DataFrame,
    macro_df: pd.DataFrame,
    macro_col: str,
    lam: float = 2.0,
    min_obs: int = 20,
) -> Optional[RegimeDNSModel]:
    """
    Fit a simple two-regime DNS split by median macro_col level.
    """
    if macro_df is None or macro_df.empty or macro_col not in macro_df.columns:
        print(f"  [RegimeDNS] Missing macro column: {macro_col}")
        return None

    aligned = yields_df.join(macro_df[[macro_col]], how="inner").dropna(subset=[macro_col])
    if len(aligned) < 2 * min_obs:
        print(f"  [RegimeDNS] Insufficient aligned observations: {len(aligned)}")
        return None

    threshold = float(aligned[macro_col].median())
    low = aligned[aligned[macro_col] <= threshold].drop(columns=[macro_col])
    high = aligned[aligned[macro_col] > threshold].drop(columns=[macro_col])
    if len(low) < min_obs or len(high) < min_obs:
        print(f"  [RegimeDNS] Regime split too small: low={len(low)}, high={len(high)}")
        return None

    low_model = fit_dns(low, lam=lam)
    high_model = fit_dns(high, lam=lam)
    if low_model is None or high_model is None:
        print("  [RegimeDNS] DNS fit failed in one regime")
        return None

    return RegimeDNSModel(
        macro_col=macro_col,
        threshold=threshold,
        low_model=low_model,
        high_model=high_model,
        low_count=len(low),
        high_count=len(high),
    )


def forecast_regime_dns(
    model: RegimeDNSModel,
    current_macro_value: float,
    horizon: int = 1,
) -> pd.DataFrame:
    """
    Forecast with regime-specific DNS selected by macro threshold.
    """
    use_high = current_macro_value > model.threshold
    base_model = model.high_model if use_high else model.low_model
    return forecast_dns(base_model, horizon=horizon)

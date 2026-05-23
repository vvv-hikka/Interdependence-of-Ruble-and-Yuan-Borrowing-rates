"""
VAR model on joint Nelson-Siegel factors for RU and CN yield curves.

Approach:
  1. Extract NS factors (beta0, beta1, beta2) for each curve independently.
  2. Stack into a 6-variable vector: [RU_b0, RU_b1, RU_b2, CN_b0, CN_b1, CN_b2].
  3. Fit VAR(p) — lag order selected by AIC up to max_lags.
  4. Forecast h steps ahead; reconstruct both yield curves from forecasted factors.

This model captures cross-currency factor dynamics that two independent DNS
models miss (e.g., CN level factor Granger-causing RU slope).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict

from src.forecasting.ns_baseline import (
    extract_ns_factors,
    reconstruct_yield_curve,
    _parse_maturity,
)

try:
    from statsmodels.tsa.vector_ar.var_model import VAR
    _STATSMODELS = True
except ImportError:
    _STATSMODELS = False
    print("[WARN] statsmodels not available — VARModel will not work.")


@dataclass
class VARFactorModel:
    """Fitted joint VAR model on RU + CN NS factors."""
    lam: float
    lag_order: int
    # Fitted statsmodels VARResults object
    var_result: object = field(repr=False)
    # Factor DataFrames used in fit (aligned, no NaNs)
    ru_factors: pd.DataFrame = field(repr=False)
    cn_factors: pd.DataFrame = field(repr=False)
    # Column metadata for reconstruction
    ru_maturity_cols: List[str] = field(default_factory=list)
    ru_maturities: List[float] = field(default_factory=list)
    cn_maturity_cols: List[str] = field(default_factory=list)
    cn_maturities: List[float] = field(default_factory=list)
    # Names of the 6 VAR variables
    var_names: List[str] = field(default_factory=list)


def _get_maturity_info(yields_df: pd.DataFrame) -> Tuple[List[str], List[float]]:
    cols = [c for c in yields_df.columns if _parse_maturity(c) is not None]
    mats = [_parse_maturity(c) for c in cols]
    return cols, mats


def fit_var(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    lam: float = 2.0,
    max_lags: int = 6,
) -> Optional[VARFactorModel]:
    """
    Fit a joint VAR(p) on the NS factors of both yield curves.

    Args:
        ru_yields: Russian yield curve DataFrame (date index, RU_* columns).
        cn_yields: Chinese yield curve DataFrame (date index, CN_* columns).
        lam: Common NS decay parameter.
        max_lags: Maximum lag order for AIC-based selection.

    Returns:
        Fitted VARFactorModel, or None if data is insufficient.
    """
    if not _STATSMODELS:
        print("  [VAR] statsmodels not available.")
        return None

    ru_cols, ru_mats = _get_maturity_info(ru_yields)
    cn_cols, cn_mats = _get_maturity_info(cn_yields)

    ru_f = extract_ns_factors(ru_yields, lam=lam)
    cn_f = extract_ns_factors(cn_yields, lam=lam)

    if ru_f.empty or cn_f.empty:
        print("  [VAR] Factor extraction failed for one or both curves.")
        return None

    ru_f = ru_f.rename(columns={c: f'RU_{c}' for c in ru_f.columns})
    cn_f = cn_f.rename(columns={c: f'CN_{c}' for c in cn_f.columns})

    # Align on common dates
    joint = ru_f.join(cn_f, how='inner').dropna()
    if len(joint) < max_lags + 20:
        print(f"  [VAR] Insufficient aligned observations ({len(joint)}).")
        return None

    var_names = list(joint.columns)
    print(f"  [VAR] Fitting VAR on {len(joint)} observations, max_lags={max_lags}...")

    model = VAR(joint)
    try:
        lag_order = model.select_order(maxlags=max_lags).aic
        lag_order = max(1, lag_order)
    except Exception:
        lag_order = 1

    result = model.fit(lag_order)
    print(f"  [VAR] Selected lag order p={lag_order}, AIC={result.aic:.2f}")

    # Restore original factor column names for reconstruction
    ru_f_orig = ru_f.rename(columns={f'RU_{c}': c for c in ['beta0', 'beta1', 'beta2']})
    cn_f_orig = cn_f.rename(columns={f'CN_{c}': c for c in ['beta0', 'beta1', 'beta2']})

    return VARFactorModel(
        lam=lam,
        lag_order=lag_order,
        var_result=result,
        ru_factors=ru_f_orig,
        cn_factors=cn_f_orig,
        ru_maturity_cols=ru_cols,
        ru_maturities=ru_mats,
        cn_maturity_cols=cn_cols,
        cn_maturities=cn_mats,
        var_names=var_names,
    )


def forecast_var(
    model: VARFactorModel,
    horizon: int = 1,
) -> Dict[str, pd.DataFrame]:
    """
    Forecast both yield curves h periods ahead.

    Args:
        model: Fitted VARFactorModel from fit_var().
        horizon: Number of periods to forecast.

    Returns:
        Dict with keys 'ru' and 'cn', each a DataFrame indexed by horizon step
        (1..horizon) with the respective yield columns.
    """
    # statsmodels VAR forecast requires last p observations
    result = model.var_result
    last_obs = result.fittedvalues.iloc[-result.k_ar:]
    forecasts = result.forecast(last_obs.values, steps=horizon)
    forecast_df = pd.DataFrame(forecasts, columns=model.var_names)

    ru_records, cn_records = [], []
    for h in range(horizon):
        row = forecast_df.iloc[h]
        ru_f = pd.Series({
            'beta0': row['RU_beta0'],
            'beta1': row['RU_beta1'],
            'beta2': row['RU_beta2'],
        })
        cn_f = pd.Series({
            'beta0': row['CN_beta0'],
            'beta1': row['CN_beta1'],
            'beta2': row['CN_beta2'],
        })
        ru_curve = reconstruct_yield_curve(ru_f, model.ru_maturities, model.lam, prefix='RU_')
        cn_curve = reconstruct_yield_curve(cn_f, model.cn_maturities, model.lam, prefix='CN_')
        ru_curve['horizon'] = h + 1
        cn_curve['horizon'] = h + 1
        ru_records.append(ru_curve)
        cn_records.append(cn_curve)

    return {
        'ru': pd.DataFrame(ru_records).set_index('horizon'),
        'cn': pd.DataFrame(cn_records).set_index('horizon'),
    }

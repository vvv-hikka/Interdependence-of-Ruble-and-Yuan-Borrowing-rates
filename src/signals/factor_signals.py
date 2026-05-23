"""
Factor divergence signals based on VAR model residuals.

Approach:
  1. Fit VAR(p) on joint NS factors [RU_b0, RU_b1, RU_b2, CN_b0, CN_b1, CN_b2].
  2. Extract in-sample residuals.
  3. For each factor, flag when the normalised residual > threshold (σ-scaled).
  4. Aggregate into actionable direction signals per curve:
       - RU signal = sign of weighted combination of RU factor residuals
         (level residual > threshold → long/short RU duration)
       - CN signal = similarly for CN factors
  5. Conflict check: if RU and CN signals agree in direction, signal is neutral
     (both curves moving together, not diverging).

Signal convention (per curve):
  +1 → go long this curve (level factor pushed unusually low → mean-reversion up)
  -1 → go short this curve
   0 → no signal

Output:
  FactorSignalResult.residuals    — DataFrame of raw residuals per factor
  FactorSignalResult.z_scores     — standardised residuals (rolling z)
  FactorSignalResult.signals      — DataFrame[date, signal_RU, signal_CN, divergence]
  FactorSignalResult.latest       — most-recent signal row
  FactorSignalResult.model        — the fitted VARFactorModel
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.forecasting.var_factors import VARFactorModel, fit_var


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class FactorSignalResult:
    residuals: pd.DataFrame = field(default_factory=pd.DataFrame)
    z_scores: pd.DataFrame = field(default_factory=pd.DataFrame)
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)
    latest: pd.Series = field(default_factory=pd.Series)
    model: Optional[VARFactorModel] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    m = series.rolling(window, min_periods=max(4, window // 4)).mean()
    s = series.rolling(window, min_periods=max(4, window // 4)).std()
    return ((series - m) / s.replace(0, np.nan)).round(4)


def _factor_direction(
    z_beta0: pd.Series,
    z_beta1: pd.Series,
    z_beta2: pd.Series,
    threshold: float,
) -> pd.Series:
    """
    Combine three NS factor z-scores into a single direction signal.

    Level (beta0) is the dominant factor for duration positioning:
      - Large positive residual in beta0 → level unusually high → mean-revert down → SHORT
      - Large negative residual in beta0 → level unusually low  → mean-revert up   → LONG

    Slope (beta1) refines: if beta1 residual confirms, amplify; if conflicts, dampen.

    Returns Series of {-1, 0, +1}.
    """
    sig = pd.Series(0, index=z_beta0.index, dtype=int)
    # Primary: level factor
    sig[z_beta0 >  threshold] = -1   # level too high → short
    sig[z_beta0 < -threshold] =  1   # level too low  → long
    # Zero out if slope contradicts strongly (cross-signal noise filter)
    contradicts = (sig == 1) & (z_beta1 > threshold) | (sig == -1) & (z_beta1 < -threshold)
    sig[contradicts] = 0
    return sig


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def compute_factor_signals(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    lam: float = 2.0,
    max_lags: int = 6,
    z_window: int = 24,
    threshold: float = 1.5,
) -> FactorSignalResult:
    """
    Fit VAR on NS factors, compute residual-based divergence signals.

    Args:
        ru_yields:  Date-indexed DataFrame with RU_* yield columns.
        cn_yields:  Date-indexed DataFrame with CN_* yield columns.
        lam:        NS decay parameter.
        max_lags:   Maximum lag order for VAR AIC selection.
        z_window:   Rolling window for z-score normalisation of residuals.
        threshold:  |z| threshold for signal entry.

    Returns:
        FactorSignalResult.
    """
    # Deduplicate before passing to VAR
    ru_yields = ru_yields[~ru_yields.index.duplicated(keep='last')]
    cn_yields = cn_yields[~cn_yields.index.duplicated(keep='last')]
    model = fit_var(ru_yields, cn_yields, lam=lam, max_lags=max_lags)
    if model is None:
        return FactorSignalResult()

    result = model.var_result
    resid = pd.DataFrame(
        result.resid,
        index=result.resid.index if hasattr(result.resid, 'index') else result.fittedvalues.index,
        columns=model.var_names,
    )

    # Normalise residuals
    z = pd.DataFrame(
        {col: _rolling_zscore(resid[col], z_window) for col in resid.columns},
        index=resid.index,
    )

    # Per-curve direction signals
    sig_ru = _factor_direction(
        z["RU_beta0"], z["RU_beta1"], z["RU_beta2"], threshold
    )
    sig_cn = _factor_direction(
        z["CN_beta0"], z["CN_beta1"], z["CN_beta2"], threshold
    )

    # Divergence flag: RU and CN moving in *opposite* directions
    divergence = (sig_ru != 0) & (sig_cn != 0) & (sig_ru != sig_cn)

    signals = pd.DataFrame({
        "signal_RU":  sig_ru,
        "signal_CN":  sig_cn,
        "divergence": divergence.astype(int),
    }, index=resid.index)

    # Add dominant factor z-scores for inspection
    for col in model.var_names:
        signals[f"z_{col}"] = z[col]

    latest = signals.iloc[-1] if not signals.empty else pd.Series(dtype=float)

    return FactorSignalResult(
        residuals=resid,
        z_scores=z,
        signals=signals,
        latest=latest,
        model=model,
    )

"""
Covered Interest Parity (CIP) deviation signal.

Theory:
  Under CIP, the yield differential between two countries should equal the
  cost of hedging the FX exposure (forward premium/discount).  Since we lack
  liquid CNY/RUB FX forward data, we approximate the forward premium with the
  *realised* annualised change in the spot CNY/RUB rate over the same horizon.

  CIP_deviation(t, mat) = r_RU(t, mat) - r_CN(t, mat) - F(t)

  where F(t) = annualised log return of CNY/RUB over the rolling `fx_window`
               (positive F means RUB is depreciating against CNY, which should
                push RU yields higher under UIP/CIP).

Signal:
  +1  → CIP deviation > +entry_z standard deviations
        (RU yields too high given FX cost → long RU / short CN)
  -1  → CIP deviation < -entry_z standard deviations
        (RU yields too low → short RU / long CN)
   0  → no position

Output columns per maturity:
  cip_{mat}         — raw CIP deviation (annualised pp)
  cip_z_{mat}       — rolling z-score
  cip_signal_{mat}  — {-1, 0, +1}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from .spread_signals import _match_maturities


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class CIPResult:
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)
    latest: pd.Series = field(default_factory=pd.Series)
    fx_premium: pd.Series = field(default_factory=pd.Series)   # annualised FX change
    maturities: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# FX premium helper
# ---------------------------------------------------------------------------

def _annualised_fx_change(cny_rub: pd.Series, fx_window: int = 12) -> pd.Series:
    """
    Compute rolling annualised log return of CNY/RUB.

    A positive value means 1 CNY buys more RUB (RUB depreciated), so a Russian
    investor hedging CNY back to RUB must sell RUB forward at a discount —
    raising the effective cost of holding CN bonds.

    Args:
        cny_rub:   Monthly series of CNY/RUB spot rate.
        fx_window: Look-back window in months for the rolling estimate.

    Returns:
        Annualised percentage change series (e.g. 5.0 = 5 % p.a.).
    """
    log_ret = np.log(cny_rub).diff()
    # Rolling mean of monthly log return → annualise × 12 → convert to %
    rolling_ann = log_ret.rolling(fx_window, min_periods=max(3, fx_window // 4)).mean() * 12 * 100
    return rolling_ann


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def compute_cip_deviation(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    currency_rates: pd.DataFrame,
    fx_window: int = 12,
    z_window: int = 24,
    entry_z: float = 1.5,
) -> CIPResult:
    """
    Compute CIP deviation and entry signals for all matched maturities.

    Args:
        ru_yields:       Date-indexed DataFrame with RU_* yield columns (in %).
        cn_yields:       Date-indexed DataFrame with CN_* yield columns (in %).
        currency_rates:  Date-indexed DataFrame containing 'cny_rub' column.
        fx_window:       Rolling window (months) for annualised FX return estimate.
        z_window:        Rolling window for z-score normalisation of CIP deviation.
        entry_z:         |z| threshold to enter a position.

    Returns:
        CIPResult with .signals DataFrame and .latest Series.
    """
    if "cny_rub" not in currency_rates.columns:
        return CIPResult()

    ru_cols = [c for c in ru_yields.columns if c.startswith("RU_")]
    cn_cols = [c for c in cn_yields.columns if c.startswith("CN_")]
    pairs = _match_maturities(ru_cols, cn_cols)
    if not pairs:
        return CIPResult()

    # Ensure date index
    cny_rub = currency_rates["cny_rub"].copy()
    if not isinstance(cny_rub.index, pd.DatetimeIndex):
        cny_rub.index = pd.to_datetime(cny_rub.index)

    fx_premium = _annualised_fx_change(cny_rub, fx_window)

    # Deduplicate then align on common dates
    ru_d = ru_yields[~ru_yields.index.duplicated(keep='last')]
    cn_d = cn_yields[~cn_yields.index.duplicated(keep='last')]

    joint_idx = ru_d.index.intersection(cn_d.index).intersection(fx_premium.dropna().index)
    if joint_idx.empty:
        return CIPResult()

    ru = ru_d.loc[joint_idx]
    cn = cn_d.loc[joint_idx]
    fp = fx_premium.loc[joint_idx]

    records = {}
    maturities = []
    for ru_col, cn_col, label in pairs:
        ru_series = ru[ru_col].astype(float)
        cn_series = cn[cn_col].astype(float)

        # CIP deviation = (RU yield - CN yield) - annualised FX cost
        # All in annualised percentage points
        cip_dev = (ru_series - cn_series) - fp

        roll_mean = cip_dev.rolling(z_window, min_periods=max(4, z_window // 4)).mean()
        roll_std  = cip_dev.rolling(z_window, min_periods=max(4, z_window // 4)).std()
        z = (cip_dev - roll_mean) / roll_std.replace(0, np.nan)

        sig = pd.Series(0, index=z.index, dtype=int)
        sig[z >  entry_z] =  1
        sig[z < -entry_z] = -1

        records[f"cip_{label}"]        = cip_dev.round(4)
        records[f"cip_z_{label}"]      = z.round(4)
        records[f"cip_signal_{label}"] = sig
        maturities.append(label)

    df = pd.DataFrame(records, index=joint_idx)
    latest = df.iloc[-1] if not df.empty else pd.Series(dtype=float)

    return CIPResult(
        signals=df,
        latest=latest,
        fx_premium=fp,
        maturities=maturities,
    )

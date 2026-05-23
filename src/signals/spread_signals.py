"""
Spread signals: rolling z-score on maturity-matched RU–CN yield spread.

For each maturity where both RU_*Y and CN_*Y are available:
  spread(t) = RU_yield(t) - CN_yield(t)
  z(t)      = (spread(t) - rolling_mean) / rolling_std

Signal:
  +1  → long RU / short CN  (spread unusually wide relative to history)
  -1  → short RU / long CN  (spread unusually narrow / negative)
   0  → no position

Entry thresholds: |z| > entry_z  (default 1.5)
Exit  thresholds: |z| < exit_z   (default 0.5)

Output:
  SpreadSignalResult.signals     — DataFrame[date, signal_{mat}, z_{mat}, spread_{mat}]
  SpreadSignalResult.latest      — most-recent row as a Series
  SpreadSignalResult.maturities  — list of matched maturity strings (e.g. ['1Y','2Y',...])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MATURITY_RE = re.compile(r"(\d+(?:\.\d+)?)(Y|M)", re.IGNORECASE)


def _parse_years(col: str) -> Optional[float]:
    """Return maturity in years from e.g. 'RU_1Y', 'CN_10Y', 'RU_3M'."""
    m = _MATURITY_RE.search(col)
    if m is None:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    return val if unit == "Y" else val / 12.0


def _match_maturities(ru_cols: List[str], cn_cols: List[str], tol_years: float = 0.1) -> List[tuple]:
    """
    Return list of (ru_col, cn_col, label) for maturities that exist in both curves
    within tol_years.
    """
    pairs = []
    for rc in ru_cols:
        ry = _parse_years(rc)
        if ry is None:
            continue
        best, best_dist = None, tol_years + 1
        for cc in cn_cols:
            cy = _parse_years(cc)
            if cy is None:
                continue
            d = abs(ry - cy)
            if d < best_dist:
                best_dist = d
                best = cc
        if best is not None and best_dist <= tol_years:
            # Label by RU maturity string
            m = _MATURITY_RE.search(rc)
            label = f"{m.group(1)}{m.group(2).upper()}" if m else rc
            pairs.append((rc, best, label))
    return pairs


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SpreadSignalResult:
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)
    latest: pd.Series = field(default_factory=pd.Series)
    maturities: List[str] = field(default_factory=list)
    pairs: List[tuple] = field(default_factory=list)  # (ru_col, cn_col, label)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def compute_spread_signals(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    window: int = 24,
    entry_z: float = 1.5,
    exit_z: float = 0.5,
) -> SpreadSignalResult:
    """
    Compute rolling z-score spread signals for all matched maturities.

    Args:
        ru_yields:  DataFrame, date-indexed, RU_* columns (% or decimal, consistent).
        cn_yields:  DataFrame, date-indexed, CN_* columns.
        window:     Rolling window for mean/std (in observations, default 24 months).
        entry_z:    |z| threshold to enter a position (default 1.5).
        exit_z:     |z| threshold to exit a position (default 0.5).

    Returns:
        SpreadSignalResult with .signals DataFrame and .latest Series.
    """
    ru_cols = [c for c in ru_yields.columns if c.startswith("RU_")]
    cn_cols = [c for c in cn_yields.columns if c.startswith("CN_")]

    pairs = _match_maturities(ru_cols, cn_cols)
    if not pairs:
        return SpreadSignalResult()

    # Deduplicate (keep last observation per date) before aligning
    ru_dedup = ru_yields[~ru_yields.index.duplicated(keep='last')]
    cn_dedup = cn_yields[~cn_yields.index.duplicated(keep='last')]

    joint_idx = ru_dedup.index.intersection(cn_dedup.index)
    if joint_idx.empty:
        return SpreadSignalResult()

    ru = ru_dedup.loc[joint_idx]
    cn = cn_dedup.loc[joint_idx]

    records = {}
    for ru_col, cn_col, label in pairs:
        spread = ru[ru_col].astype(float) - cn[cn_col].astype(float)
        roll_mean = spread.rolling(window, min_periods=max(4, window // 4)).mean()
        roll_std  = spread.rolling(window, min_periods=max(4, window // 4)).std()
        z = (spread - roll_mean) / roll_std.replace(0, np.nan)

        # Signal with hysteresis (stateless version — just threshold on z)
        sig = pd.Series(0, index=z.index, dtype=int)
        sig[z >  entry_z] =  1   # spread wide → long RU / short CN
        sig[z < -entry_z] = -1   # spread narrow → short RU / long CN

        records[f"spread_{label}"] = spread
        records[f"z_{label}"]      = z.round(4)
        records[f"signal_{label}"] = sig

    df = pd.DataFrame(records, index=joint_idx)
    latest = df.iloc[-1] if not df.empty else pd.Series(dtype=float)

    return SpreadSignalResult(
        signals=df,
        latest=latest,
        maturities=[p[2] for p in pairs],
        pairs=pairs,
    )

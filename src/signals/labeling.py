"""
Labeling helpers for robust OOS signal training.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TripleBarrierConfig:
    take_profit: float = 0.004
    stop_loss: float = 0.004
    max_holding: int = 3


def triple_barrier_labels(
    spread_returns: pd.Series,
    cfg: TripleBarrierConfig | None = None,
) -> pd.DataFrame:
    """
    Build triple-barrier labels from monthly spread returns.

    Returns columns:
      - tb_label: {-1, 0, +1}
      - tb_event_horizon: integer months to first barrier or timeout
      - is_opportunity: 1 when |tb_label| > 0 else 0
      - direction_conditional: {-1, +1} where opportunity, NaN otherwise
    """
    if cfg is None:
        cfg = TripleBarrierConfig()
    s = spread_returns.astype(float).copy()
    out = pd.DataFrame(index=s.index)
    labels: list[int] = []
    horizons: list[int] = []
    vals = s.values
    n = len(vals)

    for i in range(n):
        pnl = 0.0
        label = 0
        steps = 0
        for j in range(1, cfg.max_holding + 1):
            if i + j >= n:
                break
            pnl += float(vals[i + j])
            steps = j
            if pnl >= cfg.take_profit:
                label = 1
                break
            if pnl <= -cfg.stop_loss:
                label = -1
                break
        if steps == 0:
            steps = cfg.max_holding
        labels.append(label)
        horizons.append(int(steps))

    out["tb_label"] = labels
    out["tb_event_horizon"] = horizons
    out["is_opportunity"] = (out["tb_label"] != 0).astype(int)
    out["direction_conditional"] = out["tb_label"].replace({0: np.nan})
    return out


def make_meta_direction_targets(label_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build binary opportunity and conditional-direction targets.
    """
    out = pd.DataFrame(index=label_df.index)
    out["target_opportunity"] = label_df["is_opportunity"].astype(float)
    out["target_direction"] = np.where(label_df["direction_conditional"] > 0, 1.0, 0.0)
    out.loc[label_df["is_opportunity"] == 0, "target_direction"] = np.nan
    return out


def purged_embargo_splits(
    n_samples: int,
    n_splits: int = 5,
    embargo: int = 1,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Time-series CV splits with purge + embargo around each test block.
    """
    if n_samples <= 0:
        return []
    n_splits = max(2, min(n_splits, n_samples))
    fold_sizes = np.full(n_splits, n_samples // n_splits, dtype=int)
    fold_sizes[: n_samples % n_splits] += 1

    splits: list[tuple[np.ndarray, np.ndarray]] = []
    current = 0
    all_idx = np.arange(n_samples)
    for fold_size in fold_sizes:
        start = current
        stop = current + fold_size
        test_idx = all_idx[start:stop]
        if len(test_idx) == 0:
            current = stop
            continue

        purge_lo = max(0, start - embargo)
        purge_hi = min(n_samples, stop + embargo)
        keep_mask = np.ones(n_samples, dtype=bool)
        keep_mask[purge_lo:purge_hi] = False
        train_idx = all_idx[keep_mask]
        if len(train_idx) > 0:
            splits.append((train_idx, test_idx))
        current = stop
    return splits

"""
PCA decomposition of the joint RU+CN yield matrix.

Usage:
  1. fit_pca(ru_yields, cn_yields) → PCAModel
  2. reconstruct(model, scores) → approximate yields
  3. forecast_pca(model, horizon) → h-step random-walk forecast in PC space

The first 3 PCs typically explain >95% of yield curve variation.
PCA components are also useful as risk factors in regression and portfolio work.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict

try:
    from sklearn.decomposition import PCA
    _SKLEARN = True
except ImportError:
    _SKLEARN = False
    print("[WARN] scikit-learn not available — PCAModel will not work.")


@dataclass
class PCAModel:
    """Fitted PCA model on the joint yield matrix."""
    n_components: int
    pca: object = field(repr=False)
    all_cols: List[str] = field(default_factory=list)
    ru_cols: List[str] = field(default_factory=list)
    cn_cols: List[str] = field(default_factory=list)
    scores: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    explained_variance_ratio: np.ndarray = field(default_factory=lambda: np.array([]))
    col_means: pd.Series = field(repr=False, default_factory=pd.Series)


def fit_pca(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    n_components: int = 6,
) -> Optional[PCAModel]:
    """
    Fit PCA on the joint RU+CN yield matrix.

    Args:
        ru_yields: DataFrame with date index and RU_* columns.
        cn_yields: DataFrame with date index and CN_* columns.
        n_components: Number of PCs to retain.

    Returns:
        Fitted PCAModel, or None if data is insufficient.
    """
    if not _SKLEARN:
        print("  [PCA] scikit-learn not available.")
        return None

    ru = ru_yields.copy()
    cn = cn_yields.copy()
    joint = ru.join(cn, how='inner', lsuffix='', rsuffix='_cn').dropna()

    if len(joint) < n_components + 5:
        print(f"  [PCA] Insufficient aligned observations ({len(joint)}).")
        return None

    joint = joint.dropna(axis=1, how='all')
    all_cols = list(joint.columns)
    ru_cols = [c for c in all_cols if c.startswith('RU_')]
    cn_cols = [c for c in all_cols if c.startswith('CN_')]

    col_means = joint.mean()
    X = (joint - col_means).values

    n_comp = min(n_components, X.shape[1], X.shape[0])
    pca = PCA(n_components=n_comp)
    scores_arr = pca.fit_transform(X)
    score_cols = [f'PC{i+1}' for i in range(n_comp)]
    scores = pd.DataFrame(scores_arr, index=joint.index, columns=score_cols)

    print(f"  [PCA] {n_comp} components explain "
          f"{pca.explained_variance_ratio_.sum()*100:.1f}% of variance")
    for i, ev in enumerate(pca.explained_variance_ratio_):
        print(f"    PC{i+1}: {ev*100:.1f}%")

    return PCAModel(
        n_components=n_comp,
        pca=pca,
        all_cols=all_cols,
        ru_cols=ru_cols,
        cn_cols=cn_cols,
        scores=scores,
        explained_variance_ratio=pca.explained_variance_ratio_,
        col_means=col_means,
    )


def reconstruct_from_scores(model: PCAModel, scores: np.ndarray) -> pd.DataFrame:
    """
    Reconstruct yield matrix from PC scores.

    Args:
        model: Fitted PCAModel.
        scores: Array of shape (n_obs, n_components).

    Returns:
        DataFrame with same columns as model.all_cols.
    """
    X_approx = model.pca.inverse_transform(scores) + model.col_means.values
    return pd.DataFrame(X_approx, columns=model.all_cols)


def forecast_pca(
    model: PCAModel,
    horizon: int = 1,
) -> Dict[str, pd.DataFrame]:
    """
    Naive forecast in PC space: random walk on each PC score.

    Args:
        model: Fitted PCAModel.
        horizon: Forecast horizon.

    Returns:
        Dict with 'ru' and 'cn' DataFrames, each indexed by horizon (1..horizon).
    """
    last_scores = model.scores.iloc[-1].values

    records = []
    for h in range(1, horizon + 1):
        approx = reconstruct_from_scores(model, last_scores.reshape(1, -1))
        approx['horizon'] = h
        records.append(approx)

    full = pd.concat(records, ignore_index=True).set_index('horizon')
    ru = full[model.ru_cols] if model.ru_cols else pd.DataFrame()
    cn = full[model.cn_cols] if model.cn_cols else pd.DataFrame()
    return {'ru': ru, 'cn': cn}



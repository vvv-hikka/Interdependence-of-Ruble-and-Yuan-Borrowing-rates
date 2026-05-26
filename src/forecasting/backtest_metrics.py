"""
Shared backtest and performance metrics utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class StrategyStats:
    strategy: str
    ann_return: float
    ann_vol: float
    ann_sharpe: float
    ann_sortino: float
    calmar: float
    cagr: float
    total_return: float
    max_drawdown: float
    var95_empirical: float
    var95_parametric: float
    mean_return: float
    hit_ratio: float
    active_pct: float
    ann_turnover: float
    avg_turnover: float
    total_cost_drag: float


def compute_proxy_returns(ru: pd.DataFrame, cn: pd.DataFrame) -> pd.DataFrame:
    """
    Compute monthly duration-proxy returns for RU and CN legs and spread return.
    """
    ru_col = "RU_10Y" if "RU_10Y" in ru.columns else ru.columns[0]
    cn_col = "CN_10Y" if "CN_10Y" in cn.columns else cn.columns[0]
    common = ru.index.intersection(cn.index)
    out = pd.DataFrame(index=common)
    out["RUB"] = -ru.loc[common, ru_col].diff().fillna(0.0) / 100.0
    out["CNY"] = -cn.loc[common, cn_col].diff().fillna(0.0) / 100.0
    out["spread_ret"] = out["RUB"] - out["CNY"]
    return out.sort_index()


def align_signal_to_next_return(signal: pd.Series, returns_index: pd.Index) -> pd.Series:
    """
    Align to forecast convention: signal[t-1] is applied to return[t].
    """
    sig = signal.copy()
    sig.index = pd.to_datetime(sig.index)
    sig = sig.sort_index().astype(float)
    sig = sig.shift(1).reindex(returns_index).fillna(0.0)
    return sig


def compute_turnover(signal: pd.Series) -> pd.Series:
    """
    Per-period turnover proxy for a signed position in [-1, 1].
    """
    s = signal.astype(float).fillna(0.0)
    return s.diff().abs().fillna(abs(s.iloc[0]) if len(s) else 0.0)


def apply_transaction_costs(
    gross_returns: pd.Series,
    turnover: pd.Series,
    cost_bps: float = 5.0,
) -> tuple[pd.Series, pd.Series]:
    """
    Net return = gross return - turnover * (cost_bps / 10000).
    """
    costs = turnover.fillna(0.0) * (cost_bps / 10000.0)
    net = gross_returns.fillna(0.0) - costs
    return net, costs


def summarize_series(
    strategy_name: str,
    net_returns: pd.Series,
    active_signal: pd.Series,
    turnover: pd.Series,
    costs: pd.Series,
    periods_per_year: int = 12,
) -> StrategyStats:
    s = net_returns.dropna()
    if s.empty:
        nan = float("nan")
        return StrategyStats(
            strategy=strategy_name,
            ann_return=nan,
            ann_vol=nan,
            ann_sharpe=nan,
            ann_sortino=nan,
            calmar=nan,
            cagr=nan,
            total_return=nan,
            max_drawdown=nan,
            var95_empirical=nan,
            var95_parametric=nan,
            mean_return=nan,
            hit_ratio=nan,
            active_pct=nan,
            ann_turnover=nan,
            avg_turnover=nan,
            total_cost_drag=nan,
        )

    mean = float(s.mean())
    std = float(s.std())
    downside = s[s < 0]
    downside_std = float(downside.std()) if len(downside) > 1 else np.nan

    ann_return = float(mean * periods_per_year)
    ann_vol = float(std * np.sqrt(periods_per_year))
    ann_sharpe = float(ann_return / (ann_vol + 1e-12))
    ann_sortino = float(ann_return / ((downside_std * np.sqrt(periods_per_year)) + 1e-12))

    equity = (1.0 + s).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    years = max(len(s) / periods_per_year, 1.0 / periods_per_year)
    cagr = float((equity.iloc[-1] ** (1.0 / years)) - 1.0)
    max_dd = float((equity / equity.cummax() - 1.0).min())
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else np.nan

    var95_emp = float(np.quantile(-s, 0.95))
    var95_param = float(1.645 * std)
    hit_ratio = float((s > 0).mean())
    active_pct = float((active_signal != 0).mean())
    avg_turnover = float(turnover.mean()) if len(turnover) else 0.0
    ann_turnover = float(avg_turnover * periods_per_year)
    total_cost_drag = float(costs.sum())

    return StrategyStats(
        strategy=strategy_name,
        ann_return=round(ann_return, 6),
        ann_vol=round(ann_vol, 6),
        ann_sharpe=round(ann_sharpe, 4),
        ann_sortino=round(ann_sortino, 4),
        calmar=round(calmar, 4) if pd.notna(calmar) else np.nan,
        cagr=round(cagr, 6),
        total_return=round(total_return, 6),
        max_drawdown=round(max_dd, 4),
        var95_empirical=round(var95_emp, 4),
        var95_parametric=round(var95_param, 4),
        mean_return=round(mean, 6),
        hit_ratio=round(hit_ratio, 4),
        active_pct=round(active_pct, 4),
        ann_turnover=round(ann_turnover, 4),
        avg_turnover=round(avg_turnover, 6),
        total_cost_drag=round(total_cost_drag, 6),
    )


def to_stats_row(stats: StrategyStats) -> Dict:
    return stats.__dict__.copy()


def bootstrap_mean_diff_ci(
    a: pd.Series,
    b: pd.Series,
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Bootstrap CI for mean(a-b).
    """
    diff = (a - b).dropna().values
    if len(diff) < 5:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = []
    n = len(diff)
    for _ in range(n_boot):
        sample = diff[rng.integers(0, n, n)]
        means.append(np.mean(sample))
    alpha = (1.0 - ci) / 2.0
    lo = float(np.quantile(means, alpha))
    hi = float(np.quantile(means, 1.0 - alpha))
    return float(np.mean(diff)), lo, hi


def bootstrap_sharpe_diff_ci(
    a: pd.Series,
    b: pd.Series,
    n_boot: int = 1000,
    ci: float = 0.95,
    periods_per_year: int = 12,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Bootstrap CI for Sharpe(a)-Sharpe(b).
    """
    pair = pd.concat([a, b], axis=1).dropna()
    if len(pair) < 12:
        return np.nan, np.nan, np.nan
    vals = pair.values
    n = len(vals)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        s1 = vals[idx, 0]
        s2 = vals[idx, 1]
        sh1 = (np.mean(s1) / (np.std(s1, ddof=1) + 1e-12)) * np.sqrt(periods_per_year)
        sh2 = (np.mean(s2) / (np.std(s2, ddof=1) + 1e-12)) * np.sqrt(periods_per_year)
        diffs.append(sh1 - sh2)
    alpha = (1.0 - ci) / 2.0
    lo = float(np.quantile(diffs, alpha))
    hi = float(np.quantile(diffs, 1.0 - alpha))
    base_sh1 = (pair.iloc[:, 0].mean() / (pair.iloc[:, 0].std() + 1e-12)) * np.sqrt(periods_per_year)
    base_sh2 = (pair.iloc[:, 1].mean() / (pair.iloc[:, 1].std() + 1e-12)) * np.sqrt(periods_per_year)
    return float(base_sh1 - base_sh2), lo, hi


def paired_ttest(a: pd.Series, b: pd.Series) -> tuple[float, float]:
    """
    Paired t-test for mean(a-b) = 0.
    """
    pair = pd.concat([a, b], axis=1).dropna()
    if len(pair) < 5:
        return np.nan, np.nan
    t_stat, p_val = stats.ttest_rel(pair.iloc[:, 0], pair.iloc[:, 1], nan_policy="omit")
    return float(t_stat), float(p_val)

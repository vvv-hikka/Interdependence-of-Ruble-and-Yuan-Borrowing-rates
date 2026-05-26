"""
Yield curve forecasting package.
"""

from src.forecasting.loaders import (
    load_russian_yield_curve,
    load_chinese_yield_curve,
    load_macro_indicators,
    load_russian_yield_curve_weekly,
    load_chinese_yield_curve_weekly,
    load_currency_rates_weekly,
    load_combined_weekly,
)
from src.forecasting.ns_baseline import fit_nelson_siegel, compute_residuals, get_fitted_curves
from src.forecasting.cross_currency import build_spreads, flag_abnormal_spreads
from src.forecasting.evaluate import evaluate_ns_fit, evaluate_spreads
from src.forecasting.portfolio import (
    signal_to_weights,
)
from src.forecasting.backtest_metrics import (
    compute_proxy_returns,
    align_signal_to_next_return,
    compute_turnover,
    apply_transaction_costs,
    summarize_series,
    to_stats_row,
    bootstrap_mean_diff_ci,
    bootstrap_sharpe_diff_ci,
    paired_ttest,
)
from src.forecasting.regime_labels import (
    build_regime_frame,
    regime_counts_table,
)

__all__ = [
    "load_russian_yield_curve",
    "load_chinese_yield_curve",
    "load_macro_indicators",
    "load_russian_yield_curve_weekly",
    "load_chinese_yield_curve_weekly",
    "load_currency_rates_weekly",
    "load_combined_weekly",
    "fit_nelson_siegel",
    "compute_residuals",
    "build_spreads",
    "flag_abnormal_spreads",
    "evaluate_ns_fit",
    "evaluate_spreads",
    "signal_to_weights",
    "compute_proxy_returns",
    "align_signal_to_next_return",
    "compute_turnover",
    "apply_transaction_costs",
    "summarize_series",
    "to_stats_row",
    "bootstrap_mean_diff_ci",
    "bootstrap_sharpe_diff_ci",
    "paired_ttest",
    "build_regime_frame",
    "regime_counts_table",
]

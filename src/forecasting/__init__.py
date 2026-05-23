"""
Yield curve forecasting package.
"""

from src.forecasting.loaders import (
    load_russian_yield_curve,
    load_chinese_yield_curve,
    load_global_indicators,
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
    compute_signal_score,
    signal_to_weights,
    portfolio_var_95,
    apply_var_limit,
)

__all__ = [
    "load_russian_yield_curve",
    "load_chinese_yield_curve",
    "load_global_indicators",
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
    "compute_signal_score",
    "signal_to_weights",
    "portfolio_var_95",
    "apply_var_limit",
]

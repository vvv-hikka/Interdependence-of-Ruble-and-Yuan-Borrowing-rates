"""
Yield curve forecasting package.
"""

from src.forecasting.loaders import (
    load_russian_yield_curve,
    load_chinese_yield_curve,
    load_global_indicators,
    load_macro_indicators,
)
from src.forecasting.ns_baseline import fit_nelson_siegel, compute_residuals, get_fitted_curves
from src.forecasting.cross_currency import build_spreads, flag_abnormal_spreads
from src.forecasting.evaluate import evaluate_ns_fit, evaluate_spreads

__all__ = [
    "load_russian_yield_curve",
    "load_chinese_yield_curve",
    "load_global_indicators",
    "load_macro_indicators",
    "fit_nelson_siegel",
    "compute_residuals",
    "build_spreads",
    "flag_abnormal_spreads",
    "evaluate_ns_fit",
    "evaluate_spreads",
]

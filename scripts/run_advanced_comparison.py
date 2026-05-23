"""
Compare advanced methods (AER + regime DNS) against baseline stack.

Usage:
  python scripts/run_advanced_comparison.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forecasting.loaders import load_russian_yield_curve, load_macro_indicators
from src.forecasting.ns_baseline import get_fitted_curves, compute_residuals
from src.forecasting.evaluate import evaluate_ns_fit
from src.forecasting.aer import run_aer
from src.forecasting.regime_dns import fit_regime_dns, forecast_regime_dns


def _rmse(a: pd.Series, b: pd.Series) -> float:
    common = a.index.intersection(b.index)
    if common.empty:
        return float("nan")
    d = a.loc[common].astype(float) - b.loc[common].astype(float)
    return float(np.sqrt(np.nanmean(d**2)))


def main():
    ap = argparse.ArgumentParser(description="Run advanced method comparison")
    ap.add_argument(
        "--output-prefix",
        type=str,
        default="project report/tables/tab_6_4_advanced_methods",
        help="Output prefix for CSV and LaTeX",
    )
    args = ap.parse_args()

    ru = load_russian_yield_curve()
    if ru.empty:
        print("No RU yield data. Run pipeline first.")
        return 1

    # Baseline NS
    fitted = get_fitted_curves(ru)
    residuals = compute_residuals(ru)
    ns_eval = evaluate_ns_fit(ru, fitted, residuals)
    ns_rmse = ns_eval.get("overall", {}).get("RMSE_mean", np.nan)

    # AER proxy
    aer = run_aer(ru, lambda_aer=0.1)
    aer_obj = aer.get("objective_mean", np.nan)
    aer_penalty = aer.get("penalty_mean", np.nan)

    # Regime DNS (macro threshold using DGS10 when available)
    macro = load_macro_indicators()
    macro_col = None
    for c in ["global_indicators_DGS10", "global_indicators_FEDFUNDS"]:
        if c in macro.columns:
            macro_col = c
            break
    regime_status = "not_fitted"
    regime_rmse = np.nan
    if macro_col is not None:
        regime_model = fit_regime_dns(ru, macro, macro_col=macro_col, lam=2.0, min_obs=20)
        if regime_model is not None:
            last_macro = float(macro[macro_col].dropna().iloc[-1])
            fc = forecast_regime_dns(regime_model, current_macro_value=last_macro, horizon=1)
            if not fc.empty:
                actual = ru.iloc[-1]
                pred = fc.iloc[0]
                rmses = []
                for col in [c for c in ru.columns if c in pred.index]:
                    if pd.notna(actual.get(col)) and pd.notna(pred.get(col)):
                        rmses.append((float(actual[col]) - float(pred[col])) ** 2)
                regime_rmse = float(np.sqrt(np.mean(rmses))) if rmses else np.nan
                regime_status = "fitted"
            else:
                regime_status = "fitted_no_forecast"
        else:
            regime_status = "fit_failed"
    else:
        regime_status = "missing_macro"

    rows = [
        {"Method": "NS_baseline", "Metric": "RMSE_mean", "Value": ns_rmse, "Notes": "In-sample overall RMSE"},
        {"Method": "AER_proxy", "Metric": "Objective_mean", "Value": aer_obj, "Notes": "MSE + lambda * curvature penalty"},
        {"Method": "AER_proxy", "Metric": "Penalty_mean", "Value": aer_penalty, "Notes": "Average curvature smoothness penalty"},
        {"Method": "Regime_DNS", "Metric": "1step_RMSE_last", "Value": regime_rmse, "Notes": f"Status={regime_status}; macro={macro_col}"},
    ]
    out_df = pd.DataFrame(rows)

    out_prefix = Path(args.output_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    out_csv = out_prefix.with_suffix(".csv")
    out_tex = out_prefix.with_suffix(".tex")
    out_df.to_csv(out_csv, index=False)
    latex = out_df.to_latex(
        index=False,
        float_format="%.6f",
        caption="Advanced method comparison (AER proxy and regime DNS)",
        label="tab:6_4",
    )
    out_tex.write_text(latex, encoding="utf-8")

    print("Advanced comparison summary:")
    print(out_df.to_string(index=False))
    print(f"\nSaved: {out_csv}")
    print(f"Saved: {out_tex}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


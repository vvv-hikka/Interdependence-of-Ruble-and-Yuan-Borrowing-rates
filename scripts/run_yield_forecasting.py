"""
Run yield curve forecasting experiments.
Entry point: baseline NS, cross-currency spreads, evaluation.

Usage:
  python scripts/run_yield_forecasting.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
"""

import argparse
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.forecasting.loaders import (
    load_russian_yield_curve,
    load_chinese_yield_curve,
)
from src.forecasting.ns_baseline import compute_residuals, get_fitted_curves
from src.forecasting.cross_currency import build_spreads, flag_abnormal_spreads
from src.forecasting.evaluate import evaluate_ns_fit, evaluate_spreads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    ap.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    args = ap.parse_args()
    start_date = getattr(args, "start_date", None)
    end_date = getattr(args, "end_date", None)

    print("=" * 60)
    print("YIELD CURVE FORECASTING EXPERIMENTS")
    print("=" * 60)

    # Load data
    print("\n1. Loading yield curves...")
    ru_yields = load_russian_yield_curve(start_date=start_date, end_date=end_date)
    cn_yields = load_chinese_yield_curve(start_date=start_date, end_date=end_date)
    print(f"   RU: {len(ru_yields)} rows, {list(ru_yields.columns)}")
    print(f"   CN: {len(cn_yields)} rows, {list(cn_yields.columns)}")

    if ru_yields.empty and cn_yields.empty:
        print("   No yield data. Run pipeline first.")
        return 1

    # Baseline NS
    print("\n2. Nelson-Siegel baseline (RU)...")
    if not ru_yields.empty:
        ru_fitted = get_fitted_curves(ru_yields)
        ru_residuals = compute_residuals(ru_yields)
        ru_eval = evaluate_ns_fit(ru_yields, ru_fitted, ru_residuals)
        print(f"   Overall MAE: {ru_eval.get('overall', {}).get('MAE_mean', 'N/A')}")
        print(f"   Overall RMSE: {ru_eval.get('overall', {}).get('RMSE_mean', 'N/A')}")
        for col, s in ru_eval.get("by_maturity", {}).items():
            print(f"   {col}: MAE={s['MAE']:.4f}, RMSE={s['RMSE']:.4f}")

    print("\n3. Nelson-Siegel baseline (CN)...")
    if not cn_yields.empty:
        cn_fitted = get_fitted_curves(cn_yields)
        cn_residuals = compute_residuals(cn_yields)
        cn_eval = evaluate_ns_fit(cn_yields, cn_fitted, cn_residuals)
        print(f"   Overall MAE: {cn_eval.get('overall', {}).get('MAE_mean', 'N/A')}")
        print(f"   Overall RMSE: {cn_eval.get('overall', {}).get('RMSE_mean', 'N/A')}")
        for col, s in cn_eval.get("by_maturity", {}).items():
            print(f"   {col}: MAE={s['MAE']:.4f}, RMSE={s['RMSE']:.4f}")

    # Cross-currency spreads
    print("\n4. Cross-currency spreads (RUB-CNY)...")
    spreads = build_spreads(ru_yields, cn_yields)
    if spreads.empty:
        print("   No common maturities or overlapping dates.")
    else:
        flagged = flag_abnormal_spreads(spreads, z_threshold=2.0)
        spread_eval = evaluate_spreads(spreads, flagged)
        print(f"   Spread columns: {list(spreads.columns)}")
        for col, s in spread_eval.get("spread_stats", {}).items():
            m, sd = s.get("mean", 0), s.get("std")
            sd_str = f"{sd:.4f}" if sd is not None and sd == sd else "N/A"
            print(f"   {col}: mean={m:.4f}, std={sd_str}")
        for col, cnt in spread_eval.get("abnormal_counts", {}).items():
            print(f"   {col}: {int(cnt)} abnormal")

    # Scope note
    print("\n5. Scope note:")
    print("   - AER: not implemented yet (placeholder in src/forecasting/aer.py)")
    print("   - DNS baseline exists in src/forecasting/regime_dns.py")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

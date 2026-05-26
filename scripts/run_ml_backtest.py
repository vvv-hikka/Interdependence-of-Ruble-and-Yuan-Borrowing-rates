"""
Backtest ML signals against RU/CN proxy returns.

Usage:
  python scripts/run_ml_backtest.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forecasting.loaders import load_russian_yield_curve, load_chinese_yield_curve
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest ML arbitrage signals")
    ap.add_argument("--signals", type=str, default="data/processed/ml_signals.csv")
    ap.add_argument("--out", type=str, default="data/processed/ml_backtest_summary.csv")
    ap.add_argument("--returns-out", type=str, default="data/processed/ml_backtest_monthly_returns.csv")
    ap.add_argument("--inference-out", type=str, default="data/processed/ml_backtest_inference.csv")
    ap.add_argument("--stability-out", type=str, default="data/processed/ml_backtest_stability.csv")
    ap.add_argument("--cost-bps", type=float, default=5.0, help="Transaction cost in bps per turnover unit")
    ap.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap iterations for CI")
    args = ap.parse_args()

    sig_path = Path(args.signals)
    if not sig_path.exists():
        print(f"Missing ML signals file: {sig_path}")
        return 1
    sig = pd.read_csv(sig_path, parse_dates=["date"]).set_index("date").sort_index()
    if "ml_signal" not in sig.columns:
        print("Missing 'ml_signal' column.")
        return 1

    ru = load_russian_yield_curve()
    cn = load_chinese_yield_curve()
    if ru.empty or cn.empty:
        print("No RU/CN data. Run pipeline first.")
        return 1
    returns = compute_proxy_returns(ru, cn)
    common = returns.index.intersection(sig.index)
    if common.empty:
        print("No overlap between ML signals and returns.")
        return 1

    aligned = pd.DataFrame(index=common)
    aligned["spread_ret"] = returns.loc[common, "spread_ret"].astype(float)
    aligned["ml_signal_raw"] = sig.loc[common, "ml_signal"].astype(float)
    aligned["signal"] = align_signal_to_next_return(aligned["ml_signal_raw"], aligned.index)
    aligned["turnover"] = compute_turnover(aligned["signal"])

    aligned["strategy_gross_ret"] = aligned["signal"] * aligned["spread_ret"]
    aligned["strategy_net_ret"], aligned["strategy_cost"] = apply_transaction_costs(
        aligned["strategy_gross_ret"], aligned["turnover"], cost_bps=args.cost_bps
    )

    aligned["passive_signal"] = 1.0
    aligned["passive_turnover"] = compute_turnover(aligned["passive_signal"])
    aligned["passive_gross_ret"] = aligned["spread_ret"]
    aligned["passive_net_ret"], aligned["passive_cost"] = apply_transaction_costs(
        aligned["passive_gross_ret"], aligned["passive_turnover"], cost_bps=args.cost_bps
    )

    strat_stats = summarize_series(
        strategy_name="ml_strategy",
        net_returns=aligned["strategy_net_ret"],
        active_signal=aligned["signal"],
        turnover=aligned["turnover"],
        costs=aligned["strategy_cost"],
    )
    passive_stats = summarize_series(
        strategy_name="ml_passive_spread",
        net_returns=aligned["passive_net_ret"],
        active_signal=aligned["passive_signal"],
        turnover=aligned["passive_turnover"],
        costs=aligned["passive_cost"],
    )

    s_row = to_stats_row(strat_stats)
    p_row = to_stats_row(passive_stats)
    s_row["benchmark"] = "ml_passive_spread"
    p_row["benchmark"] = "ml_passive_spread"
    s_row["excess_ann_return_vs_benchmark"] = round(s_row["ann_return"] - p_row["ann_return"], 6)
    s_row["sharpe_delta_vs_benchmark"] = round(s_row["ann_sharpe"] - p_row["ann_sharpe"], 6)
    p_row["excess_ann_return_vs_benchmark"] = 0.0
    p_row["sharpe_delta_vs_benchmark"] = 0.0
    summary = pd.DataFrame([s_row, p_row])

    mean_diff, mean_lo, mean_hi = bootstrap_mean_diff_ci(
        aligned["strategy_net_ret"], aligned["passive_net_ret"], n_boot=args.bootstrap
    )
    sharpe_diff, sh_lo, sh_hi = bootstrap_sharpe_diff_ci(
        aligned["strategy_net_ret"], aligned["passive_net_ret"], n_boot=args.bootstrap
    )
    t_stat, p_val = paired_ttest(aligned["strategy_net_ret"], aligned["passive_net_ret"])
    inference = pd.DataFrame(
        [
            {
                "comparison": "ml_strategy_vs_passive",
                "mean_return_diff": round(mean_diff, 8) if pd.notna(mean_diff) else mean_diff,
                "mean_diff_ci_low": round(mean_lo, 8) if pd.notna(mean_lo) else mean_lo,
                "mean_diff_ci_high": round(mean_hi, 8) if pd.notna(mean_hi) else mean_hi,
                "sharpe_diff": round(sharpe_diff, 6) if pd.notna(sharpe_diff) else sharpe_diff,
                "sharpe_diff_ci_low": round(sh_lo, 6) if pd.notna(sh_lo) else sh_lo,
                "sharpe_diff_ci_high": round(sh_hi, 6) if pd.notna(sh_hi) else sh_hi,
                "paired_t_stat": round(t_stat, 6) if pd.notna(t_stat) else t_stat,
                "paired_t_pvalue": round(p_val, 6) if pd.notna(p_val) else p_val,
                "n_obs": int(len(aligned)),
                "cost_bps": float(args.cost_bps),
            }
        ]
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False)
    returns_out = Path(args.returns_out)
    aligned.to_csv(returns_out, index_label="date")
    inference_out = Path(args.inference_out)
    inference.to_csv(inference_out, index=False)
    # Sensitivity grid for strategy stability (threshold/cost robustness proxy).
    grids = [(0.55, 0.45, args.cost_bps), (0.60, 0.40, args.cost_bps), (0.55, 0.45, args.cost_bps + 5.0)]
    stab_rows = []
    for long_t, short_t, cbps in grids:
        if "proba_ensemble" in sig.columns:
            sig_tmp = np.where(sig["proba_ensemble"] >= long_t, 1, np.where(sig["proba_ensemble"] <= short_t, -1, 0))
        else:
            sig_tmp = sig["ml_signal"].astype(float).values
        tmp = pd.DataFrame(index=common)
        tmp["spread_ret"] = returns.loc[common, "spread_ret"].astype(float)
        tmp["signal_raw"] = pd.Series(sig_tmp, index=sig.index).reindex(common).fillna(0.0)
        tmp["signal"] = align_signal_to_next_return(tmp["signal_raw"], tmp.index)
        tmp["turnover"] = compute_turnover(tmp["signal"])
        tmp["gross"] = tmp["signal"] * tmp["spread_ret"]
        tmp["net"], _ = apply_transaction_costs(tmp["gross"], tmp["turnover"], cost_bps=cbps)
        ann_ret = float(tmp["net"].mean() * 12)
        ann_vol = float(tmp["net"].std() * (12 ** 0.5))
        ann_sh = ann_ret / (ann_vol + 1e-12)
        stab_rows.append(
            {
                "prob_long": long_t,
                "prob_short": short_t,
                "cost_bps": cbps,
                "active_pct": float((tmp["signal"] != 0).mean()),
                "ann_sharpe": round(float(ann_sh), 6),
                "ann_return": round(float(ann_ret), 6),
            }
        )
    stability = pd.DataFrame(stab_rows)
    stability.to_csv(Path(args.stability_out), index=False)

    print("ML backtest summary:")
    print(summary.to_string(index=False))
    print(f"Saved: {out}")
    print(f"Saved: {returns_out}")
    print(f"Saved: {inference_out}")
    print(f"Saved: {args.stability_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

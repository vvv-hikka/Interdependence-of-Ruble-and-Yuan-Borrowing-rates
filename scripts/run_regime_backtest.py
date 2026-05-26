"""
Run regime-stratified backtests and v1 router decisions.

Usage:
  python scripts/run_regime_backtest.py
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
from src.signals.signal_config import SignalConfig, ArtifactVersion


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _classical_signal_series(path: Path) -> pd.Series:
    df = _read(path)
    if df.empty or "date" not in df.columns:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    sig_cols = [
        c for c in df.columns if c.startswith("spread_signal_") or c.startswith("cip_signal_") or c in ("signal_RU", "signal_CN")
    ]
    if not sig_cols:
        return pd.Series(dtype=float)
    for c in sig_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    s = df.groupby("date")[sig_cols].mean().mean(axis=1).clip(-1.0, 1.0)
    return s.sort_index()


def _ml_signal_series(df: pd.DataFrame, model: str) -> pd.Series:
    if df.empty or "date" not in df.columns:
        return pd.Series(dtype=float)
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    if model == "ML_ENS":
        if "ml_signal" not in d.columns:
            return pd.Series(dtype=float)
        return d.set_index("date")["ml_signal"].astype(float).sort_index()

    proba_col = {
        "ML_LOGIT": "proba_logit",
        "ML_RF": "proba_rf",
        "ML_RIDGE": "proba_ridge",
        "ML_HGB": "proba_hgb",
    }.get(model)
    if proba_col is None or proba_col not in d.columns:
        return pd.Series(dtype=float)
    proba = pd.to_numeric(d[proba_col], errors="coerce")
    sig = np.where(proba >= 0.55, 1, np.where(proba <= 0.45, -1, 0))
    out = pd.Series(sig, index=d["date"], name=model).astype(float)
    return out.sort_index()


def _evaluate_single(
    signal_raw: pd.Series,
    spread_ret: pd.Series,
    benchmark: pd.Series,
    strategy_name: str,
    benchmark_name: str,
    cost_bps: float,
    n_boot: int,
) -> tuple[dict, dict, pd.DataFrame]:
    idx = spread_ret.index.intersection(signal_raw.index).intersection(benchmark.index)
    if len(idx) < 12:
        return {}, {}, pd.DataFrame()
    aligned = pd.DataFrame(index=idx)
    aligned["spread_ret"] = spread_ret.loc[idx].astype(float)
    aligned["signal_raw"] = signal_raw.loc[idx].astype(float)
    aligned["signal"] = align_signal_to_next_return(aligned["signal_raw"], aligned.index)
    aligned["turnover"] = compute_turnover(aligned["signal"])
    aligned["strategy_gross_ret"] = aligned["signal"] * aligned["spread_ret"]
    aligned["strategy_net_ret"], aligned["strategy_cost"] = apply_transaction_costs(
        aligned["strategy_gross_ret"], aligned["turnover"], cost_bps=cost_bps
    )

    aligned["bench_signal"] = benchmark.loc[idx].astype(float)
    aligned["bench_turnover"] = compute_turnover(aligned["bench_signal"])
    aligned["bench_gross_ret"] = aligned["bench_signal"] * aligned["spread_ret"]
    aligned["bench_net_ret"], aligned["bench_cost"] = apply_transaction_costs(
        aligned["bench_gross_ret"], aligned["bench_turnover"], cost_bps=cost_bps
    )

    s_stats = summarize_series(
        strategy_name=strategy_name,
        net_returns=aligned["strategy_net_ret"],
        active_signal=aligned["signal"],
        turnover=aligned["turnover"],
        costs=aligned["strategy_cost"],
    )
    b_stats = summarize_series(
        strategy_name=benchmark_name,
        net_returns=aligned["bench_net_ret"],
        active_signal=aligned["bench_signal"],
        turnover=aligned["bench_turnover"],
        costs=aligned["bench_cost"],
    )
    s_row = to_stats_row(s_stats)
    b_row = to_stats_row(b_stats)
    s_row["benchmark"] = benchmark_name
    b_row["benchmark"] = benchmark_name
    s_row["excess_ann_return_vs_benchmark"] = round(s_row["ann_return"] - b_row["ann_return"], 6)
    s_row["sharpe_delta_vs_benchmark"] = round(s_row["ann_sharpe"] - b_row["ann_sharpe"], 6)
    b_row["excess_ann_return_vs_benchmark"] = 0.0
    b_row["sharpe_delta_vs_benchmark"] = 0.0

    mean_diff, mean_lo, mean_hi = bootstrap_mean_diff_ci(
        aligned["strategy_net_ret"], aligned["bench_net_ret"], n_boot=n_boot
    )
    sharpe_diff, sh_lo, sh_hi = bootstrap_sharpe_diff_ci(
        aligned["strategy_net_ret"], aligned["bench_net_ret"], n_boot=n_boot
    )
    t_stat, p_val = paired_ttest(aligned["strategy_net_ret"], aligned["bench_net_ret"])
    inf_row = {
        "comparison": f"{strategy_name}_vs_{benchmark_name}",
        "mean_return_diff": mean_diff,
        "mean_diff_ci_low": mean_lo,
        "mean_diff_ci_high": mean_hi,
        "sharpe_diff": sharpe_diff,
        "sharpe_diff_ci_low": sh_lo,
        "sharpe_diff_ci_high": sh_hi,
        "paired_t_stat": t_stat,
        "paired_t_pvalue": p_val,
        "n_obs": int(len(aligned)),
        "cost_bps": float(cost_bps),
    }
    return s_row, inf_row, aligned


def main() -> int:
    ap = argparse.ArgumentParser(description="Run regime-stratified strategy backtests")
    ap.add_argument("--signals", type=str, default="data/processed/signals_latest.csv")
    ap.add_argument("--ml-signals", type=str, default="data/processed/ml_signals.csv")
    ap.add_argument("--regimes", type=str, default="data/processed/regime_labels_monthly.csv")
    ap.add_argument("--cost-bps", type=float, default=5.0)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--summary-out", type=str, default="data/processed/regime_backtest_summary.csv")
    ap.add_argument("--returns-out", type=str, default="data/processed/regime_backtest_monthly_returns.csv")
    ap.add_argument("--inference-out", type=str, default="data/processed/regime_backtest_inference.csv")
    ap.add_argument("--router-out", type=str, default="data/processed/regime_router_decisions.csv")
    ap.add_argument("--ml-decisions", type=str, default="data/processed/ml_signals_decisions.csv")
    ap.add_argument("--min-obs", type=int, default=12)
    args = ap.parse_args()
    cfg = SignalConfig()
    ver = ArtifactVersion()

    ru = load_russian_yield_curve()
    cn = load_chinese_yield_curve()
    if ru.empty or cn.empty:
        print("Missing RU/CN data.")
        return 1
    ret = compute_proxy_returns(ru, cn)
    spread_ret = ret["spread_ret"].copy()
    reg = _read(Path(args.regimes))
    if reg.empty:
        print("Missing regime labels.")
        return 1
    reg["date"] = pd.to_datetime(reg["date"])
    reg = reg.set_index("date").sort_index()

    classical = _classical_signal_series(Path(args.signals))
    ml_df = _read(Path(args.ml_signals))
    ml_decisions = _read(Path(args.ml_decisions))
    models = {
        "CL_PANEL": classical,
        "CL_SPREAD": classical,
        "ML_ENS": _ml_signal_series(ml_df, "ML_ENS"),
        "ML_LOGIT": _ml_signal_series(ml_df, "ML_LOGIT"),
        "ML_RF": _ml_signal_series(ml_df, "ML_RF"),
    }
    benchmark = pd.Series(1.0, index=spread_ret.index, name="PASSIVE_SPREAD")
    regime_cols = [c for c in ["regime_R1_lag1", "regime_M1_lag1", "regime_C1_lag1", "ms_state_persist_lag1"] if c in reg.columns]
    if not regime_cols:
        print("No required regime columns found.")
        return 1

    summary_rows = []
    inf_rows = []
    returns_rows = []
    router_rows = []

    for rid in regime_cols:
        vc = reg[rid].value_counts()
        for cell, n_obs in vc.items():
            idx_reg = reg.index[reg[rid] == cell]
            if len(idx_reg) < args.min_obs:
                continue
            model_perf = []
            for model_id, sig in models.items():
                if sig.empty:
                    continue
                s_row, inf_row, aligned = _evaluate_single(
                    signal_raw=sig.loc[sig.index.intersection(idx_reg)],
                    spread_ret=spread_ret.loc[spread_ret.index.intersection(idx_reg)],
                    benchmark=benchmark.loc[benchmark.index.intersection(idx_reg)],
                    strategy_name=model_id,
                    benchmark_name="PASSIVE_SPREAD",
                    cost_bps=args.cost_bps,
                    n_boot=args.bootstrap,
                )
                if not s_row:
                    continue
                s_row["regime_id"] = rid.replace("_lag1", "")
                s_row["regime_cell"] = str(cell)
                s_row["n_obs"] = int(n_obs)
                s_row["family"] = "regime_router"
                summary_rows.append(s_row)

                inf_row["regime_id"] = rid.replace("_lag1", "")
                inf_row["regime_cell"] = str(cell)
                inf_row["model_id"] = model_id
                inf_row["family"] = "regime_router"
                inf_rows.append(inf_row)

                if not aligned.empty:
                    tmp = aligned.copy()
                    tmp["regime_id"] = rid.replace("_lag1", "")
                    tmp["regime_cell"] = str(cell)
                    tmp["model_id"] = model_id
                    tmp["family"] = "regime_router"
                    tmp = tmp.reset_index().rename(columns={"index": "date"})
                    returns_rows.append(tmp)

                score = (
                    0.55 * float(s_row["ann_sharpe"])
                    + 0.20 * float(s_row.get("ann_sortino", 0.0))
                    - 0.10 * abs(float(s_row.get("max_drawdown", 0.0)))
                    - 0.05 * float(s_row.get("ann_turnover", 0.0))
                    - 0.10 * float(s_row.get("total_cost_drag", 0.0))
                )
                model_perf.append((model_id, score, float(s_row["ann_sharpe"]), int(n_obs)))

            if model_perf:
                best_model, best_score, best_sharpe, n = sorted(model_perf, key=lambda x: x[1], reverse=True)[0]
                chosen = best_model if n >= args.min_obs else "neutral"
                conf = 0.5
                reason = "score_selected"
                expected_edge = best_score / 100.0
                if not ml_decisions.empty:
                    dtmp = ml_decisions.copy()
                    if "date" in dtmp.columns:
                        dtmp["date"] = pd.to_datetime(dtmp["date"])
                        dtmp = dtmp.set_index("date")
                        sub = dtmp.loc[dtmp.index.intersection(idx_reg)]
                        if not sub.empty:
                            conf = float(pd.to_numeric(sub.get("confidence"), errors="coerce").mean())
                            expected_edge = float(pd.to_numeric(sub.get("expected_net_edge"), errors="coerce").mean())
                            mode_reason = sub.get("reason_code")
                            if mode_reason is not None and not mode_reason.dropna().empty:
                                reason = str(mode_reason.dropna().mode().iloc[0])
                if conf < cfg.min_confidence or expected_edge <= cfg.min_expected_edge:
                    chosen = "neutral"
                    reason = "low_confidence_or_edge"
                router_rows.append(
                    {
                        "regime_id": rid.replace("_lag1", ""),
                        "regime_cell": str(cell),
                        "selected_model": chosen,
                        "router_score": round(best_score, 6),
                        "selected_ann_sharpe": round(best_sharpe, 6),
                        "confidence": round(conf, 6),
                        "expected_net_edge": round(expected_edge, 6),
                        "reason_code": reason,
                        "no_trade": int(chosen == "neutral"),
                        "n_obs": int(n),
                        "label_version": ver.label_version,
                        "router_policy_version": ver.router_policy_version,
                    }
                )

    summary = pd.DataFrame(summary_rows)
    inference = pd.DataFrame(inf_rows)
    monthly = pd.concat(returns_rows, ignore_index=True) if returns_rows else pd.DataFrame()
    router = pd.DataFrame(router_rows)

    Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary_out, index=False)
    inference.to_csv(args.inference_out, index=False)
    monthly.to_csv(args.returns_out, index=False)
    router.to_csv(args.router_out, index=False)

    print(f"Saved: {args.summary_out}")
    print(f"Saved: {args.inference_out}")
    print(f"Saved: {args.returns_out}")
    print(f"Saved: {args.router_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

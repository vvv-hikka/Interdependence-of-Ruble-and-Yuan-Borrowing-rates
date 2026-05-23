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


def _compute_proxy_returns(ru: pd.DataFrame, cn: pd.DataFrame) -> pd.DataFrame:
    ru_col = "RU_10Y" if "RU_10Y" in ru.columns else ru.columns[0]
    cn_col = "CN_10Y" if "CN_10Y" in cn.columns else cn.columns[0]
    common = ru.index.intersection(cn.index)
    out = pd.DataFrame(index=common)
    out["RUB"] = -ru.loc[common, ru_col].diff().fillna(0.0) / 100.0
    out["CNY"] = -cn.loc[common, cn_col].diff().fillna(0.0) / 100.0
    out["spread_ret"] = out["RUB"] - out["CNY"]
    return out


def _metrics(series: pd.Series) -> dict:
    s = series.dropna()
    if s.empty:
        return {
            "ann_sharpe": np.nan,
            "max_drawdown": np.nan,
            "var95_empirical": np.nan,
            "mean_return": np.nan,
            "hit_ratio": np.nan,
        }
    cum = (1.0 + s).cumprod()
    sharpe = float((s.mean() / (s.std() + 1e-12)) * np.sqrt(12))
    drawdown = float((cum / cum.cummax() - 1.0).min())
    var95 = float(np.quantile(-s, 0.95))
    hit = float((s > 0).mean())
    return {
        "ann_sharpe": round(sharpe, 4),
        "max_drawdown": round(drawdown, 4),
        "var95_empirical": round(var95, 4),
        "mean_return": round(float(s.mean()), 6),
        "hit_ratio": round(hit, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest ML arbitrage signals")
    ap.add_argument("--signals", type=str, default="data/processed/ml_signals.csv")
    ap.add_argument("--out", type=str, default="data/processed/ml_backtest_summary.csv")
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
    returns = _compute_proxy_returns(ru, cn)
    common = returns.index.intersection(sig.index)
    if common.empty:
        print("No overlap between ML signals and returns.")
        return 1

    aligned = pd.DataFrame(index=common)
    aligned["spread_ret"] = returns.loc[common, "spread_ret"]
    aligned["signal"] = sig.loc[common, "ml_signal"].astype(int)
    aligned["strategy_ret"] = aligned["signal"] * aligned["spread_ret"]
    aligned["passive_spread"] = aligned["spread_ret"]
    aligned["active_rate"] = (aligned["signal"] != 0).astype(int)

    strategy_stats = _metrics(aligned["strategy_ret"])
    passive_stats = _metrics(aligned["passive_spread"])
    summary = pd.DataFrame(
        [
            {"strategy": "ml_strategy", **strategy_stats, "active_pct": round(float(aligned["active_rate"].mean()), 4)},
            {"strategy": "ml_passive_spread", **passive_stats, "active_pct": 1.0},
        ]
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False)
    print("ML backtest summary:")
    print(summary.to_string(index=False))
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Combine classical and ML backtest outputs into unified artifacts.

Usage:
  python scripts/run_unified_backtest.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser(description="Create unified backtest artifacts")
    ap.add_argument("--classical-summary", type=str, default="data/processed/portfolio_backtest_summary.csv")
    ap.add_argument("--ml-summary", type=str, default="data/processed/ml_backtest_summary.csv")
    ap.add_argument("--classical-inference", type=str, default="data/processed/portfolio_backtest_inference.csv")
    ap.add_argument("--ml-inference", type=str, default="data/processed/ml_backtest_inference.csv")
    ap.add_argument("--classical-returns", type=str, default="data/processed/portfolio_backtest_monthly_returns.csv")
    ap.add_argument("--ml-returns", type=str, default="data/processed/ml_backtest_monthly_returns.csv")
    ap.add_argument("--regime-summary", type=str, default="data/processed/regime_backtest_summary.csv")
    ap.add_argument("--regime-inference", type=str, default="data/processed/regime_backtest_inference.csv")
    ap.add_argument("--regime-returns", type=str, default="data/processed/regime_backtest_monthly_returns.csv")
    ap.add_argument("--router-decisions", type=str, default="data/processed/regime_router_decisions.csv")
    ap.add_argument("--ml-decisions", type=str, default="data/processed/ml_signals_decisions.csv")
    ap.add_argument("--out-summary", type=str, default="data/processed/unified_backtest_summary.csv")
    ap.add_argument("--out-inference", type=str, default="data/processed/unified_backtest_inference.csv")
    ap.add_argument("--out-returns", type=str, default="data/processed/unified_backtest_monthly_returns.csv")
    ap.add_argument("--out-decisions", type=str, default="data/processed/unified_router_decisions.csv")
    args = ap.parse_args()

    classical = _load(Path(args.classical_summary))
    ml = _load(Path(args.ml_summary))
    regime = _load(Path(args.regime_summary))
    if classical.empty and ml.empty:
        print("No classical/ML summary files found.")
        return 1

    frames = []
    if not classical.empty:
        c = classical.copy()
        c["family"] = "classical"
        frames.append(c)
    if not ml.empty:
        m = ml.copy()
        m["family"] = "ml"
        frames.append(m)
    if not regime.empty:
        r = regime.copy()
        if "family" not in r.columns:
            r["family"] = "regime_router"
        frames.append(r)
    summary = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    inf_frames = []
    c_inf = _load(Path(args.classical_inference))
    if not c_inf.empty:
        c_inf["family"] = "classical"
        inf_frames.append(c_inf)
    m_inf = _load(Path(args.ml_inference))
    if not m_inf.empty:
        m_inf["family"] = "ml"
        inf_frames.append(m_inf)
    r_inf = _load(Path(args.regime_inference))
    if not r_inf.empty:
        if "family" not in r_inf.columns:
            r_inf["family"] = "regime_router"
        inf_frames.append(r_inf)
    inference = pd.concat(inf_frames, ignore_index=True) if inf_frames else pd.DataFrame()

    ret_frames = []
    c_ret = _load(Path(args.classical_returns))
    if not c_ret.empty:
        c_ret["family"] = "classical"
        ret_frames.append(c_ret)
    m_ret = _load(Path(args.ml_returns))
    if not m_ret.empty:
        m_ret["family"] = "ml"
        ret_frames.append(m_ret)
    r_ret = _load(Path(args.regime_returns))
    if not r_ret.empty:
        if "family" not in r_ret.columns:
            r_ret["family"] = "regime_router"
        ret_frames.append(r_ret)
    returns = pd.concat(ret_frames, ignore_index=True) if ret_frames else pd.DataFrame()

    dec_frames = []
    r_dec = _load(Path(args.router_decisions))
    if not r_dec.empty:
        r_dec["decision_family"] = "regime_router"
        dec_frames.append(r_dec)
    m_dec = _load(Path(args.ml_decisions))
    if not m_dec.empty:
        m_dec["decision_family"] = "ml_gate"
        dec_frames.append(m_dec)
    decisions = pd.concat(dec_frames, ignore_index=True) if dec_frames else pd.DataFrame()

    out_summary = Path(args.out_summary)
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary, index=False)
    print(f"Saved: {out_summary}")

    out_inf = Path(args.out_inference)
    inference.to_csv(out_inf, index=False)
    print(f"Saved: {out_inf}")

    out_ret = Path(args.out_returns)
    returns.to_csv(out_ret, index=False)
    print(f"Saved: {out_ret}")

    out_dec = Path(args.out_decisions)
    decisions.to_csv(out_dec, index=False)
    print(f"Saved: {out_dec}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

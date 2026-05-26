"""
Lightweight schema regression checks for key output CSVs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def _check(path: Path, required_cols: list[str]) -> list[str]:
    if not path.exists():
        return [f"missing file: {path}"]
    df = pd.read_csv(path, nrows=1)
    miss = [c for c in required_cols if c not in df.columns]
    if miss:
        return [f"{path.name}: missing columns {miss}"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Check output artifact schemas")
    ap.add_argument("--processed-dir", type=str, default="data/processed")
    args = ap.parse_args()
    p = Path(args.processed_dir)

    checks = {
        p / "ml_signals.csv": [
            "date",
            "proba_ensemble",
            "ml_signal",
            "proba_opportunity",
            "proba_final_long",
            "proba_final_short",
        ],
        p / "ml_signals_decisions.csv": [
            "date",
            "selected_model",
            "trade_enabled",
            "confidence",
            "expected_net_edge",
            "reason_code",
        ],
        p / "regime_router_decisions.csv": [
            "regime_id",
            "regime_cell",
            "selected_model",
            "confidence",
            "expected_net_edge",
            "reason_code",
            "no_trade",
        ],
        p / "unified_backtest_summary.csv": [
            "strategy",
            "ann_return",
            "ann_sharpe",
            "family",
        ],
    }

    errs: list[str] = []
    for path, cols in checks.items():
        errs.extend(_check(path, cols))

    if errs:
        print("Schema check failed:")
        for e in errs:
            print(f" - {e}")
        return 1
    print("Schema check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

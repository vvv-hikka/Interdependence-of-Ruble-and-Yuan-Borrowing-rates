"""
Generate ML arbitrage signals and export artifacts.

Usage:
  python scripts/run_ml_signals.py
  python scripts/run_ml_signals.py --save-prefix data/processed/ml_signals
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forecasting.loaders import load_russian_yield_curve, load_chinese_yield_curve
from src.signals.ml_signals import generate_ml_signals

try:
    from config import DB_PATH
except ImportError:
    DB_PATH = Path(__file__).resolve().parent.parent / "bond_rates_database.db"

try:
    from src.database import DatabaseManager
except ImportError:
    DatabaseManager = None


def _load_currency_rates(start_date=None, end_date=None) -> pd.DataFrame:
    if DatabaseManager is None:
        return pd.DataFrame()
    db = DatabaseManager(str(DB_PATH))
    df = db.load_dataframe("currency_rates")
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    return df.set_index("date").sort_index()


def main() -> int:
    ap = argparse.ArgumentParser(description="Run ML-based arbitrage signals")
    ap.add_argument("--start-date", type=str, default=None)
    ap.add_argument("--end-date", type=str, default=None)
    ap.add_argument(
        "--save-prefix",
        type=str,
        default="data/processed/ml_signals",
        help="Prefix for exported CSV files (without extension)",
    )
    args = ap.parse_args()

    ru = load_russian_yield_curve(args.start_date, args.end_date)
    cn = load_chinese_yield_curve(args.start_date, args.end_date)
    fx = _load_currency_rates(args.start_date, args.end_date)
    if ru.empty or cn.empty:
        print("Insufficient RU/CN data for ML signals.")
        return 1

    result = generate_ml_signals(ru, cn, fx_rates=fx)
    if result.predictions.empty:
        print("ML signal generation returned no predictions (likely short history).")
        return 1

    prefix = Path(args.save_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    pred_path = prefix.with_suffix(".csv")
    diag_path = prefix.with_name(f"{prefix.stem}_diagnostics.csv")
    snap_path = prefix.with_name(f"{prefix.stem}_snapshot.csv")

    result.predictions.to_csv(pred_path, index_label="date")
    result.diagnostics.to_csv(diag_path, index=False)

    snapshot = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp.utcnow().isoformat().replace("+00:00", "Z"),
                "signal_type": "ml",
                "maturity_bucket": "10Y_rel",
                "direction": int(result.latest["direction"]),
                "strength": float(result.latest["strength"]),
                "confidence": float(result.latest["confidence"]),
                "proba_ensemble": float(result.latest["proba_ensemble"]),
            }
        ]
    )
    snapshot.to_csv(snap_path, index=False)

    print("ML signals exported:")
    print(f"  predictions: {pred_path}")
    print(f"  diagnostics: {diag_path}")
    print(f"  snapshot:    {snap_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

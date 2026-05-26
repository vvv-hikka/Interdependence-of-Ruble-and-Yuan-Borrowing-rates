"""
Build and export monthly regime labels/counts.

Usage:
  python scripts/run_regime_labels.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forecasting.loaders import (
    load_russian_yield_curve,
    load_chinese_yield_curve,
    load_macro_indicators,
    load_currency_rates,
)
from src.forecasting.regime_labels import build_regime_frame, regime_counts_table


def main() -> int:
    ap = argparse.ArgumentParser(description="Export monthly regime labels")
    ap.add_argument("--labels-out", type=str, default="data/processed/regime_labels_monthly.csv")
    ap.add_argument("--counts-out", type=str, default="data/processed/regime_counts.csv")
    ap.add_argument("--persistence-months", type=int, default=2)
    args = ap.parse_args()

    ru = load_russian_yield_curve()
    cn = load_chinese_yield_curve()
    macro = load_macro_indicators()
    fx = load_currency_rates()
    if ru.empty or cn.empty:
        print("Missing RU/CN yields; cannot build regimes.")
        return 1

    regime_df = build_regime_frame(
        ru=ru,
        cn=cn,
        macro=macro,
        fx=fx,
        persistence_months=args.persistence_months,
    )
    if regime_df.empty:
        print("No regime labels generated.")
        return 1
    counts = regime_counts_table(regime_df)

    labels_out = Path(args.labels_out)
    labels_out.parent.mkdir(parents=True, exist_ok=True)
    regime_df.to_csv(labels_out, index_label="date")
    counts_out = Path(args.counts_out)
    counts.to_csv(counts_out, index=False)

    print(f"Saved: {labels_out}")
    print(f"Saved: {counts_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

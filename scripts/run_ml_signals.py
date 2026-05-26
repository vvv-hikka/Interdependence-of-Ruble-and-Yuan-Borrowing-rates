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

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forecasting.loaders import (
    load_russian_yield_curve,
    load_chinese_yield_curve,
    load_macro_indicators,
    load_currency_rates,
)
from src.signals.ml_signals import generate_ml_signals
from src.signals.decision_router import build_confirmation_table
from src.signals.signal_config import SignalConfig, ArtifactVersion

def _load_classical_signals(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date").sort_index()


def _load_regimes(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date").sort_index()


def _population_stability_index(
    base: pd.Series,
    current: pd.Series,
    bins: int = 10,
) -> float:
    a = pd.to_numeric(base, errors="coerce").dropna().values
    b = pd.to_numeric(current, errors="coerce").dropna().values
    if len(a) < 20 or len(b) < 20:
        return float("nan")
    cuts = np.quantile(a, np.linspace(0, 1, bins + 1))
    cuts = np.unique(cuts)
    if len(cuts) < 3:
        return float("nan")
    pa, _ = np.histogram(a, bins=cuts)
    pb, _ = np.histogram(b, bins=cuts)
    pa = pa / max(pa.sum(), 1)
    pb = pb / max(pb.sum(), 1)
    eps = 1e-8
    return float(np.sum((pb - pa) * np.log((pb + eps) / (pa + eps))))


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
    ap.add_argument("--classical-signals", type=str, default="data/processed/signals_latest.csv")
    ap.add_argument("--regimes", type=str, default="data/processed/regime_labels_monthly.csv")
    args = ap.parse_args()
    cfg = SignalConfig()
    ver = ArtifactVersion()

    ru = load_russian_yield_curve(args.start_date, args.end_date)
    cn = load_chinese_yield_curve(args.start_date, args.end_date)
    fx = load_currency_rates(args.start_date, args.end_date)
    macro = load_macro_indicators(args.start_date, args.end_date)
    if ru.empty or cn.empty:
        print("Insufficient RU/CN data for ML signals.")
        return 1

    result = generate_ml_signals(
        ru,
        cn,
        fx_rates=fx,
        prob_long=cfg.prob_long,
        prob_short=cfg.prob_short,
        n_cv_splits=cfg.cv_splits,
        embargo=cfg.cv_embargo,
        extra_features=macro,
    )
    if result.predictions.empty:
        print("ML signal generation returned no predictions (likely short history).")
        return 1

    prefix = Path(args.save_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    pred_path = prefix.with_suffix(".csv")
    diag_path = prefix.with_name(f"{prefix.stem}_diagnostics.csv")
    snap_path = prefix.with_name(f"{prefix.stem}_snapshot.csv")
    rel_path = prefix.with_name(f"{prefix.stem}_reliability.csv")
    st_path = prefix.with_name(f"{prefix.stem}_stability.csv")
    dec_path = prefix.with_name(f"{prefix.stem}_decisions.csv")
    drift_path = prefix.with_name(f"{prefix.stem}_drift.csv")

    result.predictions.to_csv(pred_path, index_label="date")
    if not result.reliability.empty:
        result.reliability.to_csv(rel_path, index=False)
    if not result.stability.empty:
        result.stability.to_csv(st_path, index=False)
        for _, r in result.stability.iterrows():
            result.diagnostics = pd.concat(
                [
                    result.diagnostics,
                    pd.DataFrame(
                        [
                            {
                                "metric": f"stability_sharpe_l{r['prob_long']}_s{r['prob_short']}",
                                "value": float(r.get("ann_sharpe", np.nan)),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
    result.diagnostics.to_csv(diag_path, index=False)
    split = max(1, int(0.7 * len(result.predictions)))
    base = result.predictions.iloc[:split]
    curr = result.predictions.iloc[split:]
    drift_rows = []
    for col in ["proba_ensemble", "proba_opportunity", "model_proba_max", "ret_diff_lag1", "carry_proxy"]:
        if col in result.predictions.columns:
            psi = _population_stability_index(base[col], curr[col], bins=10)
            drift_rows.append({"feature": col, "psi": psi, "alert": int(pd.notna(psi) and psi >= 0.25)})
    drift_df = pd.DataFrame(drift_rows)
    drift_df.to_csv(drift_path, index=False)

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
    classical = _load_classical_signals(Path(args.classical_signals))
    regimes = _load_regimes(Path(args.regimes))
    decisions = build_confirmation_table(result.predictions, classical_signals=classical, regimes=regimes)
    if not decisions.empty:
        decisions["run_id"] = f"{ver.run_id_prefix}_{pd.Timestamp.utcnow().strftime('%Y%m%d%H%M%S')}"
        decisions["label_version"] = ver.label_version
        decisions["router_policy_version"] = ver.router_policy_version
        decisions.to_csv(dec_path, index_label="date")

    print("ML signals exported:")
    print(f"  predictions: {pred_path}")
    print(f"  diagnostics: {diag_path}")
    print(f"  snapshot:    {snap_path}")
    if rel_path.exists():
        print(f"  reliability: {rel_path}")
    if st_path.exists():
        print(f"  stability:   {st_path}")
    if dec_path.exists():
        print(f"  decisions:   {dec_path}")
    if drift_path.exists():
        print(f"  drift:       {drift_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

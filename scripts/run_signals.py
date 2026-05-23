"""
Phase 3 arbitrage signal runner.

Runs all three signal modules and prints a summary of current signals
and recent signal history.

Usage:
  python scripts/run_signals.py
  python scripts/run_signals.py --start-date 2020-01-01
  python scripts/run_signals.py --window 36 --entry-z 2.0
  python scripts/run_signals.py --save-csv output/signals.csv
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forecasting.loaders import (
    load_russian_yield_curve,
    load_chinese_yield_curve,
)
from src.signals.spread_signals import compute_spread_signals
from src.signals.cip import compute_cip_deviation
from src.signals.factor_signals import compute_factor_signals

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
    return df.set_index("date")


def _section(title: str):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


def _safe_console(text: str) -> str:
    """
    Return a console-safe string for terminals that cannot encode unicode arrows.
    """
    try:
        text.encode(sys.stdout.encoding or "utf-8")
        return text
    except Exception:
        return text.replace("→", "->")


def _compute_stability_diagnostics(df: pd.DataFrame, signal_cols: list) -> pd.DataFrame:
    """
    Compute simple stability diagnostics:
    - persistence: fraction of months where signal equals previous non-zero signal
    - flip_rate: non-zero sign changes divided by non-zero observations
    - active_pct: share of periods with active signal
    """
    rows = []
    for col in signal_cols:
        s = df[col].fillna(0).astype(int)
        non_zero = s[s != 0]
        if non_zero.empty:
            rows.append({"signal": col, "active_pct": 0.0, "persistence": 0.0, "flip_rate": 0.0})
            continue
        active_pct = float((s != 0).mean())
        shifted = non_zero.shift(1).dropna()
        aligned = non_zero.loc[shifted.index]
        persistence = float((aligned == shifted).mean()) if not shifted.empty else 0.0
        flips = int((aligned != shifted).sum()) if not shifted.empty else 0
        flip_rate = float(flips / len(non_zero)) if len(non_zero) else 0.0
        rows.append(
            {
                "signal": col,
                "active_pct": round(active_pct, 4),
                "persistence": round(persistence, 4),
                "flip_rate": round(flip_rate, 4),
            }
        )
    return pd.DataFrame(rows)


def _signal_strength_confidence(signal: int, z_score: float) -> tuple:
    strength = abs(float(z_score)) if pd.notna(z_score) else 0.0
    confidence = min(1.0, strength / 3.0)
    return int(signal), round(strength, 4), round(confidence, 4)


def _print_latest(label: str, latest: pd.Series, signal_cols: list, z_cols: list):
    """Print a two-row summary: z-scores and signals for the latest date."""
    if latest.empty:
        print(f"  {label}: no data")
        return
    date_str = latest.name.strftime("%Y-%m-%d") if hasattr(latest.name, 'strftime') else str(latest.name)
    print(f"\n  Latest ({date_str}):")

    if z_cols:
        z_vals = "  ".join(f"{c}: {latest.get(c, float('nan')):+.2f}" for c in z_cols)
        print(f"    z-scores : {z_vals}")

    sig_vals = "  ".join(
        f"{c}: {int(latest.get(c, 0)):+d}" for c in signal_cols
    )
    print(f"    signals  : {sig_vals}")


def _print_signal_history(df: pd.DataFrame, signal_cols: list, tail: int = 12):
    """Print last `tail` rows where any signal is non-zero."""
    if df.empty:
        return
    mask = (df[signal_cols] != 0).any(axis=1)
    active = df[mask].tail(tail)
    if active.empty:
        print("  (no active signals in history)")
        return
    display = active[signal_cols].copy()
    display.index = display.index.strftime("%Y-%m")
    print(display.to_string())


def main():
    parser = argparse.ArgumentParser(description="Run Phase 3 arbitrage signals")
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date",   type=str, default=None)
    parser.add_argument("--window",     type=int, default=24,
                        help="Rolling z-score window in months (default 24)")
    parser.add_argument("--entry-z",    type=float, default=1.5,
                        help="Entry z-score threshold (default 1.5)")
    parser.add_argument("--save-csv",   type=str, default=None,
                        help="Save combined signals DataFrame to this CSV path")
    args = parser.parse_args()

    print("Loading yield curves and FX data...")
    ru_yields = load_russian_yield_curve(args.start_date, args.end_date)
    cn_yields = load_chinese_yield_curve(args.start_date, args.end_date)
    fx_rates  = _load_currency_rates(args.start_date, args.end_date)

    print(f"  RU: {len(ru_yields)} obs   CN: {len(cn_yields)} obs   FX: {len(fx_rates)} obs")

    if ru_yields.empty or cn_yields.empty:
        print("Insufficient yield data. Run the pipeline first.")
        return 1

    # ------------------------------------------------------------------
    # 1. Spread signals
    # ------------------------------------------------------------------
    _section("SPREAD SIGNALS  (RU yield - CN yield,  rolling z-score)")
    spread_result = compute_spread_signals(
        ru_yields, cn_yields,
        window=args.window,
        entry_z=args.entry_z,
    )
    if spread_result.signals.empty:
        print("  No matched maturities found.")
    else:
        sig_cols = [c for c in spread_result.signals.columns if c.startswith("signal_")]
        z_cols   = [c for c in spread_result.signals.columns if c.startswith("z_")]
        print(f"  Matched maturities: {spread_result.maturities}")
        _print_latest("Spread", spread_result.latest, sig_cols, z_cols)
        print(f"\n  Active signal history (last 12 non-zero months):")
        _print_signal_history(spread_result.signals, sig_cols)

    # ------------------------------------------------------------------
    # 2. CIP deviation signals
    # ------------------------------------------------------------------
    _section("CIP DEVIATION SIGNALS  (yield diff - annualised FX change)")
    if fx_rates.empty:
        print("  No FX data available.")
        cip_result_signals = pd.DataFrame()
    else:
        cip_result = compute_cip_deviation(
            ru_yields, cn_yields, fx_rates,
            z_window=args.window,
            entry_z=args.entry_z,
        )
        if cip_result.signals.empty:
            print("  No CIP signals computed.")
            cip_result_signals = pd.DataFrame()
        else:
            sig_cols = [c for c in cip_result.signals.columns if c.startswith("cip_signal_")]
            z_cols   = [c for c in cip_result.signals.columns if c.startswith("cip_z_")]
            print(f"  Maturities: {cip_result.maturities}")
            # Latest FX premium
            if not cip_result.fx_premium.empty:
                fp_latest = cip_result.fx_premium.iloc[-1]
                fp_date   = cip_result.fx_premium.index[-1].strftime("%Y-%m")
                print(f"  Rolling annualised FX premium (CNY/RUB, {fp_date}): {fp_latest:+.2f}%")
            _print_latest("CIP", cip_result.latest, sig_cols, z_cols)
            print(f"\n  Active signal history (last 12 non-zero months):")
            _print_signal_history(cip_result.signals, sig_cols)
            cip_result_signals = cip_result.signals

    # ------------------------------------------------------------------
    # 3. Factor divergence signals
    # ------------------------------------------------------------------
    _section("FACTOR DIVERGENCE SIGNALS  (VAR residuals on NS factors)")
    factor_result = compute_factor_signals(
        ru_yields, cn_yields,
        z_window=args.window,
        threshold=args.entry_z,
    )
    if factor_result.signals.empty:
        print("  VAR fitting failed or insufficient data.")
    else:
        sig_cols = ["signal_RU", "signal_CN", "divergence"]
        z_cols_f = [c for c in factor_result.signals.columns if c.startswith("z_")]
        _print_latest("Factors", factor_result.latest, sig_cols, z_cols_f[:6])
        print(f"\n  Divergence events (last 12):")
        div_df = factor_result.signals[factor_result.signals["divergence"] == 1].tail(12)
        if div_df.empty:
            print("  (no divergence events in-sample)")
        else:
            display = div_df[["signal_RU", "signal_CN"]].copy()
            display.index = display.index.strftime("%Y-%m")
            print(display.to_string())

    # ------------------------------------------------------------------
    # 4. Consolidated summary
    # ------------------------------------------------------------------
    _section("CONSOLIDATED LATEST SIGNALS")
    rows = []
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    signal_snapshot_rows = []
    if not spread_result.signals.empty:
        for mat in spread_result.maturities:
            sig  = spread_result.latest.get(f"signal_{mat}", 0)
            z    = spread_result.latest.get(f"z_{mat}", float("nan"))
            rows.append({"maturity": mat, "spread_signal": int(sig), "spread_z": round(z, 2)})

    if rows:
        summary = pd.DataFrame(rows).set_index("maturity")
        if not cip_result_signals.empty:
            for mat in cip_result.maturities:
                if mat in summary.index:
                    summary.loc[mat, "cip_signal"] = int(cip_result.latest.get(f"cip_signal_{mat}", 0))
                    summary.loc[mat, "cip_z"]      = round(cip_result.latest.get(f"cip_z_{mat}", float("nan")), 2)
        print(summary.to_string())
        for mat in summary.index:
            spread_sig = int(summary.loc[mat, "spread_signal"])
            spread_z = float(summary.loc[mat, "spread_z"])
            direction, strength, confidence = _signal_strength_confidence(spread_sig, spread_z)
            signal_snapshot_rows.append(
                {
                    "timestamp": timestamp,
                    "signal_type": "spread",
                    "maturity_bucket": mat,
                    "direction": direction,
                    "strength": strength,
                    "confidence": confidence,
                }
            )
            if "cip_signal" in summary.columns:
                cip_sig = int(summary.loc[mat, "cip_signal"])
                cip_z = float(summary.loc[mat, "cip_z"])
                direction, strength, confidence = _signal_strength_confidence(cip_sig, cip_z)
                signal_snapshot_rows.append(
                    {
                        "timestamp": timestamp,
                        "signal_type": "cip",
                        "maturity_bucket": mat,
                        "direction": direction,
                        "strength": strength,
                        "confidence": confidence,
                    }
                )
    else:
        print("  No signals to display.")

    if factor_result.signals is not None and not factor_result.signals.empty:
        print(f"\n  Factor signals (latest):")
        print(f"    RU: {int(factor_result.latest.get('signal_RU', 0)):+d}   "
              f"CN: {int(factor_result.latest.get('signal_CN', 0)):+d}   "
              f"Divergence: {'YES' if factor_result.latest.get('divergence', 0) else 'no'}")
        for curve in ["RU", "CN"]:
            sig_col = f"signal_{curve}"
            z_col = f"z_{curve}_beta0"
            direction, strength, confidence = _signal_strength_confidence(
                int(factor_result.latest.get(sig_col, 0)),
                float(factor_result.latest.get(z_col, float("nan"))),
            )
            signal_snapshot_rows.append(
                {
                    "timestamp": timestamp,
                    "signal_type": "factor",
                    "maturity_bucket": curve,
                    "direction": direction,
                    "strength": strength,
                    "confidence": confidence,
                }
            )

    _section("SIGNAL STABILITY DIAGNOSTICS")
    diag_frames = []
    if not spread_result.signals.empty:
        sig_cols = [c for c in spread_result.signals.columns if c.startswith("signal_")]
        spread_diag = _compute_stability_diagnostics(spread_result.signals, sig_cols)
        if not spread_diag.empty:
            spread_diag["signal_type"] = "spread"
            diag_frames.append(spread_diag)
    if not cip_result_signals.empty:
        sig_cols = [c for c in cip_result_signals.columns if c.startswith("cip_signal_")]
        cip_diag = _compute_stability_diagnostics(cip_result_signals, sig_cols)
        if not cip_diag.empty:
            cip_diag["signal_type"] = "cip"
            diag_frames.append(cip_diag)
    if not factor_result.signals.empty:
        sig_cols = [c for c in ["signal_RU", "signal_CN"] if c in factor_result.signals.columns]
        factor_diag = _compute_stability_diagnostics(factor_result.signals, sig_cols)
        if not factor_diag.empty:
            factor_diag["signal_type"] = "factor"
            diag_frames.append(factor_diag)
    if diag_frames:
        diagnostics = pd.concat(diag_frames, ignore_index=True)
        print(diagnostics[["signal_type", "signal", "active_pct", "persistence", "flip_rate"]].to_string(index=False))
    else:
        diagnostics = pd.DataFrame()
        print("  No diagnostics available.")

    # ------------------------------------------------------------------
    # 5. Optional CSV export
    # ------------------------------------------------------------------
    if args.save_csv:
        frames = []
        if not spread_result.signals.empty:
            frames.append(spread_result.signals.add_prefix("spread_"))
        if not cip_result_signals.empty:
            frames.append(cip_result_signals)
        if not factor_result.signals.empty:
            frames.append(factor_result.signals)
        if frames:
            combined = pd.concat(frames, axis=1)
            out_path = Path(args.save_csv)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            combined.to_csv(out_path)
            print(_safe_console(f"\n  Signals saved -> {out_path}"))
            if signal_snapshot_rows:
                snapshot_df = pd.DataFrame(signal_snapshot_rows)
                snapshot_path = out_path.with_name(f"{out_path.stem}_snapshot.csv")
                snapshot_df.to_csv(snapshot_path, index=False)
                print(_safe_console(f"  Snapshot saved -> {snapshot_path}"))
            if not diagnostics.empty:
                diag_path = out_path.with_name(f"{out_path.stem}_diagnostics.csv")
                diagnostics.to_csv(diag_path, index=False)
                print(_safe_console(f"  Diagnostics saved -> {diag_path}"))

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

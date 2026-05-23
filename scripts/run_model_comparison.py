"""
Walk-forward model comparison: Random Walk vs NS-static vs DNS vs VAR.

For each test window step:
  1. Fit each model on the training window.
  2. Forecast 1 step ahead.
  3. Compare against realised yields.
  4. Print RMSE per maturity per model at the end.

Usage:
  python scripts/run_model_comparison.py
  python scripts/run_model_comparison.py --curve RU --horizon 1
  python scripts/run_model_comparison.py --curve CN --start-date 2020-01-01
  python scripts/run_model_comparison.py --curve both --train-window 60 --horizon 3
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forecasting.loaders import load_russian_yield_curve, load_chinese_yield_curve
from src.forecasting.ns_baseline import get_fitted_curves, _parse_maturity
from src.forecasting.regime_dns import fit_dns, forecast_dns
from src.forecasting.var_factors import fit_var, forecast_var
from src.forecasting.rw_benchmark import forecast_random_walk
from src.forecasting.pca_curves import fit_pca, forecast_pca
from src.forecasting.evaluate import summarize_rmse_table


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rmse(actual: pd.Series, predicted: pd.Series) -> float:
    common = actual.index.intersection(predicted.index)
    if common.empty:
        return np.nan
    diff = actual[common].astype(float) - predicted[common].astype(float)
    return float(np.sqrt(np.nanmean(diff ** 2)))


def _filter_sparse(yields_df: pd.DataFrame, min_maturities: int = 4) -> pd.DataFrame:
    """Drop rows with fewer than min_maturities non-null yield columns."""
    yield_cols = [c for c in yields_df.columns if _parse_maturity(c) is not None]
    mask = yields_df[yield_cols].notna().sum(axis=1) >= min_maturities
    filtered = yields_df[mask]
    dropped = len(yields_df) - len(filtered)
    if dropped:
        print(f"  [filter] Dropped {dropped} sparse rows (< {min_maturities} maturities). "
              f"{len(filtered)} usable rows remain.")
    return filtered


def _walk_forward_single(
    yields_df: pd.DataFrame,
    train_window: int,
    horizon: int,
    curve: str,  # 'ru' or 'cn'
    include_pca: bool = False,
    other_curve_df: pd.DataFrame = None,
) -> dict:
    """
    Walk-forward evaluation for RW, NS-static, and DNS on a single curve.
    Rows with fewer than 4 non-null maturities are dropped before evaluation.

    Returns:
        dict mapping model_name -> DataFrame of per-maturity RMSE.
    """
    yields_df = _filter_sparse(yields_df)
    yield_cols = [c for c in yields_df.columns if _parse_maturity(c) is not None]
    prefix = "RU_" if curve == 'ru' else "CN_"

    errors = {m: {'RW': [], 'NS_static': [], 'DNS': [], 'PCA': []} for m in yield_cols}

    n = len(yields_df)
    steps = 0

    for t in range(train_window, n - horizon):
        train = yields_df.iloc[t - train_window: t]
        actual_row = yields_df.iloc[t + horizon - 1]

        # --- Random Walk ---
        rw_fc = forecast_random_walk(train, horizon=horizon).iloc[-1]

        # --- NS static (last fitted curve as forecast) ---
        fitted_last = get_fitted_curves(train.iloc[[-1]])
        if not fitted_last.empty:
            ns_fc = fitted_last.iloc[0]
        else:
            ns_fc = train.iloc[-1]

        # --- DNS ---
        dns_model = fit_dns(train)
        if dns_model is not None:
            dns_fc_df = forecast_dns(dns_model, horizon=horizon)
            dns_fc = dns_fc_df.iloc[-1]
        else:
            dns_fc = rw_fc  # fallback to RW

        # --- PCA (optional baseline from joint curve only) ---
        pca_fc = rw_fc
        if include_pca and other_curve_df is not None and not other_curve_df.empty:
            other_train = other_curve_df.reindex(train.index).dropna(how="all")
            if not other_train.empty:
                if curve == 'ru':
                    pca_model = fit_pca(train, other_train)
                    if pca_model is not None:
                        pca_fc_dict = forecast_pca(pca_model, horizon=horizon)
                        if 'ru' in pca_fc_dict and not pca_fc_dict['ru'].empty:
                            pca_fc = pca_fc_dict['ru'].iloc[-1]
                else:
                    pca_model = fit_pca(other_train, train)
                    if pca_model is not None:
                        pca_fc_dict = forecast_pca(pca_model, horizon=horizon)
                        if 'cn' in pca_fc_dict and not pca_fc_dict['cn'].empty:
                            pca_fc = pca_fc_dict['cn'].iloc[-1]

        for col in yield_cols:
            actual_val = actual_row.get(col, np.nan)
            if pd.isna(actual_val):
                continue
            errors[col]['RW'].append((actual_val - rw_fc.get(col, np.nan)) ** 2)
            errors[col]['NS_static'].append((actual_val - ns_fc.get(col, np.nan)) ** 2)
            errors[col]['DNS'].append((actual_val - dns_fc.get(col, np.nan)) ** 2)
            errors[col]['PCA'].append((actual_val - pca_fc.get(col, np.nan)) ** 2)

        steps += 1

    if steps == 0:
        print(f"  [WARN] No walk-forward steps completed for {curve.upper()}.")
        return {}

    rmse_rows = []
    for col in yield_cols:
        row = {'maturity': col}
        for model in ['RW', 'NS_static', 'DNS', 'PCA']:
            vals = [v for v in errors[col][model] if not np.isnan(v)]
            row[model] = float(np.sqrt(np.mean(vals))) if vals else np.nan
        rmse_rows.append(row)

    return pd.DataFrame(rmse_rows).set_index('maturity')


def _walk_forward_var(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    train_window: int,
    horizon: int,
) -> dict:
    """
    Walk-forward evaluation for the joint VAR model.
    Returns dict with 'ru' and 'cn' DataFrames of per-maturity RMSE.
    """
    ru_cols = [c for c in ru_yields.columns if _parse_maturity(c) is not None]
    cn_cols = [c for c in cn_yields.columns if _parse_maturity(c) is not None]

    ru_err = {c: [] for c in ru_cols}
    cn_err = {c: [] for c in cn_cols}

    ru_yields = _filter_sparse(ru_yields)
    cn_yields = _filter_sparse(cn_yields)
    # Align on common dates (RU is now month-end so intersection works)
    joint_idx = ru_yields.index.intersection(cn_yields.index)
    ru_al = ru_yields.loc[joint_idx]
    cn_al = cn_yields.loc[joint_idx]
    n = len(joint_idx)

    for t in range(train_window, n - horizon):
        ru_train = ru_al.iloc[t - train_window: t]
        cn_train = cn_al.iloc[t - train_window: t]
        ru_actual = ru_al.iloc[t + horizon - 1]
        cn_actual = cn_al.iloc[t + horizon - 1]

        var_model = fit_var(ru_train, cn_train)
        if var_model is None:
            continue

        fc = forecast_var(var_model, horizon=horizon)
        ru_fc = fc['ru'].iloc[-1]
        cn_fc = fc['cn'].iloc[-1]

        for col in ru_cols:
            av = ru_actual.get(col, np.nan)
            pv = ru_fc.get(col, np.nan)
            if not (np.isnan(av) or np.isnan(pv)):
                ru_err[col].append((av - pv) ** 2)

        for col in cn_cols:
            av = cn_actual.get(col, np.nan)
            pv = cn_fc.get(col, np.nan)
            if not (np.isnan(av) or np.isnan(pv)):
                cn_err[col].append((av - pv) ** 2)

    def _to_rmse_df(err_dict):
        rows = [{'maturity': c, 'VAR': float(np.sqrt(np.mean(v))) if v else np.nan}
                for c, v in err_dict.items()]
        return pd.DataFrame(rows).set_index('maturity') if rows else pd.DataFrame()

    return {'ru': _to_rmse_df(ru_err), 'cn': _to_rmse_df(cn_err)}


def _print_comparison(single_rmse: pd.DataFrame, var_rmse: pd.DataFrame, curve: str):
    if single_rmse is None or single_rmse.empty:
        print(f"\n  No results for {curve.upper()}.")
        return
    combined = single_rmse.copy()
    if var_rmse is not None and not var_rmse.empty:
        combined = combined.join(var_rmse, how='left')
    print(f"\n{'='*65}")
    print(f"  RMSE COMPARISON — {curve.upper()} yield curve (h={args_global.horizon})")
    print(f"{'='*65}")
    print(combined.round(4).to_string())
    # Highlight best model per maturity
    model_cols = [c for c in combined.columns if c in ('RW', 'NS_static', 'DNS', 'VAR', 'PCA')]
    if model_cols:
        best = combined[model_cols].idxmin(axis=1)
        print(f"\n  Best model per maturity:")
        for mat, mdl in best.items():
            print(f"    {mat}: {mdl}")
        summary = summarize_rmse_table(combined, model_cols=model_cols)
        mean_rmse = summary.get("mean_rmse", {})
        if mean_rmse:
            print("\n  Mean RMSE by model:")
            for model in model_cols:
                if model in mean_rmse:
                    print(f"    {model}: {mean_rmse[model]:.4f}")


def _combine_results(single_rmse: pd.DataFrame, var_rmse: pd.DataFrame) -> pd.DataFrame:
    if single_rmse is None or single_rmse.empty:
        return pd.DataFrame()
    combined = single_rmse.copy()
    if var_rmse is not None and not var_rmse.empty:
        combined = combined.join(var_rmse, how="left")
    return combined


def _export_artifacts(
    ru_combined: pd.DataFrame,
    cn_combined: pd.DataFrame,
    export_prefix: Path,
):
    export_prefix.parent.mkdir(parents=True, exist_ok=True)

    if ru_combined is not None and not ru_combined.empty:
        ru_csv = export_prefix.with_name(f"{export_prefix.name}_ru.csv")
        ru_tex = export_prefix.with_name(f"{export_prefix.name}_ru.tex")
        ru_combined.round(4).to_csv(ru_csv)
        ru_latex = ru_combined.round(4).reset_index().to_latex(
            index=False,
            float_format="%.4f",
            caption="Out-of-sample RMSE comparison (RU curve)",
            label="tab:6_3_ru",
        )
        ru_tex.write_text(ru_latex, encoding="utf-8")

    if cn_combined is not None and not cn_combined.empty:
        cn_csv = export_prefix.with_name(f"{export_prefix.name}_cn.csv")
        cn_tex = export_prefix.with_name(f"{export_prefix.name}_cn.tex")
        cn_combined.round(4).to_csv(cn_csv)
        cn_latex = cn_combined.round(4).reset_index().to_latex(
            index=False,
            float_format="%.4f",
            caption="Out-of-sample RMSE comparison (CN curve)",
            label="tab:6_3_cn",
        )
        cn_tex.write_text(cn_latex, encoding="utf-8")

    # Compact best-model summary table (for direct report inclusion)
    rows = []
    for curve_name, df in [("RU", ru_combined), ("CN", cn_combined)]:
        if df is None or df.empty:
            continue
        model_cols = [c for c in ("RW", "NS_static", "DNS", "VAR", "PCA") if c in df.columns]
        if not model_cols:
            continue
        best = df[model_cols].idxmin(axis=1)
        for maturity, model in best.items():
            rows.append({"Curve": curve_name, "Maturity": maturity, "BestModel": model})
    if rows:
        summary_df = pd.DataFrame(rows)
        summary_csv = export_prefix.with_name(f"{export_prefix.name}_best_model.csv")
        summary_tex = export_prefix.with_name(f"{export_prefix.name}_best_model.tex")
        summary_df.to_csv(summary_csv, index=False)
        summary_latex = summary_df.to_latex(
            index=False,
            caption="Best out-of-sample model by maturity",
            label="tab:6_3_best",
        )
        summary_tex.write_text(summary_latex, encoding="utf-8")

    # Figure: average RMSE by model for RU/CN
    model_order = ["RW", "NS_static", "DNS", "VAR", "PCA"]
    fig_rows = []
    for curve_name, df in [("RU", ru_combined), ("CN", cn_combined)]:
        if df is None or df.empty:
            continue
        for model in model_order:
            if model in df.columns:
                fig_rows.append(
                    {"curve": curve_name, "model": model, "avg_rmse": float(df[model].mean(skipna=True))}
                )
    if fig_rows:
        fig_df = pd.DataFrame(fig_rows)
        pivot = fig_df.pivot(index="model", columns="curve", values="avg_rmse").reindex(model_order)
        ax = pivot.plot(kind="bar", figsize=(10, 5), rot=0)
        ax.set_title("Average OOS RMSE by model")
        ax.set_ylabel("RMSE")
        ax.grid(True, axis="y", alpha=0.3)
        fig_path = export_prefix.with_name(f"{export_prefix.name}_avg_rmse.png")
        plt.tight_layout()
        plt.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

args_global = None  # set in main for use in _print_comparison


def main():
    global args_global
    parser = argparse.ArgumentParser(description='Walk-forward model comparison')
    parser.add_argument('--curve', choices=['ru', 'cn', 'both'], default='both',
                        help='Which yield curve(s) to evaluate')
    parser.add_argument('--horizon', type=int, default=1,
                        help='Forecast horizon in periods (default 1)')
    parser.add_argument('--train-window', type=int, default=60,
                        help='Rolling training window size in periods (default 60)')
    parser.add_argument('--start-date', type=str, default=None,
                        help='Restrict data start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=None,
                        help='Restrict data end date (YYYY-MM-DD)')
    parser.add_argument(
        '--export-prefix',
        type=str,
        default=None,
        help='Optional prefix path for exporting result tables/figure '
             '(e.g. "project report/tables/tab_6_3_model_comparison")',
    )
    parser.add_argument(
        '--include-pca',
        action='store_true',
        help='Include PCA baseline in walk-forward comparison (slower).',
    )
    args = parser.parse_args()
    args_global = args

    print("Loading yield curves...")
    ru_yields = load_russian_yield_curve(args.start_date, args.end_date)
    cn_yields = load_chinese_yield_curve(args.start_date, args.end_date)

    if ru_yields.empty and cn_yields.empty:
        print("No yield data available. Run the pipeline first.")
        return 1

    print(f"  RU: {len(ru_yields)} observations, {list(ru_yields.columns)}")
    print(f"  CN: {len(cn_yields)} observations, {list(cn_yields.columns)}")
    print(f"\nWalk-forward params: train_window={args.train_window}, horizon={args.horizon}")

    run_ru = args.curve in ('ru', 'both') and not ru_yields.empty
    run_cn = args.curve in ('cn', 'both') and not cn_yields.empty
    run_var = args.curve == 'both' and not ru_yields.empty and not cn_yields.empty

    ru_single, cn_single, var_results = None, None, None

    if run_ru:
        print(f"\nEvaluating RU models (walk-forward)...")
        ru_single = _walk_forward_single(
            ru_yields, args.train_window, args.horizon, 'ru',
            include_pca=args.include_pca, other_curve_df=cn_yields
        )

    if run_cn:
        print(f"\nEvaluating CN models (walk-forward)...")
        cn_single = _walk_forward_single(
            cn_yields, args.train_window, args.horizon, 'cn',
            include_pca=args.include_pca, other_curve_df=ru_yields
        )

    if run_var:
        print(f"\nEvaluating joint VAR model (walk-forward)...")
        var_results = _walk_forward_var(ru_yields, cn_yields, args.train_window, args.horizon)

    # Print results
    if run_ru:
        var_ru = var_results['ru'] if var_results else None
        _print_comparison(ru_single, var_ru, 'ru')

    if run_cn:
        var_cn = var_results['cn'] if var_results else None
        _print_comparison(cn_single, var_cn, 'cn')

    if args.export_prefix:
        ru_combined = _combine_results(ru_single, var_results['ru'] if var_results else None)
        cn_combined = _combine_results(cn_single, var_results['cn'] if var_results else None)
        _export_artifacts(ru_combined, cn_combined, Path(args.export_prefix))
        print(f"\nExported artifacts with prefix: {args.export_prefix}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

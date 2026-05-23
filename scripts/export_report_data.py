"""
Export tables and figures for the coursework report.
====================================================

Run this script after the data pipeline has populated the database.
It executes the analysis logic, exports tables to LaTeX, and generates figures.

Usage:
    python scripts/export_report_data.py

Output:
    - project report/tables/*.tex  (LaTeX table fragments)
    - project report/graphics/*.png (figures)
"""

import os
import sys
import re
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# Use non-interactive backend for figure generation (no display)
import matplotlib
matplotlib.use('Agg')

TABLES_DIR = PROJECT_ROOT / "project report" / "tables"
GRAPHICS_DIR = PROJECT_ROOT / "project report" / "graphics"
TABLES_DIR.mkdir(parents=True, exist_ok=True)
GRAPHICS_DIR.mkdir(parents=True, exist_ok=True)


def to_month(df):
    """Normalise date to 1st-of-month."""
    import pandas as pd
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df['_m'] = df['date'].dt.to_period('M')
    df = df.sort_values('date').groupby('_m').last().reset_index()
    df['date'] = df['_m'].dt.to_timestamp()
    return df.drop(columns=['_m'])


def force_numeric(df):
    import pandas as pd
    df = df.copy()
    for c in df.columns:
        if c != 'date':
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def prep(df, cols=None):
    import pandas as pd
    if cols:
        cols = [c for c in cols if c in df.columns]
        df = df[cols]
    df = force_numeric(to_month(df))
    return df.dropna(axis=1, how='all')


def build_panel(db):
    """Build analysis panel from database (same logic as statistical_analysis.ipynb)."""
    import pandas as pd
    cbr_key = db.load_dataframe('cbr_key_rate')
    gcurve = db.load_dataframe('cbr_gcurve')
    fx = db.load_dataframe('currency_rates')
    ofz = db.load_dataframe('russian_bond_yields')
    ru_macro = db.load_dataframe('russian_macro')
    pboc = db.load_dataframe('pboc_lpr')
    cn_bonds = db.load_dataframe('chinese_bond_yields')
    glob_ind = db.load_dataframe('global_indicators')

    p_key = prep(cbr_key, ['date', 'cbr_key_rate'])
    p_gc = prep(gcurve, ['date', 'RU_1Y', 'RU_3Y', 'RU_5Y', 'RU_10Y'])
    p_fx = prep(fx, ['date', 'usd_rub', 'cny_rub'])
    ofz_cols = ['date'] + [c for c in ofz.columns if c.startswith('RU_')]
    p_ofz = prep(ofz, ofz_cols)
    p_ofz = p_ofz.rename(columns={c: f'OFZ_{c}' for c in p_ofz.columns if c.startswith('RU_')})
    lpr_cols = ['date'] + [c for c in pboc.columns if 'LPR' in c.upper()]
    p_lpr = prep(pboc, lpr_cols) if len(lpr_cols) > 1 else pd.DataFrame({'date': pd.Series(dtype='datetime64[ns]')})
    if not cn_bonds.empty:
        cn_cols = ['date'] + [c for c in cn_bonds.columns if c.startswith('CN_')]
        p_cn = prep(cn_bonds, cn_cols)
    else:
        p_cn = pd.DataFrame({'date': pd.Series(dtype='datetime64[ns]')})
    gi_cols = ['date', 'DGS10', 'DGS2', 'FEDFUNDS', 'DCOILBRENTEU', 'DTWEXBGS']
    p_gi = prep(glob_ind, gi_cols)
    ru_macro_cols = ['date'] + [c for c in ru_macro.columns if c != 'date']
    p_ru_macro = prep(ru_macro, ru_macro_cols) if not ru_macro.empty else pd.DataFrame({'date': pd.Series(dtype='datetime64[ns]')})

    frames = [p_key, p_gc, p_fx, p_ofz, p_lpr, p_cn, p_gi, p_ru_macro]
    panel = frames[0]
    for df in frames[1:]:
        if df.empty or 'date' not in df.columns or len(df.columns) <= 1:
            continue
        panel = panel.merge(df, on='date', how='outer')

    panel = panel.sort_values('date').reset_index(drop=True)
    panel = panel[(panel['date'] >= '2018-01-01') & (panel['date'] <= '2026-02-01')]
    panel = panel.dropna(axis=1, how='all')

    # Coalesce CN duplicates
    cn_dup = [c for c in panel.columns if c.startswith('CN_') and ('_x' in c or '_y' in c or c.endswith('_dup'))]
    if cn_dup:
        base_to_cols = {}
        for c in panel.columns:
            if not c.startswith('CN_'):
                continue
            base = re.sub(r'_(x|y|dup)$', '', c)
            base_to_cols.setdefault(base, []).append(c)
        for base, cols in base_to_cols.items():
            if len(cols) <= 1:
                continue
            first = base if base in cols else cols[0]
            panel[base] = panel[first].copy()
            for col in cols:
                if col != base:
                    panel[base] = panel[base].combine_first(panel[col])
            panel = panel.drop(columns=[c for c in cols if c != base])

    panel = panel.set_index('date')
    for c in panel.columns:
        panel[c] = pd.to_numeric(panel[c], errors='coerce')
    return panel


def run_statistical_analysis():
    """Run statistical analysis and export tables."""
    import pandas as pd
    import numpy as np
    from statsmodels.tsa.stattools import adfuller, coint, grangercausalitytests
    from statsmodels.tsa.vector_ar.var_model import VAR
    import statsmodels.api as sm

    from src.database import DatabaseManager

    db = DatabaseManager()
    panel = build_panel(db)
    if panel.empty:
        print("No panel data. Run pipeline first.")
        return

    # 1. Descriptive statistics
    def desc_row(s):
        valid = s.dropna()
        if len(valid) < 2:
            return None
        from scipy import stats as scipy_stats
        return {
            'mean': valid.mean(),
            'std': valid.std(),
            'min': valid.min(),
            'max': valid.max(),
            'skew': scipy_stats.skew(valid, nan_policy='omit'),
            'kurt': scipy_stats.kurtosis(valid, nan_policy='omit'),
        }
    desc_list = []
    for c in panel.columns:
        r = desc_row(panel[c])
        if r:
            r['variable'] = c
            desc_list.append(r)
    desc_df = pd.DataFrame(desc_list)
    if not desc_df.empty:
        tbl = desc_df[['variable', 'mean', 'std', 'min', 'max', 'skew', 'kurt']].head(15)
        latex = tbl.to_latex(index=False, float_format="%.3f", escape=False,
                             caption="Descriptive statistics (selected series)", label="tab:5_1")
        (TABLES_DIR / "tab_5_1_descriptive.tex").write_text(latex, encoding='utf-8')
        print("Exported tab_5_1_descriptive.tex")

    # 2. ADF
    def adf_summary(series, name):
        s = series.dropna()
        if len(s) < 10:
            return {'variable': name, 'n': len(s), 'adf_stat': np.nan, 'p_value': np.nan, 'stationary': 'N/A'}
        try:
            result = adfuller(s, autolag='AIC')
            stat = 'Yes' if result[1] < 0.05 else 'No'
            return {'variable': name, 'n': len(s), 'adf_stat': round(result[0], 4),
                    'p_value': round(result[1], 4), 'stationary': stat}
        except Exception:
            return {'variable': name, 'n': len(s), 'adf_stat': np.nan, 'p_value': np.nan, 'stationary': 'N/A'}

    adf_vars = ['cbr_key_rate', 'LPR1Y', 'LPR5Y', 'DGS10', 'DGS2', 'CN_10Y', 'OFZ_RU_10Y']
    adf_vars = [v for v in adf_vars if v in panel.columns]
    adf_results = []
    for v in adf_vars:
        adf_results.append(adf_summary(panel[v], v))
        d = panel[v].diff().dropna()
        adf_results.append(adf_summary(d, f'd({v})'))
    adf_df = pd.DataFrame(adf_results)
    levels = adf_df[~adf_df['variable'].str.startswith('d(')]
    if not levels.empty:
        latex = levels[['variable', 'adf_stat', 'p_value', 'stationary']].to_latex(
            index=False, float_format="%.4f", caption="ADF test (levels)", label="tab:5_2")
        (TABLES_DIR / "tab_5_2_adf.tex").write_text(latex, encoding='utf-8')
        print("Exported tab_5_2_adf.tex")

    # 3. Cointegration
    ru_vars = ['cbr_key_rate', 'OFZ_RU_10Y', 'OFZ_RU_5Y']
    partner_vars = ['LPR1Y', 'DGS10', 'CN_10Y']
    coint_pairs = []
    for ru in ru_vars:
        if ru not in panel.columns:
            continue
        for partner in partner_vars:
            if partner not in panel.columns:
                continue
            pair = panel[[ru, partner]].dropna()
            if len(pair) < 30:
                continue
            try:
                score, pval, _ = coint(pair[ru].values, pair[partner].values)
                coint_pairs.append({
                    'series_1': ru, 'series_2': partner, 'n': len(pair),
                    'test_stat': round(score, 4), 'p_value': round(pval, 4),
                    'cointegrated': 'Yes' if pval < 0.05 else 'No',
                })
            except Exception:
                pass
    coint_df = pd.DataFrame(coint_pairs)
    if not coint_df.empty:
        latex = coint_df.to_latex(index=False, float_format="%.4f", caption="Cointegration", label="tab:5_3")
        (TABLES_DIR / "tab_5_3_coint.tex").write_text(latex, encoding='utf-8')
        print("Exported tab_5_3_coint.tex")

    # 4. Granger
    def granger_test(data, col1, col2, max_lag=6):
        pair = data[[col1, col2]].dropna()
        if len(pair) < max_lag + 20:
            return None
        try:
            result = grangercausalitytests(pair.values, max_lag, verbose=False)
            best_p, best_lag = 1, 0
            for lag in range(1, max_lag + 1):
                p = result[lag][0]['ssr_ftest'][1]
                if p < best_p:
                    best_p, best_lag = p, lag
            return {'cause': col1, 'effect': col2, 'best_lag': best_lag, 'best_p': round(best_p, 4),
                    'significant': 'Yes' if best_p < 0.05 else 'No', 'n': len(pair)}
        except Exception:
            return None

    dpanel = panel.diff().dropna(how='all')
    granger_pairs = [('LPR1Y', 'cbr_key_rate'), ('DGS10', 'cbr_key_rate'), ('DCOILBRENTEU', 'cbr_key_rate')]
    granger_results = []
    for c1, c2 in granger_pairs:
        if c1 in dpanel.columns and c2 in dpanel.columns:
            r = granger_test(dpanel, c1, c2)
            if r:
                granger_results.append(r)
            r = granger_test(dpanel, c2, c1)
            if r:
                granger_results.append(r)
    granger_df = pd.DataFrame(granger_results)
    if not granger_df.empty:
        latex = granger_df[['cause', 'effect', 'best_lag', 'best_p', 'significant']].to_latex(
            index=False, float_format="%.4f", caption="Granger causality", label="tab:5_4")
        (TABLES_DIR / "tab_5_4_granger.tex").write_text(latex, encoding='utf-8')
        print("Exported tab_5_4_granger.tex")

    # 5. VAR
    var_cols = ['cbr_key_rate', 'LPR1Y', 'DGS10', 'DCOILBRENTEU', 'CN_10Y']
    var_cols = [c for c in var_cols if c in panel.columns]
    var_data = panel[var_cols].dropna()
    if len(var_data) > 30:
        try:
            model = VAR(var_data)
            lag_order = model.select_order(maxlags=8)
            best_lag = int(lag_order.aic) if pd.notna(lag_order.aic) else 1
            fitted = model.fit(best_lag)
            var_info = f"Variables: {', '.join(var_cols)}\nLag order (AIC): {best_lag}"
            (TABLES_DIR / "tab_5_5_var.txt").write_text(var_info, encoding='utf-8')
            var_df = pd.DataFrame(
                [{"Variables": ", ".join(var_cols), "AIC_lag": best_lag, "Observations": len(var_data)}]
            )
            var_latex = var_df.to_latex(index=False, caption="VAR model specification", label="tab:5_5")
            (TABLES_DIR / "tab_5_5_var.tex").write_text(var_latex, encoding='utf-8')
            print("Exported tab_5_5_var.txt")
            print("Exported tab_5_5_var.tex")
        except Exception as e:
            print(f"VAR failed: {e}")

    # 6. OLS
    ols_cols = ['LPR1Y', 'DGS10', 'FEDFUNDS', 'DCOILBRENTEU', 'usd_rub']
    ols_cols = [c for c in ols_cols if c in panel.columns]
    if ols_cols and 'cbr_key_rate' in panel.columns:
        reg_data = panel[['cbr_key_rate'] + ols_cols].dropna()
        if len(reg_data) > 20:
            y = reg_data['cbr_key_rate']
            X = sm.add_constant(reg_data[ols_cols])
            ols = sm.OLS(y, X).fit(cov_type='HC1')
            ols_df = pd.DataFrame({
                'Regressor': ['const'] + ols_cols + ['R2'],
                'Coef': [ols.params.get('const', np.nan)] + [ols.params.get(c, np.nan) for c in ols_cols] + [ols.rsquared],
                'Robust SE': [ols.bse.get('const', np.nan)] + [ols.bse.get(c, np.nan) for c in ols_cols] + [np.nan],
            })
            latex = ols_df.to_latex(index=False, float_format="%.4f", caption="OLS: CBR key rate", label="tab:5_6")
            (TABLES_DIR / "tab_5_6_ols.tex").write_text(latex, encoding='utf-8')
            print("Exported tab_5_6_ols.tex")


def run_yield_forecasting_export():
    """Export yield forecasting tables."""
    import pandas as pd
    from src.database import DatabaseManager
    from src.forecasting.loaders import load_russian_yield_curve, load_chinese_yield_curve
    from src.forecasting.ns_baseline import compute_residuals, get_fitted_curves
    from src.forecasting.cross_currency import build_spreads, flag_abnormal_spreads
    from src.forecasting.evaluate import evaluate_ns_fit, evaluate_spreads

    ru_yields = load_russian_yield_curve()
    cn_yields = load_chinese_yield_curve()

    # NS metrics
    rows = []
    for name, yields in [('RU', ru_yields), ('CN', cn_yields)]:
        if yields.empty:
            continue
        fitted = get_fitted_curves(yields)
        residuals = compute_residuals(yields)
        ev = evaluate_ns_fit(yields, fitted, residuals)
        for mat, d in ev.get('by_maturity', {}).items():
            rows.append({'Currency': name, 'Maturity': mat, 'MAE': d['MAE'], 'RMSE': d['RMSE']})
    if rows:
        ns_df = pd.DataFrame(rows)
        latex = ns_df.to_latex(index=False, float_format="%.4f", caption="NS fit metrics", label="tab:6_1")
        (TABLES_DIR / "tab_6_1_ns_metrics.tex").write_text(latex, encoding='utf-8')
        print("Exported tab_6_1_ns_metrics.tex")

    # Spreads and abnormal flags
    if not ru_yields.empty and not cn_yields.empty:
        spreads = build_spreads(ru_yields, cn_yields)
        flagged = flag_abnormal_spreads(spreads, z_threshold=2.0)
        ev = evaluate_spreads(spreads, flagged)
        ac = ev.get('abnormal_counts', {})
        if ac:
            # Clean names: spread_1Y_abnormal -> 1Y
            rows = [(k.replace('spread_', '').replace('_abnormal', ''), int(v)) for k, v in ac.items()]
            ab_df = pd.DataFrame(rows, columns=['Maturity', 'Count'])
            latex = ab_df.to_latex(index=False, caption="Abnormal spread flags (Z>2)", label="tab:6_2")
            (TABLES_DIR / "tab_6_2_abnormal.tex").write_text(latex, encoding='utf-8')
            print("Exported tab_6_2_abnormal.tex")


def run_figures():
    """Generate all report figures."""
    import pandas as pd
    import matplotlib.pyplot as plt
    import numpy as np
    try:
        import seaborn as sns
        sns.set_palette('deep')
        has_seaborn = True
    except ImportError:
        has_seaborn = False
    from src.database import DatabaseManager
    from src.forecasting.loaders import load_russian_yield_curve, load_chinese_yield_curve
    from src.forecasting.ns_baseline import compute_residuals, get_fitted_curves
    from src.forecasting.cross_currency import build_spreads

    try:
        plt.style.use('seaborn-v0_8-whitegrid')
    except OSError:
        plt.style.use('default')
    plt.rcParams['figure.figsize'] = (14, 5)
    plt.rcParams['figure.dpi'] = 100

    db = DatabaseManager()
    panel = build_panel(db)
    if panel.empty:
        print("No panel data for figures. Run pipeline first.")
        return

    # Fig 4.2: Russian rates (CBR + G-curve) and OFZ
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    ax = axes[0]
    if 'cbr_key_rate' in panel.columns:
        ax.plot(panel.index, panel['cbr_key_rate'].values, label='CBR Key Rate', lw=2)
    for c in ['RU_1Y', 'RU_3Y', 'RU_5Y', 'RU_10Y']:
        if c in panel.columns:
            ax.plot(panel.index, panel[c].values, label=c, alpha=0.8)
    ax.set_title('Russian Interest Rates (CBR Key Rate & G-Curve)')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    ax = axes[1]
    ofz_cols = sorted([c for c in panel.columns if c.startswith('OFZ_')])
    for col in ofz_cols[:7]:
        s = panel[col].dropna()
        if len(s) > 0:
            ax.plot(s.index, s.values, label=col.replace('OFZ_', ''), alpha=0.8)
    ax.set_title('OFZ Bond Yields by Maturity')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(GRAPHICS_DIR / 'fig_4_2_russian_rates.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("Saved fig_4_2_russian_rates.png")

    # Fig 4.3: LPR and FX
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    ax = axes[0]
    for col in [c for c in panel.columns if 'LPR' in c.upper()]:
        s = panel[col].dropna()
        if len(s) > 0:
            ax.plot(s.index, s.values, label=col, alpha=0.8)
    ax.set_title('Chinese Policy Rates (PBOC LPR)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax = axes[1]
    for col in ['usd_rub', 'cny_rub']:
        if col in panel.columns:
            ax.plot(panel.index, panel[col].values, label=col, alpha=0.8)
    ax.set_title('Exchange Rates')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(GRAPHICS_DIR / 'fig_4_3_lpr_fx.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("Saved fig_4_3_lpr_fx.png")

    # Fig 4.5: Chinese bonds
    cn_cols = sorted([c for c in panel.columns if c.startswith('CN_')])
    if cn_cols:
        fig, ax = plt.subplots(figsize=(14, 5))
        for col in cn_cols[:10]:
            s = panel[col].dropna()
            if len(s) > 0:
                ax.plot(s.index, s.values, label=col, alpha=0.8)
        ax.set_title('Chinese Sovereign Bond Yields by Maturity')
        ax.legend(ncol=3)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(GRAPHICS_DIR / 'fig_4_5_chinese_bonds.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("Saved fig_4_5_chinese_bonds.png")

    # Fig 4.7: US rates and Brent
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    ax = axes[0]
    for col in ['DGS10', 'DGS2', 'FEDFUNDS']:
        if col in panel.columns:
            ax.plot(panel.index, panel[col].values, label=col, alpha=0.8)
    ax.set_title('US Interest Rates')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax = axes[1]
    if 'DCOILBRENTEU' in panel.columns:
        ax.plot(panel.index, panel['DCOILBRENTEU'].values, label='Brent Crude (USD)', color='tab:brown', lw=1.5)
    ax.set_title('Brent Crude Oil')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(GRAPHICS_DIR / 'fig_4_7_global.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("Saved fig_4_7_global.png")

    # Fig 5.1: Correlation heatmap
    rate_vars = (['cbr_key_rate'] + [c for c in panel.columns if c.startswith('RU_') and not c.startswith('OFZ_')]
                 + sorted([c for c in panel.columns if c.startswith('OFZ_')])[:5]
                 + [c for c in panel.columns if 'LPR' in c.upper()]
                 + sorted([c for c in panel.columns if c.startswith('CN_')])[:5]
                 + [c for c in ['DGS10', 'FEDFUNDS', 'DCOILBRENTEU', 'usd_rub', 'cny_rub'] if c in panel.columns])
    rate_vars = [v for v in rate_vars if v in panel.columns][:20]
    sub = panel[rate_vars].dropna(thresh=min(10, len(rate_vars) - 2))
    if len(sub) > 5:
        corr = sub.corr()
        mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
        fig, ax = plt.subplots(figsize=(12, 10))
        if has_seaborn:
            sns.heatmap(corr, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r', center=0,
                        square=True, linewidths=0.5, cbar_kws={'shrink': 0.8})
        else:
            im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
            ax.set_xticks(range(len(corr.columns)))
            ax.set_yticks(range(len(corr.columns)))
            ax.set_xticklabels(corr.columns, rotation=45, ha='right')
            ax.set_yticklabels(corr.columns)
            for i in range(len(corr)):
                for j in range(len(corr)):
                    if i < j:
                        ax.text(j, i, f'{corr.iloc[i, j]:.2f}', ha='center', va='center', fontsize=8)
            plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title('Correlation Matrix: Key Rate Variables')
        plt.tight_layout()
        plt.savefig(GRAPHICS_DIR / 'fig_5_1_correlation.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("Saved fig_5_1_correlation.png")

    # Fig 5.2: VAR IRF
    var_cols = [c for c in ['cbr_key_rate', 'LPR1Y', 'DGS10', 'DCOILBRENTEU', 'CN_10Y'] if c in panel.columns]
    var_data = panel[var_cols].dropna()
    if len(var_data) > 30:
        try:
            from statsmodels.tsa.vector_ar.var_model import VAR
            model = VAR(var_data)
            lag_order = model.select_order(maxlags=8)
            best_lag = max(1, int(lag_order.aic) if pd.notna(lag_order.aic) else 1)
            fitted = model.fit(best_lag)
            irf = fitted.irf(12)
            fig = irf.plot(orth=False, figsize=(14, 10))
            plt.suptitle('Impulse Response Functions (12-month horizon)', y=1.02, fontsize=14)
            plt.tight_layout()
            plt.savefig(GRAPHICS_DIR / 'fig_5_2_irf.png', dpi=150, bbox_inches='tight')
            plt.close()
            print("Saved fig_5_2_irf.png")
        except Exception as e:
            print(f"VAR IRF figure skipped: {e}")

    # Fig 6.1: RUB-CNY spreads
    ru_yields = load_russian_yield_curve()
    cn_yields = load_chinese_yield_curve()
    if not ru_yields.empty and not cn_yields.empty:
        spreads = build_spreads(ru_yields, cn_yields)
        spread_cols = [c for c in spreads.columns if c.startswith('spread_')]
        if spread_cols:
            spreads[spread_cols].plot(figsize=(12, 5), title='RUB–CNY yield spreads by maturity')
            plt.tight_layout()
            plt.savefig(GRAPHICS_DIR / 'fig_6_1_spreads.png', dpi=150, bbox_inches='tight')
            plt.close()
            print("Saved fig_6_1_spreads.png")

    # Fig 6.2: NS residuals (RU)
    if not ru_yields.empty:
        ru_residuals = compute_residuals(ru_yields)
        valid = [c for c in ru_residuals.columns if ru_residuals[c].notna().any()]
        if valid:
            ru_residuals[valid].plot(figsize=(12, 5), title='RU Nelson-Siegel residuals by maturity', legend=True)
            plt.ylabel('Residual (pp)')
            plt.tight_layout()
            plt.savefig(GRAPHICS_DIR / 'fig_6_2_ns_residuals.png', dpi=150, bbox_inches='tight')
            plt.close()
            print("Saved fig_6_2_ns_residuals.png")


def run_model_comparison_export():
    """
    Run walk-forward model comparison and export report-ready artifacts.
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_model_comparison.py"),
        "--curve", "both",
        "--horizon", "1",
        "--train-window", "60",
        "--export-prefix",
        str(TABLES_DIR / "tab_6_3_model_comparison"),
    ]
    print("\nRunning out-of-sample model comparison export...")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print("Model comparison export failed:")
        print(proc.stderr or proc.stdout)
        return
    print("Exported model comparison tables/figure (tab_6_3_*)")


def run_portfolio_backtest_export():
    """
    Run simple constrained portfolio backtest and export summary CSV.
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_portfolio_backtest.py"),
    ]
    print("\nRunning portfolio backtest export...")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print("Portfolio backtest export failed:")
        print(proc.stderr or proc.stdout)
        return
    print("Exported portfolio summary to data/processed/portfolio_backtest_summary.csv")


def run_advanced_comparison_export():
    """
    Run advanced-method comparison (AER proxy + regime DNS) and export report table.
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_advanced_comparison.py"),
        "--output-prefix",
        str(TABLES_DIR / "tab_6_4_advanced_methods"),
    ]
    print("\nRunning advanced-method comparison export...")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print("Advanced comparison export failed:")
        print(proc.stderr or proc.stdout)
        return
    print("Exported advanced comparison table (tab_6_4_advanced_methods.*)")


def run_ml_signals_export():
    """
    Run ML signal generation + ML backtest exports.
    """
    sig_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_ml_signals.py"),
        "--save-prefix",
        str(PROJECT_ROOT / "data" / "processed" / "ml_signals"),
    ]
    print("\nRunning ML signal export...")
    proc = subprocess.run(sig_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print("ML signal export failed:")
        print(proc.stderr or proc.stdout)
        return
    print("Exported ML signals to data/processed/ml_signals*.csv")

    bt_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_ml_backtest.py"),
    ]
    print("Running ML backtest export...")
    proc = subprocess.run(bt_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print("ML backtest export failed:")
        print(proc.stderr or proc.stdout)
        return
    print("Exported ML backtest summary to data/processed/ml_backtest_summary.csv")


def main():
    import pandas as pd
    import argparse
    parser = argparse.ArgumentParser(description="Export report data and figures")
    parser.add_argument(
        "--with-model-comparison",
        action="store_true",
        help="Also run walk-forward model comparison export for section 6 artifacts",
    )
    parser.add_argument(
        "--with-portfolio-backtest",
        action="store_true",
        help="Also run portfolio/risk backtest summary export",
    )
    parser.add_argument(
        "--with-advanced-comparison",
        action="store_true",
        help="Also run advanced-method comparison export (AER proxy + regime DNS)",
    )
    parser.add_argument(
        "--with-ml-signals",
        action="store_true",
        help="Also run ML signal + ML backtest exports",
    )
    args = parser.parse_args()

    print("Exporting report tables...")
    run_statistical_analysis()
    run_yield_forecasting_export()
    if args.with_model_comparison:
        run_model_comparison_export()
    if args.with_portfolio_backtest:
        run_portfolio_backtest_export()
    if args.with_advanced_comparison:
        run_advanced_comparison_export()
    if args.with_ml_signals:
        run_ml_signals_export()
    print("\nGenerating figures...")
    run_figures()
    print("\nDone. Tables in project report/tables/, figures in project report/graphics/")


if __name__ == "__main__":
    main()

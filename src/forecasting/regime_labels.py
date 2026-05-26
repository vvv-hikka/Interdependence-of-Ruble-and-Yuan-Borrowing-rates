"""
Monthly regime label builder for strategy routing/evaluation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression


def _expanding_median(series: pd.Series, min_periods: int = 24) -> pd.Series:
    return series.expanding(min_periods=min_periods).median()


def _rolling_z(series: pd.Series, window: int = 12, min_periods: int = 6) -> pd.Series:
    m = series.rolling(window, min_periods=min_periods).mean()
    s = series.rolling(window, min_periods=min_periods).std().replace(0.0, np.nan)
    return (series - m) / s


def build_regime_frame(
    ru: pd.DataFrame,
    cn: pd.DataFrame,
    macro: pd.DataFrame | None = None,
    fx: pd.DataFrame | None = None,
    min_history: int = 24,
    persistence_months: int = 2,
) -> pd.DataFrame:
    """
    Build regime feature frame at monthly frequency.
    """
    if ru.empty or cn.empty:
        return pd.DataFrame()
    common = ru.index.intersection(cn.index)
    if common.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=common)
    ru10 = "RU_10Y" if "RU_10Y" in ru.columns else ru.columns[0]
    cn10 = "CN_10Y" if "CN_10Y" in cn.columns else cn.columns[0]
    ru2 = "RU_2Y" if "RU_2Y" in ru.columns else ru10
    cn2 = "CN_2Y" if "CN_2Y" in cn.columns else cn10

    out["spread_10"] = ru.loc[common, ru10].astype(float) - cn.loc[common, cn10].astype(float)
    out["spread_z12"] = _rolling_z(out["spread_10"], window=12, min_periods=6)
    out["slope_diff"] = (
        (ru.loc[common, ru10].astype(float) - ru.loc[common, ru2].astype(float))
        - (cn.loc[common, cn10].astype(float) - cn.loc[common, cn2].astype(float))
    )

    if macro is not None and not macro.empty:
        m = macro.copy()
        m.index = pd.to_datetime(m.index)
        m = m.reindex(common)
        out["dgs10"] = pd.to_numeric(m.get("global_indicators_DGS10"), errors="coerce")
        out["fedfunds"] = pd.to_numeric(m.get("global_indicators_FEDFUNDS"), errors="coerce")
        out["brent"] = pd.to_numeric(m.get("global_indicators_DCOILBRENTEU"), errors="coerce")
    else:
        out["dgs10"] = np.nan
        out["fedfunds"] = np.nan
        out["brent"] = np.nan

    if fx is not None and not fx.empty and "cny_rub" in fx.columns:
        f = fx.copy()
        f.index = pd.to_datetime(f.index)
        f = f.reindex(common)
        out["fx_chg3"] = np.log(pd.to_numeric(f["cny_rub"], errors="coerce")).diff(3) * 100.0
    else:
        out["fx_chg3"] = np.nan

    out["spread_med"] = _expanding_median(out["spread_10"], min_periods=min_history)
    out["slope_med"] = _expanding_median(out["slope_diff"], min_periods=min_history)
    out["dgs10_med"] = _expanding_median(out["dgs10"], min_periods=min_history)
    out["fx_chg3_med"] = _expanding_median(out["fx_chg3"], min_periods=min_history)

    out["regime_R1"] = np.where(
        out["spread_med"].isna(), "other",
        np.where(out["spread_10"] >= out["spread_med"], "R1_high_spread", "R1_low_spread")
    )
    out["regime_R3"] = np.where(
        out["spread_z12"].abs() > 2.0, "R3_extreme", "R3_normal"
    )
    out["regime_R4"] = np.where(
        out["slope_med"].isna(), "other",
        np.where(out["slope_diff"] > out["slope_med"], "R4_ru_steep", "R4_cn_steep")
    )
    out["regime_M1"] = np.where(
        out["dgs10_med"].isna(), "other",
        np.where(out["dgs10"] >= out["dgs10_med"], "M1_high_rates", "M1_low_rates")
    )
    out["regime_M5"] = np.where(
        out["fx_chg3_med"].isna(), "other",
        np.where(out["fx_chg3"] >= out["fx_chg3_med"], "M5_rub_weak", "M5_rub_strong")
    )
    out["regime_C1"] = np.where(
        out["regime_M1"] == "other", "other",
        np.where(
            (out["regime_M1"] == "M1_high_rates") & (out["regime_R3"] == "R3_extreme"),
            "C1_macro_tight_stress",
            np.where(
                out["regime_M1"] == "M1_high_rates",
                "C1_macro_tight_calm",
                "C1_macro_loose",
            ),
        ),
    )

    # Markov-switching smoother on spread changes (fallback-safe).
    out["ms_prob_low"] = np.nan
    out["ms_prob_high"] = np.nan
    out["ms_state"] = "other"
    out["ms_state_persist"] = "other"
    valid = out["spread_10"].diff().dropna()
    if len(valid) >= 36:
        try:
            ms = MarkovRegression(valid, k_regimes=2, trend="c", switching_variance=True)
            fit = ms.fit(disp=False)
            smp = fit.smoothed_marginal_probabilities
            p0 = smp.iloc[:, 0].reindex(out.index).fillna(method="ffill")
            p1 = smp.iloc[:, 1].reindex(out.index).fillna(method="ffill")
            out["ms_prob_low"] = p0
            out["ms_prob_high"] = p1
            out["ms_state"] = np.where(p1 >= 0.5, "MS_high", "MS_low")

            # Persistence filter: state switch only after repeated confirmation.
            raw = out["ms_state"].fillna("other").tolist()
            persisted = []
            current = raw[0] if raw else "other"
            streak = 1
            persisted.append(current if raw else "other")
            for i in range(1, len(raw)):
                if raw[i] == current:
                    streak = 1
                    persisted.append(current)
                    continue
                if i > 0 and raw[i] == raw[i - 1]:
                    streak += 1
                else:
                    streak = 1
                if streak >= max(2, persistence_months):
                    current = raw[i]
                    streak = 1
                persisted.append(current)
            out["ms_state_persist"] = persisted
        except Exception:
            pass

    # Causal regime usage in trading: use t-1 label for month t.
    for col in ["regime_R1", "regime_R3", "regime_R4", "regime_M1", "regime_M5", "regime_C1", "ms_state", "ms_state_persist"]:
        out[f"{col}_lag1"] = out[col].shift(1).fillna("other")

    return out


def regime_counts_table(regime_df: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten counts for all regime label columns.
    """
    rows = []
    label_cols = [c for c in regime_df.columns if c.startswith("regime_") and c.endswith("_lag1")]
    for c in label_cols:
        vc = regime_df[c].value_counts(dropna=False)
        rid = c.replace("_lag1", "")
        for cell, n in vc.items():
            rows.append({"regime_id": rid, "regime_cell": str(cell), "n_obs": int(n)})
    return pd.DataFrame(rows)

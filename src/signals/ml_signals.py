"""
ML-based arbitrage signal generation for RU/CN rates.

The module builds a monthly binary classification task:
  target_t = sign( (RU_duration_return - CN_duration_return) at t+1 )

Signals are generated with walk-forward training to avoid look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import RidgeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV

from src.signals.labeling import (
    TripleBarrierConfig,
    triple_barrier_labels,
    make_meta_direction_targets,
    purged_embargo_splits,
)


@dataclass
class MLSignalResult:
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    latest: pd.Series = field(default_factory=pd.Series)
    diagnostics: pd.DataFrame = field(default_factory=pd.DataFrame)
    reliability: pd.DataFrame = field(default_factory=pd.DataFrame)
    stability: pd.DataFrame = field(default_factory=pd.DataFrame)


def _pick_col(df: pd.DataFrame, preferred: str, fallback_prefix: str) -> str | None:
    if preferred in df.columns:
        return preferred
    cols = [c for c in df.columns if c.startswith(fallback_prefix)]
    return cols[0] if cols else None


def _prepare_training_frame(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    fx_rates: pd.DataFrame | None = None,
    extra_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    ru_col_10 = _pick_col(ru_yields, "RU_10Y", "RU_")
    cn_col_10 = _pick_col(cn_yields, "CN_10Y", "CN_")
    ru_col_2 = _pick_col(ru_yields, "RU_2Y", "RU_")
    cn_col_2 = _pick_col(cn_yields, "CN_2Y", "CN_")
    if ru_col_10 is None or cn_col_10 is None:
        return pd.DataFrame()

    common = ru_yields.index.intersection(cn_yields.index)
    if common.empty:
        return pd.DataFrame()

    frame = pd.DataFrame(index=common)
    frame["ru10"] = ru_yields.loc[common, ru_col_10].astype(float)
    frame["cn10"] = cn_yields.loc[common, cn_col_10].astype(float)
    frame["spread_10"] = frame["ru10"] - frame["cn10"]
    frame["spread_10_diff1"] = frame["spread_10"].diff()
    frame["spread_10_diff3"] = frame["spread_10"] - frame["spread_10"].shift(3)

    if ru_col_2 is not None and cn_col_2 is not None:
        frame["ru_slope"] = frame["ru10"] - ru_yields.loc[common, ru_col_2].astype(float)
        frame["cn_slope"] = frame["cn10"] - cn_yields.loc[common, cn_col_2].astype(float)
        frame["slope_diff"] = frame["ru_slope"] - frame["cn_slope"]
    else:
        frame["ru_slope"] = np.nan
        frame["cn_slope"] = np.nan
        frame["slope_diff"] = np.nan

    frame["ret_ru"] = -frame["ru10"].diff() / 100.0
    frame["ret_cn"] = -frame["cn10"].diff() / 100.0
    frame["ret_diff"] = frame["ret_ru"] - frame["ret_cn"]
    frame["ret_diff_lag1"] = frame["ret_diff"].shift(1)
    frame["ret_diff_lag3"] = frame["ret_diff"].rolling(3, min_periods=1).mean().shift(1)

    if fx_rates is not None and not fx_rates.empty and "cny_rub" in fx_rates.columns:
        fx = fx_rates.copy()
        fx = fx[~fx.index.duplicated(keep="last")]
        fx = fx.reindex(common).sort_index()
        frame["fx_chg1"] = np.log(fx["cny_rub"]).diff() * 100.0
        frame["fx_chg3"] = np.log(fx["cny_rub"]).diff(3) * 100.0
    else:
        frame["fx_chg1"] = np.nan
        frame["fx_chg3"] = np.nan

    # Stage-2 relative-value/carry + stress interactions
    frame["curvature_proxy"] = (
        frame["spread_10"] - 2.0 * ((frame["ru10"] - frame["cn10"]) - frame["slope_diff"].fillna(0.0))
    )
    frame["carry_proxy"] = frame["spread_10"].shift(1)
    frame["roll_down_proxy"] = frame["slope_diff"].shift(1)
    frame["oil_shock_1m"] = np.nan
    frame["risk_stress_proxy"] = np.nan
    if extra_features is not None and not extra_features.empty:
        ef = extra_features.copy()
        ef.index = pd.to_datetime(ef.index)
        ef = ef.reindex(common)
        if "global_indicators_DCOILBRENTEU" in ef.columns:
            oil = pd.to_numeric(ef["global_indicators_DCOILBRENTEU"], errors="coerce")
            frame["oil_shock_1m"] = np.log(oil).diff() * 100.0
        if "global_indicators_DTWEXBGS" in ef.columns:
            dxy = pd.to_numeric(ef["global_indicators_DTWEXBGS"], errors="coerce")
            frame["risk_stress_proxy"] = dxy.pct_change() * 100.0

    tb = triple_barrier_labels(frame["ret_diff"], TripleBarrierConfig())
    targets = make_meta_direction_targets(tb)
    frame = frame.join(tb[["tb_label", "tb_event_horizon", "is_opportunity", "direction_conditional"]], how="left")
    frame = frame.join(targets, how="left")
    return frame


def _reliability_bins(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 5) -> pd.DataFrame:
    if len(y_true) == 0:
        return pd.DataFrame()
    b = pd.DataFrame({"y": y_true, "p": proba})
    b["bin"] = pd.cut(b["p"], bins=np.linspace(0, 1, n_bins + 1), include_lowest=True, duplicates="drop")
    g = b.groupby("bin", observed=False).agg(
        n_obs=("y", "size"),
        p_mean=("p", "mean"),
        y_rate=("y", "mean"),
    ).reset_index()
    g["calibration_gap"] = (g["p_mean"] - g["y_rate"]).abs()
    g["bin"] = g["bin"].astype(str)
    return g


def _stability_grid(pred_df: pd.DataFrame) -> pd.DataFrame:
    if pred_df.empty:
        return pd.DataFrame()
    rows = []
    grids = [(0.55, 0.45), (0.60, 0.40), (0.65, 0.35)]
    for long_t, short_t in grids:
        sig = np.where(pred_df["proba_ensemble"] >= long_t, 1, np.where(pred_df["proba_ensemble"] <= short_t, -1, 0))
        active = float((sig != 0).mean())
        flips = float(np.mean(np.abs(np.diff(sig)))) if len(sig) > 1 else 0.0
        rows.append(
            {
                "prob_long": long_t,
                "prob_short": short_t,
                "active_pct": round(active, 6),
                "flip_proxy": round(flips, 6),
            }
        )
    return pd.DataFrame(rows)


def generate_ml_signals(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    fx_rates: pd.DataFrame | None = None,
    min_train: int = 48,
    prob_long: float = 0.55,
    prob_short: float = 0.45,
    n_cv_splits: int = 5,
    embargo: int = 1,
    extra_features: pd.DataFrame | None = None,
) -> MLSignalResult:
    frame = _prepare_training_frame(ru_yields, cn_yields, fx_rates, extra_features=extra_features)
    if frame.empty:
        return MLSignalResult()

    feature_cols = [
        "spread_10",
        "spread_10_diff1",
        "spread_10_diff3",
        "ru_slope",
        "cn_slope",
        "slope_diff",
        "ret_diff_lag1",
        "ret_diff_lag3",
        "fx_chg1",
        "fx_chg3",
        "curvature_proxy",
        "carry_proxy",
        "roll_down_proxy",
        "oil_shock_1m",
        "risk_stress_proxy",
    ]
    model_cols = ["proba_logit", "proba_rf", "proba_ridge", "proba_hgb", "proba_ensemble"]
    preds: List[Dict] = []

    clean = frame.copy()
    clean[feature_cols] = clean[feature_cols].replace([np.inf, -np.inf], np.nan)
    clean = clean.dropna(subset=feature_cols + ["target_opportunity"])
    if len(clean) <= min_train:
        return MLSignalResult()

    for i in range(min_train, len(clean)):
        train = clean.iloc[:i]
        test = clean.iloc[i : i + 1]
        x_train = train[feature_cols].values
        train_dir = train.dropna(subset=["target_direction"])
        y_train = train_dir["target_direction"].astype(int).values if not train_dir.empty else np.array([], dtype=int)
        y_train_meta = train["target_opportunity"].astype(int).values
        x_train_dir = train_dir[feature_cols].values if not train_dir.empty else np.empty((0, len(feature_cols)))
        x_test = test[feature_cols].values

        # If training labels are one-sided, avoid model failure.
        if len(y_train) == 0 or len(np.unique(y_train)) < 2:
            p_logit = float(np.mean(y_train)) if len(y_train) else 0.5
            p_rf = p_logit
            p_ridge = p_logit
            p_hgb = p_logit
        else:
            if len(np.unique(y_train_meta)) < 2:
                p_meta = float(np.mean(y_train_meta))
            else:
                meta = LogisticRegression(max_iter=1000, class_weight="balanced")
                meta.fit(x_train, y_train_meta)
                p_meta = float(meta.predict_proba(x_test)[0, 1])

            logit = LogisticRegression(max_iter=1000, class_weight="balanced")
            logit.fit(x_train_dir, y_train)
            p_logit = float(logit.predict_proba(x_test)[0, 1])

            rf = RandomForestClassifier(
                n_estimators=300,
                random_state=42,
                min_samples_leaf=3,
                class_weight="balanced_subsample",
            )
            rf.fit(x_train_dir, y_train)
            p_rf = float(rf.predict_proba(x_test)[0, 1])

            ridge_base = RidgeClassifier(alpha=1.0)
            ridge = CalibratedClassifierCV(ridge_base, cv=3, method="sigmoid")
            ridge.fit(x_train_dir, y_train)
            p_ridge = float(ridge.predict_proba(x_test)[0, 1])

            hgb = HistGradientBoostingClassifier(
                max_depth=2,
                max_leaf_nodes=8,
                min_samples_leaf=5,
                learning_rate=0.05,
                random_state=42,
                early_stopping=True,
            )
            hgb.fit(x_train_dir, y_train)
            p_hgb = float(hgb.predict_proba(x_test)[0, 1])

        p_ens = 0.25 * (p_logit + p_rf + p_ridge + p_hgb)
        p_trade = p_meta if "p_meta" in locals() else float(np.mean(y_train_meta))
        p_dir = p_ens
        p_final_long = p_trade * p_dir
        p_final_short = p_trade * (1.0 - p_dir)
        if p_final_long >= prob_long:
            signal = 1
        elif p_final_short >= (1.0 - prob_short):
            signal = -1
        else:
            signal = 0
        model_probas = {
            "ML_LOGIT": p_logit,
            "ML_RF": p_rf,
            "ML_RIDGE": p_ridge,
            "ML_HGB": p_hgb,
        }
        best_model = max(model_probas, key=model_probas.get)
        strength = abs(p_ens - 0.5) * 2.0
        preds.append(
            {
                "date": test.index[0],
                "y_true_direction": test["target_direction"].iloc[0],
                "y_true_opportunity": int(test["target_opportunity"].iloc[0]),
                "proba_logit": round(p_logit, 6),
                "proba_rf": round(p_rf, 6),
                "proba_ridge": round(p_ridge, 6),
                "proba_hgb": round(p_hgb, 6),
                "proba_ensemble": round(p_ens, 6),
                "proba_opportunity": round(float(p_trade), 6),
                "proba_final_long": round(float(p_final_long), 6),
                "proba_final_short": round(float(p_final_short), 6),
                "ml_signal": int(signal),
                "direction": int(signal),
                "strength": round(float(strength), 6),
                "confidence": round(float(strength), 6),
                "best_model": best_model,
                "model_proba_max": round(float(model_probas[best_model]), 6),
                "label_method": "triple_barrier_meta",
                "cv_scheme": f"purged_embargo_{n_cv_splits}x_emb{embargo}",
            }
        )

    pred_df = pd.DataFrame(preds).set_index("date").sort_index()
    if pred_df.empty:
        return MLSignalResult()

    dir_eval = pred_df.dropna(subset=["y_true_direction"]).copy()
    y_true = dir_eval["y_true_direction"].astype(int).values
    y_true_opp = pred_df["y_true_opportunity"].astype(int).values
    y_hat = (dir_eval["proba_ensemble"] >= 0.5).astype(int).values if not dir_eval.empty else np.array([], dtype=int)
    proba = dir_eval["proba_ensemble"].values if not dir_eval.empty else np.array([], dtype=float)
    proba_opp = pred_df["proba_opportunity"].values
    trade_mask = pred_df["ml_signal"] != 0
    directional_correct = np.nan
    if trade_mask.any():
        active_eval = pred_df.loc[trade_mask].dropna(subset=["y_true_direction"])
        if not active_eval.empty:
            signed_true = np.where(active_eval["y_true_direction"].values == 1, 1, -1)
            signed_pred = active_eval["ml_signal"].values
            directional_correct = float((signed_true == signed_pred).mean())

    diag_rows = [
        {"metric": "n_predictions", "value": float(len(pred_df))},
        {"metric": "trade_rate", "value": float(trade_mask.mean())},
        {"metric": "brier_direction", "value": float(brier_score_loss(y_true, proba)) if len(y_true) else np.nan},
        {"metric": "brier_opportunity", "value": float(brier_score_loss(y_true_opp, proba_opp))},
        {"metric": "accuracy", "value": float(accuracy_score(y_true, y_hat)) if len(y_true) else np.nan},
        {"metric": "precision", "value": float(precision_score(y_true, y_hat, zero_division=0)) if len(y_true) else np.nan},
        {"metric": "recall", "value": float(recall_score(y_true, y_hat, zero_division=0)) if len(y_true) else np.nan},
        {"metric": "f1", "value": float(f1_score(y_true, y_hat, zero_division=0)) if len(y_true) else np.nan},
        {"metric": "roc_auc", "value": float(roc_auc_score(y_true, proba)) if len(y_true) and len(np.unique(y_true)) > 1 else np.nan},
        {"metric": "directional_hit_when_active", "value": directional_correct},
    ]
    for c in model_cols:
        diag_rows.append({"metric": f"{c}_mean", "value": float(pred_df[c].mean())})
    splits = purged_embargo_splits(len(pred_df), n_splits=n_cv_splits, embargo=embargo)
    diag_rows.append({"metric": "cv_n_splits", "value": float(len(splits))})
    diag_rows.append({"metric": "cv_embargo", "value": float(embargo)})

    diag_df = pd.DataFrame(diag_rows)
    rel = _reliability_bins(y_true, proba, n_bins=5)
    st = _stability_grid(pred_df)
    latest = pred_df.iloc[-1]
    return MLSignalResult(predictions=pred_df, latest=latest, diagnostics=diag_df, reliability=rel, stability=st)

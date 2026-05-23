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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score


@dataclass
class MLSignalResult:
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    latest: pd.Series = field(default_factory=pd.Series)
    diagnostics: pd.DataFrame = field(default_factory=pd.DataFrame)


def _pick_col(df: pd.DataFrame, preferred: str, fallback_prefix: str) -> str | None:
    if preferred in df.columns:
        return preferred
    cols = [c for c in df.columns if c.startswith(fallback_prefix)]
    return cols[0] if cols else None


def _prepare_training_frame(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    fx_rates: pd.DataFrame | None = None,
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

    frame["target"] = np.sign(frame["ret_diff"].shift(-1)).replace(0.0, np.nan)
    frame["target"] = (frame["target"] > 0).astype(float)
    return frame


def generate_ml_signals(
    ru_yields: pd.DataFrame,
    cn_yields: pd.DataFrame,
    fx_rates: pd.DataFrame | None = None,
    min_train: int = 48,
    prob_long: float = 0.55,
    prob_short: float = 0.45,
) -> MLSignalResult:
    frame = _prepare_training_frame(ru_yields, cn_yields, fx_rates)
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
    ]
    model_cols = ["proba_logit", "proba_rf", "proba_ensemble"]
    preds: List[Dict] = []

    clean = frame.copy()
    clean[feature_cols] = clean[feature_cols].replace([np.inf, -np.inf], np.nan)
    clean = clean.dropna(subset=feature_cols + ["target"])
    if len(clean) <= min_train:
        return MLSignalResult()

    for i in range(min_train, len(clean)):
        train = clean.iloc[:i]
        test = clean.iloc[i : i + 1]
        x_train = train[feature_cols].values
        y_train = train["target"].astype(int).values
        x_test = test[feature_cols].values

        # If training labels are one-sided, avoid model failure.
        if len(np.unique(y_train)) < 2:
            p_logit = float(np.mean(y_train))
            p_rf = p_logit
        else:
            logit = LogisticRegression(max_iter=1000, class_weight="balanced")
            logit.fit(x_train, y_train)
            p_logit = float(logit.predict_proba(x_test)[0, 1])

            rf = RandomForestClassifier(
                n_estimators=300,
                random_state=42,
                min_samples_leaf=3,
                class_weight="balanced_subsample",
            )
            rf.fit(x_train, y_train)
            p_rf = float(rf.predict_proba(x_test)[0, 1])

        p_ens = 0.5 * (p_logit + p_rf)
        if p_ens >= prob_long:
            signal = 1
        elif p_ens <= prob_short:
            signal = -1
        else:
            signal = 0
        strength = abs(p_ens - 0.5) * 2.0
        preds.append(
            {
                "date": test.index[0],
                "y_true": int(test["target"].iloc[0]),
                "proba_logit": round(p_logit, 6),
                "proba_rf": round(p_rf, 6),
                "proba_ensemble": round(p_ens, 6),
                "ml_signal": int(signal),
                "direction": int(signal),
                "strength": round(float(strength), 6),
                "confidence": round(float(strength), 6),
            }
        )

    pred_df = pd.DataFrame(preds).set_index("date").sort_index()
    if pred_df.empty:
        return MLSignalResult()

    y_true = pred_df["y_true"].astype(int).values
    y_hat = (pred_df["proba_ensemble"] >= 0.5).astype(int).values
    proba = pred_df["proba_ensemble"].values
    trade_mask = pred_df["ml_signal"] != 0
    directional_correct = np.nan
    if trade_mask.any():
        signed_true = np.where(pred_df.loc[trade_mask, "y_true"].values == 1, 1, -1)
        signed_pred = pred_df.loc[trade_mask, "ml_signal"].values
        directional_correct = float((signed_true == signed_pred).mean())

    diag_rows = [
        {"metric": "n_predictions", "value": float(len(pred_df))},
        {"metric": "trade_rate", "value": float(trade_mask.mean())},
        {"metric": "accuracy", "value": float(accuracy_score(y_true, y_hat))},
        {"metric": "precision", "value": float(precision_score(y_true, y_hat, zero_division=0))},
        {"metric": "recall", "value": float(recall_score(y_true, y_hat, zero_division=0))},
        {"metric": "f1", "value": float(f1_score(y_true, y_hat, zero_division=0))},
        {"metric": "roc_auc", "value": float(roc_auc_score(y_true, proba)) if len(np.unique(y_true)) > 1 else np.nan},
        {"metric": "directional_hit_when_active", "value": directional_correct},
    ]
    for c in model_cols:
        diag_rows.append({"metric": f"{c}_mean", "value": float(pred_df[c].mean())})

    diag_df = pd.DataFrame(diag_rows)
    latest = pred_df.iloc[-1]
    return MLSignalResult(predictions=pred_df, latest=latest, diagnostics=diag_df)

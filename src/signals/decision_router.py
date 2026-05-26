"""
Signal confirmation and operator decision table.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ConfirmationConfig:
    min_confidence: float = 0.20
    min_expected_edge: float = 0.0002


def build_confirmation_table(
    ml_pred: pd.DataFrame,
    classical_signals: pd.DataFrame | None = None,
    regimes: pd.DataFrame | None = None,
    cfg: ConfirmationConfig | None = None,
) -> pd.DataFrame:
    """
    Build per-month trade/no-trade decisions with reason codes.
    """
    if cfg is None:
        cfg = ConfirmationConfig()
    if ml_pred.empty:
        return pd.DataFrame()

    d = ml_pred.copy()
    d.index = pd.to_datetime(d.index)
    d = d.sort_index()
    d["confidence_final"] = pd.to_numeric(d.get("confidence"), errors="coerce").fillna(0.0)
    d["expected_net_edge"] = (
        pd.to_numeric(d.get("proba_final_long"), errors="coerce").fillna(0.0)
        - pd.to_numeric(d.get("proba_final_short"), errors="coerce").fillna(0.0)
    ) * 0.01

    if classical_signals is not None and not classical_signals.empty:
        c = classical_signals.copy()
        c.index = pd.to_datetime(c.index)
        c = c.sort_index()
        sig_cols = [
            ccol
            for ccol in c.columns
            if ccol.startswith("spread_signal_") or ccol.startswith("cip_signal_") or ccol in ("signal_RU", "signal_CN")
        ]
        if sig_cols:
            classical_dir = c[sig_cols].mean(axis=1).clip(-1.0, 1.0)
            d["classical_dir"] = classical_dir.reindex(d.index).fillna(0.0)
        else:
            d["classical_dir"] = 0.0
    else:
        d["classical_dir"] = 0.0

    if regimes is not None and not regimes.empty:
        r = regimes.copy()
        r.index = pd.to_datetime(r.index)
        reg_col = "regime_C1_lag1" if "regime_C1_lag1" in r.columns else None
        if reg_col:
            d["regime_state"] = r[reg_col].reindex(d.index).fillna("other")
        else:
            d["regime_state"] = "other"
    else:
        d["regime_state"] = "other"

    decisions = []
    for idx, row in d.iterrows():
        ml_sig = int(row.get("ml_signal", 0))
        conf = float(row.get("confidence_final", 0.0))
        edge = float(row.get("expected_net_edge", 0.0))
        cdir = float(row.get("classical_dir", 0.0))
        regime_state = str(row.get("regime_state", "other"))

        reason = "confirmed"
        trade = 1
        if ml_sig == 0:
            reason = "neutral_signal"
            trade = 0
        elif conf < cfg.min_confidence:
            reason = "insufficient_confidence"
            trade = 0
        elif abs(edge) < cfg.min_expected_edge:
            reason = "low_expected_edge"
            trade = 0
        elif cdir != 0 and np.sign(cdir) != np.sign(ml_sig):
            reason = "signal_disagreement"
            trade = 0
        elif regime_state.endswith("stress"):
            reason = "regime_conflict"
            trade = 0

        decisions.append(
            {
                "date": idx,
                "selected_model": row.get("best_model", "ML_ENS"),
                "direction": ml_sig if trade else 0,
                "trade_enabled": int(trade),
                "confidence": round(conf, 6),
                "expected_net_edge": round(edge, 6),
                "reason_code": reason,
                "why_not_trade": "" if trade else reason,
                "regime_state": regime_state,
            }
        )

    return pd.DataFrame(decisions).set_index("date")

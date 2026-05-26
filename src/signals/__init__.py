"""
Phase 3 arbitrage signals for RU/CN yield curve trading.

Modules:
  spread_signals  — rolling z-score on RU-CN maturity-matched spread
  cip             — Covered Interest Parity deviation
  factor_signals  — VAR residual-based NS-factor divergence signals
"""

from .spread_signals import compute_spread_signals, SpreadSignalResult
from .cip import compute_cip_deviation, CIPResult
from .factor_signals import compute_factor_signals, FactorSignalResult
from .ml_signals import generate_ml_signals, MLSignalResult
from .decision_router import build_confirmation_table, ConfirmationConfig
from .signal_config import SignalConfig, ArtifactVersion

__all__ = [
    "compute_spread_signals", "SpreadSignalResult",
    "compute_cip_deviation", "CIPResult",
    "compute_factor_signals", "FactorSignalResult",
    "generate_ml_signals", "MLSignalResult",
    "build_confirmation_table", "ConfirmationConfig",
    "SignalConfig", "ArtifactVersion",
]

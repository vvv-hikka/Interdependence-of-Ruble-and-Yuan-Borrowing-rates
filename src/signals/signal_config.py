"""
Centralized config and artifact-version metadata for signal stack.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalConfig:
    prob_long: float = 0.55
    prob_short: float = 0.45
    min_confidence: float = 0.20
    min_expected_edge: float = 0.0002
    min_obs_router: int = 12
    cost_bps_default: float = 5.0
    persistence_months: int = 2
    cv_splits: int = 5
    cv_embargo: int = 1


@dataclass(frozen=True)
class ArtifactVersion:
    run_id_prefix: str = "signal_reliability_upgrade"
    label_version: str = "v2_triple_barrier_meta"
    router_policy_version: str = "v2_risk_confidence_weighted"
    feature_block_version: str = "v2_relval_macro_stress"

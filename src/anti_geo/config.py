from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefenseConfig:
    """Thresholds for retrieval and synthesis gating."""

    trust_endorsement_min: float = 0.62
    trust_institutional: float = 0.75
    domain_age_young_days: int = 90
    domain_age_established_days: int = 365 * 3
    thin_content_words: int = 80
    broken_link_penalty_ratio: float = 0.4
    broken_link_block_ratio: float = 0.5

    authority_flag_threshold: float = 0.35
    comparative_flag_threshold: float = 0.35
    hedging_flag_threshold: float = 0.2

    high_stakes_risk_threshold: float = 0.45
    high_stakes_trust_threshold: float = 0.65
    downrank_risk_threshold: float = 0.55
    downrank_trust_threshold: float = 0.55

    endorsement_risk_downrank: float = 0.2
    endorsement_risk_block: float = 0.5
    # Ignore tiny endorsement scores when gating on trust (noise floor).
    endorsement_risk_trust_gate: float = 0.05

    independence_jaccard_threshold: float = 0.45
    pawc_dominance_alert: float = 0.60

    front_load_window_words: int = 200
    l1_penalty_weight: float = 0.5
    l2_penalty_weight: float = 0.45
    l2_faulty_penalty: float = 0.35
    retrieval_manipulation_penalty_weight: float = 0.35
    intent_mismatch_penalty_weight: float = 0.3
    retrieve_downrank_penalty: float = 0.25
    dominant_host_penalty: float = 0.45

    commercial_label_min_tier: str = "high"
    commercial_hedge_min_tier: str = "medium"
    claim_chunk_overlap_min: float = 0.15
    audit_persistence_window_days: int = 7

    concealment_hidden_ratio_alert: float = 0.15
    concealment_hidden_words_min: int = 20
    concealment_trust_penalty_max: float = 0.25


DEFAULT_CONFIG = DefenseConfig()

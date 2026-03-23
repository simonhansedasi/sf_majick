# utility_engine.py
import numpy as np
from typing import List, Union, Dict, Tuple
from dataclasses import dataclass, field
from .entities import Lead, Opportunity
from .micro_actions import MICRO_ACTIONS, micro_actions_allowed
from .probabilities import compute_lead_probability, compute_opportunity_probability, simulate_macro_probability
from .utils import clamp


# ------------------------------------------------------------------
# Strategy  (now personality-derived, still manually tunable)
# ------------------------------------------------------------------
@dataclass
class Strategy:
    """
    Tunable strategy for a sales rep.
    All knobs are floats in [0,1] unless otherwise noted.

    New knobs vs. original:
      recency_bias   – overweight deals touched recently (human flaw)
      sunk_cost_bias – keep working deals with high invested-action count
      aggression     – mirrors personality; boosts late-stage, discounts early
      empathy        – mirrors personality; boosts sentiment-heavy scoring
    """
    name:            str   = "Default"
    risk_aversion:   float = 0.5   # 0=chase small deals, 1=chase whales
    communicativeness: float = 0.5 # higher → more micro actions per day
    patience:        float = 0.5   # higher → keep working older leads longer
    focus:           float = 0.5   # higher → concentrate on fewer targets
    momentum_bias:   float = 0.5   # higher → weight macro momentum in scoring
    recency_bias:    float = 0.2   # overweight recently-touched deals
    sunk_cost_bias:  float = 0.15  # overweight deals with high action investment
    aggression:      float = 0.5   # boosts Negotiation/Proposal weight, discounts Prospecting
    empathy:         float = 0.5   # boosts high-sentiment entities

    @classmethod
    def from_personality(cls, personality) -> "Strategy":
        """
        Derive a Strategy from a RepPersonality so knobs reflect character.
        """
        return cls(
            name             = personality.name,
            risk_aversion    = 0.3 + 0.5 * personality.aggression,
            communicativeness= 0.3 + 0.4 * personality.empathy,
            patience         = 1.0 - 0.6 * personality.aggression,
            focus            = 0.3 + 0.5 * personality.discipline,
            momentum_bias    = 0.3 + 0.4 * personality.aggression,
            recency_bias     = 0.1 + 0.3 * (1.0 - personality.discipline),
            sunk_cost_bias   = 0.05 + 0.25 * (1.0 - personality.discipline),
            aggression       = personality.aggression,
            empathy          = personality.empathy,
        )


# ------------------------------------------------------------------
# Core utility functions
# ------------------------------------------------------------------

def expected_commission(entity: Union[Lead, Opportunity], commission_rate: float = 0.010) -> float:
    revenue = getattr(entity, "revenue", 0)
    if isinstance(entity, Lead):
        prob = compute_lead_probability(entity)
        # Fresh leads score near-zero before engagement thresholds are met,
        # causing reps to skip them. A decaying prospecting bonus keeps unworked
        # leads visible in the queue long enough to receive initial touches.
        ms = getattr(entity, "micro_state", None)
        total_touches = ms.get("send_email", 0) + ms.get("make_call", 0) if ms else 0
        prospecting_bonus = max(0.0, 0.015 * (1.0 - min(total_touches / 3.0, 1.0)))
        return (prob + prospecting_bonus) * revenue * commission_rate
    else:
        prob = compute_opportunity_probability(entity)
    return prob * revenue * commission_rate


def _sunk_cost_score(entity) -> float:
    """
    Returns a 0–1 score based on total actions invested so far.
    Reps irrationally overweight deals they've already worked hard on.
    """
    ms = getattr(entity, "micro_state", None)
    if ms is None:
        return 0.0
    total = sum(
        getattr(ms, a, 0)
        for a in ("send_email", "make_call", "hold_meeting",
                  "follow_up", "internal_prep", "research_account",
                  "solution_design", "stakeholder_alignment", "send_proposal")
    )
    # Saturates around 100 total actions → score ≈ 1.0
    return 1.0 - np.exp(-total / 50.0)


def _recency_score(entity) -> float:
    """
    Returns 1.0 for a deal touched yesterday, decays to 0 after ~10 days.
    Models reps' tendency to gravitate toward deals already in motion.
    """
    days = getattr(entity, "days_since_touch", 99)
    return np.exp(-days / 4.0)


def _sentiment_score(entity) -> float:
    """Normalised sentiment, clamped to [0,1]."""
    raw = getattr(entity, "sentiment", 0.0)
    return clamp((raw + 1.0) / 2.0, 0.0, 1.0)


def _stage_aggression_weight(entity, aggression: float) -> float:
    """
    Aggressive reps assign higher weight to late-stage deals.
    Patient reps are more balanced across the pipeline.

    Flattened vs original: base weights are brought closer together so that
    non-aggressive reps still work early-stage opps rather than ignoring them
    entirely. This tightens the earnings spread across personality types.
    """
    stage = getattr(entity, "stage", "")
    base_weights = {
        "Prospecting":   0.60,   # was 0.40 — raised so patient reps still engage
        "Qualification": 0.75,   # was 0.65
        "Proposal":      0.90,
        "Negotiation":   1.10,   # was 1.20 — lowered to reduce Grinder dominance
    }
    base = base_weights.get(stage, 0.70)
    if stage in ("Proposal", "Negotiation"):
        return base * (1.0 + 0.3 * aggression)   # was 0.5 — gentled
    elif stage in ("Prospecting", "Qualification"):
        return base * (1.0 - 0.15 * aggression)  # was 0.3 — gentled
    return base


def strategy_weighted_utility(entity, strategy: Strategy, commission_rate: float = 0.10) -> float:
    """
    Score an entity for prioritisation.  Adds human-bias terms vs. original:
      - recency_bias:   reps overweight recently-touched deals
      - sunk_cost_bias: reps overweight heavily-worked deals
      - aggression:     boosts late-stage, discounts early-stage
      - empathy:        boosts high-sentiment entities
    """
    base = expected_commission(entity, commission_rate)

    revenue = getattr(entity, "revenue", 0)
    risk_modifier       = (revenue / 1_000_000) ** max(strategy.risk_aversion, 0.01)

    macro_prob          = simulate_macro_probability(entity)
    macro_modifier      = 1.0 + strategy.momentum_bias * macro_prob

    patience_modifier   = strategy.patience
    focus_modifier      = strategy.focus

    # Human-bias terms
    recency_modifier    = 1.0 + strategy.recency_bias    * _recency_score(entity)
    sunk_cost_modifier  = 1.0 + strategy.sunk_cost_bias  * _sunk_cost_score(entity)
    sentiment_modifier  = 1.0 + strategy.empathy         * _sentiment_score(entity)
    stage_modifier      = _stage_aggression_weight(entity, strategy.aggression)

    return (
        base
        * risk_modifier
        * macro_modifier
        * patience_modifier
        * focus_modifier
        * recency_modifier
        * sunk_cost_modifier
        * sentiment_modifier
        * stage_modifier
    )


def micro_actions_allowed(entity):
    """
    Returns MicroAction objects the entity can currently perform
    (respects gating and cooldowns).
    """
    allowed = []
    for action in MICRO_ACTIONS.values():
        if entity.micro_state.can_perform(action.name):
            allowed.append(action)
    return allowed


def choose_targets_with_strategy(
    entities: List[Union[Lead, Opportunity]],
    rep_id: str,
    strategy: Strategy,
    commission_rate: float = 0.10,
) -> List[Tuple[Union[Lead, Opportunity], List[str]]]:
    """
    Returns a sorted list of (entity, allowed_micro_actions) tuples.
    Focus knob: high-focus reps only get the top-N entities,
    low-focus reps get a wider (noisier) portfolio.
    """
    actionable_entities = []

    for e in entities:
        if isinstance(e, Opportunity) and getattr(e, "rep_id", None) != rep_id:
            continue

        allowed_actions = [a.name for a in micro_actions_allowed(e)]

        if isinstance(e, Opportunity) and not allowed_actions:
            continue

        if isinstance(e, Lead) and not allowed_actions:
            allowed_actions = ["send_email", "make_call", "hold_meeting"]

        actionable_entities.append((e, allowed_actions))

    # Sort by strategy-weighted utility
    actionable_entities.sort(
        key=lambda tup: strategy_weighted_utility(tup[0], strategy, commission_rate),
        reverse=True,
    )

    # Focus: high-focus reps work fewer targets more deeply
    if len(actionable_entities) > 3:
        # focus=1.0 → top 30% of pipeline; focus=0.0 → all of it
        cap = max(3, int(len(actionable_entities) * (0.30 + 0.70 * (1.0 - strategy.focus))))
        actionable_entities = actionable_entities[:cap]

    return actionable_entities


# ------------------------------------------------------------------
# Commission helpers (unchanged interface)
# ------------------------------------------------------------------

def prioritize_opportunities(
    opportunities: List[object],
    strategy: str = "hybrid",
):
    if strategy == "whale":
        return sorted(opportunities, key=lambda o: getattr(o, "revenue", 0), reverse=True)
    elif strategy == "small":
        return sorted(opportunities, key=lambda o: getattr(o, "revenue", 0))
    elif strategy == "hybrid":
        return sorted(opportunities, key=lambda o: expected_commission(o), reverse=True)
    else:
        return opportunities

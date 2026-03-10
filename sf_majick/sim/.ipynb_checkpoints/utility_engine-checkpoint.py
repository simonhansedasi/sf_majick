# utility.py
import numpy as np
from typing import List, Union, Dict, Tuple
from dataclasses import dataclass
from .entities import Lead, Opportunity
from .micro_actions import MICRO_ACTIONS, micro_actions_allowed
from .probabilities import compute_lead_probability, compute_opportunity_probability, simulate_macro_probability
# from .utils import 
from .utils import clamp

@dataclass
class Strategy:
    """
    Tunable strategy for a sales rep.
    All knobs are floats in [0,1] unless otherwise noted.
    """
    name: str = "Default"
    risk_aversion: float = 0.5       # 0=chase small, 1=chase whales
    communicativeness: float = 0.5   # higher -> more micro actions per day
    patience: float = 0.5            # higher -> keep working older leads longer
    focus: float = 0.5               # higher -> concentrate attention on fewer targets
    momentum_bias: float = 0.5       # higher -> weight momentum in probability

# ---------------------------------------------------------------------
# Core Utility Functions
# ---------------------------------------------------------------------

def expected_commission(entity: Union[Lead, Opportunity], commission_rate: float = 0.010) -> float:
    """
    Expected commission for an entity (lead or opportunity).
    """
    revenue = getattr(entity, "revenue", getattr(entity, "revenue", 0))
    if isinstance(entity, Lead):
        prob = compute_lead_probability(entity)  # <-- use the function
    else:
        prob = compute_opportunity_probability(entity)
        
    # print(prob, revenue, commission_rate)
    return prob * revenue * commission_rate





def strategy_weighted_utility(entity, strategy, commission_rate=0.10):
    base = expected_commission(entity, commission_rate)

    revenue = getattr(entity, "revenue", 0)
    risk_modifier = (revenue / 1_000_000) ** strategy.risk_aversion

    # Use visible macro probability, not hidden momentum
    macro_prob = simulate_macro_probability(entity)
    macro_modifier = 1.0 + strategy.momentum_bias * macro_prob

    patience_modifier = strategy.patience
    focus_modifier = strategy.focus

    return base * risk_modifier * macro_modifier * patience_modifier * focus_modifier
    # return base * risk_modifier * momentum_modifier * patience_modifier * focus_modifier



def micro_actions_allowed(op: Opportunity):
    """
    Returns a list of MicroAction objects that this Opportunity
    can currently perform, taking cooldown and dependencies into account.
    """
    allowed_actions = []
    for action in MICRO_ACTIONS.values():
        if op.micro_state.can_perform(action.name):
            allowed_actions.append(action)
    return allowed_actions





def choose_targets_with_strategy(
    entities: List[Union[Lead, Opportunity]],
    rep_id: str,
    strategy: Strategy,
    commission_rate: float = 0.10
) -> List[Tuple[Union[Lead, Opportunity], List[str]]]:
    """
    Returns a sorted list of (entity, allowed_micro_actions) tuples.
    Only includes opportunities assigned to this rep and with available actions.
    Leads are included with their allowed micro actions.
    """
    actionable_entities = []

    for e in entities:
        # Enforce ownership for Opportunities
        if isinstance(e, Opportunity) and getattr(e, "rep_id", None) != rep_id:
            continue

        # Determine allowed actions
        allowed_actions = [a.name for a in micro_actions_allowed(e)]

        # Skip Opportunities with no actions
        if isinstance(e, Opportunity) and not allowed_actions:
            continue

        # Leads are always included if they have allowed actions
        if isinstance(e, Lead) and not allowed_actions:
            # Assign default lead micro actions if empty
            allowed_actions = ["send_email", "make_call", "hold_meeting"]

        actionable_entities.append((e, allowed_actions))

    # Sort by strategy-weighted utility
    actionable_entities.sort(
        key=lambda tup: strategy_weighted_utility(tup[0], strategy, commission_rate),
        reverse=True
    )

    return actionable_entities
# ---------------------------------------------------------------------
# Commission Helpers
# ---------------------------------------------------------------------

from typing import List
# from .macro_actions import estimate_close_probability


def prioritize_opportunities(
    opportunities: List[object],  # Could be Lead or Opportunity
    strategy: str = "hybrid"
):
    """
    Returns opportunities sorted by priority based on strategy.

    Strategies:
    - 'whale': prioritize high commission opportunities
    - 'small': prioritize low commission, high number opportunities
    - 'hybrid': expected commission
    """

    if strategy == "whale":
        # descending revenue
        return sorted(opportunities, key=lambda o: getattr(o, "revenue", 0), reverse=True)
    elif strategy == "small":
        # ascending revenue
        return sorted(opportunities, key=lambda o: getattr(o, "revenue", 0))
    elif strategy == "hybrid":
        # expected commission
        return sorted(opportunities, key=lambda o: expected_commission(o), reverse=True)
    else:
        return opportunities

    
    
    
    



# micro_policy.py
import numpy as np
import random

from .entities import Lead, Opportunity
from .theta import theta
from .micro_actions import derived_momentum, derived_friction, MICRO_ACTIONS
from .macro_actions import compute_opportunity_probability, compute_close_probability


# ------------------------------------------------------------------
# Action affinity tables
# Personality traits pull reps toward/away from action families.
# ------------------------------------------------------------------

# Actions that aggressive reps prefer (direct, revenue-moving)
AGGRESSIVE_PREFERRED  = {"make_call", "hold_meeting", "send_proposal", "stakeholder_alignment"}
# Actions that empathetic reps prefer (relationship, nurture)
EMPATHY_PREFERRED     = {"send_email", "follow_up", "hold_meeting", "internal_prep"}
# Actions that disciplined reps prefer (systematic, foundational)
DISCIPLINE_PREFERRED  = {"research_account", "internal_prep", "solution_design"}
# Actions that scattered reps over-use (low-effort defaults)
SCATTERED_DEFAULT     = {"send_email", "make_call"}


def _personality_action_weight(action_name: str, personality) -> float:
    """
    Returns a multiplier [0.5, 2.0] for how much a rep's personality
    pulls them toward a given action.
    """
    weight = 1.0

    if action_name in AGGRESSIVE_PREFERRED:
        weight *= 1.0 + personality.aggression
    if action_name in EMPATHY_PREFERRED:
        weight *= 1.0 + personality.empathy
    if action_name in DISCIPLINE_PREFERRED:
        weight *= 1.0 + personality.discipline
    if action_name in SCATTERED_DEFAULT and personality.discipline < 0.35:
        # Scattered reps gravitate to comfort-zone actions
        weight *= 1.5

    return np.clip(weight, 0.5, 3.0)


def _softmax_temperature(personality) -> float:
    """
    Disciplined reps are deterministic (low T → sharp argmax).
    Scattered reps are noisy (high T → near-uniform).
    Stress also raises temperature (decision fatigue).
    """
    base_temp  = 0.5 + 1.5 * (1.0 - personality.discipline)
    return base_temp


def _context_action_bonus(action_name: str, entity, rep=None) -> float:
    """
    Context-aware bonuses: reward actions that match the deal's current state.

    Combines two signals:
      1. Hardcoded heuristics (momentum, friction, stage, sentiment)
      2. Rep's personally learned timing weights for (action, stage)

    The learned component starts at zero and grows as the rep accumulates
    observations. Early in a run the heuristics dominate; later the rep's
    own experience adjusts the bonuses up or down.
    """
    bonus = 0.0

    momentum  = derived_momentum(entity)
    friction  = derived_friction(entity)
    sentiment = getattr(entity, "sentiment", 0.0)
    stage     = getattr(entity, "stage", "Prospecting")

    # Momentum context
    if momentum > 0.1 and action_name in {"hold_meeting", "send_proposal", "stakeholder_alignment"}:
        bonus += 0.3 * momentum

    # Friction / repair context
    if friction > 0.15 and action_name in {"follow_up", "send_email", "internal_prep"}:
        bonus += 0.4 * friction

    # Sentiment repair: if sentiment is negative, more nurture
    if sentiment < -0.3 and action_name in {"follow_up", "hold_meeting", "send_email"}:
        bonus += 0.3

    # Stage context: early stages prefer groundwork
    if stage in ("Prospecting", "Qualification") and action_name in {
        "send_email", "make_call", "research_account"
    }:
        bonus += 0.2

    # Stage context: late stages prefer commitment actions
    if stage in ("Proposal", "Negotiation") and action_name in {
        "send_proposal", "stakeholder_alignment", "follow_up", "hold_meeting"
    }:
        bonus += 0.3

    # Learned timing bonus — grows with the rep's personal evidence
    if rep is not None and hasattr(rep, "get_timing_bonus"):
        bonus += rep.get_timing_bonus(action_name, stage)

    return bonus


def simulate_rep_thinking(rep, entity, horizon: int = 3) -> str:
    """
    Choose a micro action for the rep on the given entity.

    Personality shapes:
      1. Which actions are even considered (via can_perform gating)
      2. How each action is scored (personality affinity + context bonus)
      3. How deterministically the rep follows the optimal action (temperature)
      4. Whether a distracted rep just picks a comfort-zone action instead
    """
    personality = getattr(rep, "personality", None)

    # --- Build eligible action list ---
    if isinstance(entity, Opportunity):
        candidate_pool = [
            "send_email", "make_call", "hold_meeting",
            "follow_up", "send_proposal", "internal_prep",
            "research_account", "solution_design", "stakeholder_alignment",
        ]
    elif isinstance(entity, Lead):
        candidate_pool = [
            "send_email", "make_call", "hold_meeting",
            "follow_up", "internal_prep", "research_account",
        ]
    else:
        candidate_pool = []

    eligible_actions = [a for a in candidate_pool if entity.micro_state.can_perform(a)]

    # --- Fallback if nothing is gated-open ---
    if not eligible_actions:
        fallback = ["send_email", "make_call", "research_account", "internal_prep"]
        eligible_actions = [a for a in fallback if a in MICRO_ACTIONS]
        if not eligible_actions:
            eligible_actions = list(MICRO_ACTIONS.keys())

    # --- Scattered-rep distraction: sometimes just pick a comfort action ---
    if personality and personality.discipline < 0.35:
        if random.random() < (0.35 - personality.discipline):
            comfort = [a for a in SCATTERED_DEFAULT if a in eligible_actions]
            if comfort:
                return random.choice(comfort)

    # --- Score each action ---
    action_values: dict = {}

    for action_name in eligible_actions:
        # Lookahead simulation
        total_expected = 0.0
        sim_entity = entity.copy_for_simulation()

        for t in range(horizon):
            delta = simulate_behavioral_response(sim_entity, action_name)

            sim_actions = [
                a for a in eligible_actions
                if sim_entity.micro_state.can_perform(a)
            ]
            if not sim_actions:
                break

            momentum = derived_momentum(sim_entity)
            friction = derived_friction(sim_entity)

            if sim_entity.stage == "Negotiation":
                p = compute_close_probability(sim_entity)
            else:
                p = compute_opportunity_probability(sim_entity)

            total_expected += p * sim_entity.revenue * rep.comp_rate

            # Greedy next step (inner loop unchanged from original)
            sim_action = max(
                sim_actions,
                key=lambda a: compute_opportunity_probability(sim_entity) * sim_entity.revenue,
            )

        base_value = total_expected / horizon

        # --- Personality affinity modifier ---
        if personality:
            affinity = _personality_action_weight(action_name, personality)
        else:
            affinity = 1.0

        # --- Context-aware bonus (includes rep's learned timing weights) ---
        context_bonus = _context_action_bonus(action_name, entity, rep=rep)

        action_values[action_name] = base_value * affinity + context_bonus

    # --- Softmax selection with personality-derived temperature ---
    names = list(action_values.keys())
    if not names:
        return np.random.choice(["send_email", "make_call", "research_account"])

    temp = _softmax_temperature(personality) if personality else 1.0

    # Motivation loss raises temperature (demoralised reps act more randomly)
    motivation = getattr(rep, "motivation", 1.0)
    temp *= (1.0 + 0.5 * (1.0 - motivation))

    raw_values = np.array(list(action_values.values()))
    scaled     = (raw_values - raw_values.max()) / temp
    exp_vals   = np.exp(scaled)
    probs      = exp_vals / exp_vals.sum()

    return np.random.choice(names, p=probs)


def simulate_behavioral_response(entity, action_type: str) -> dict:
    """
    Return a delta dict for what would happen if the action is applied,
    WITHOUT mutating real MicroState or sentiment.
    """
    all_actions = [
        "send_email", "make_call", "hold_meeting", "follow_up",
        "send_proposal", "internal_prep", "research_account",
        "solution_design", "stakeholder_alignment",
    ]
    delta = {a: 0 for a in all_actions}

    if entity.micro_state.can_perform(action_type):
        delta[action_type] += 1

    return delta


def execute_actions(entity, actions) -> None:
    """
    Apply a micro action dict or requirement-tree to an entity.
    """
    if actions is None:
        return

    if isinstance(actions, dict):
        if all(isinstance(v, int) for v in actions.values()):
            for k, v in actions.items():
                entity.micro_state.record_action(k, v)
            return

        if "sequence" in actions:
            for step in actions["sequence"]:
                execute_actions(entity, step)
            return

        if "and" in actions or "or" in actions:
            key = "and" if "and" in actions else "or"
            for step in actions[key]:
                execute_actions(entity, step)
            return

        if "chance" in actions:
            if random.random() < actions["chance"]:
                execute_actions(entity, actions.get("req", {}))
            return
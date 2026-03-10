import numpy as np

from .entities import Lead, Opportunity
from .theta import theta
from .micro_actions import derived_momentum, derived_friction, MICRO_ACTIONS
from .macro_actions import compute_opportunity_probability, compute_close_probability


def simulate_rep_thinking(rep, entity, horizon=3):
    """
    Choose a micro action for the rep on the given entity.
    Functional behavior unchanged; adds safe fallback if no actions eligible.
    """
    # --- Define eligible actions based on type ---
    if isinstance(entity, Opportunity):
        eligible_actions = [
            "send_email", "make_call", "hold_meeting",
            "follow_up", "send_proposal", "internal_prep", "research_account",
            "solution_design", "stakeholder_alignment"
        ]
    elif isinstance(entity, Lead):
        eligible_actions = [
            "send_email", "make_call", "hold_meeting",
            "follow_up", "internal_prep", "research_account"
        ]
    else:
        eligible_actions = []

    # Filter by micro_state.can_perform
    eligible_actions = [a for a in eligible_actions if entity.micro_state.can_perform(a)]

    # --- Fallback for empty eligible actions ---
    if not eligible_actions:
        # return None
        # pick low-effort, always-available actions
        fallback = ["send_email", "make_call", "research_account", "internal_prep"]
        eligible_actions = [a for a in fallback if a in MICRO_ACTIONS]

        # still empty? pick literally any known action
        if not eligible_actions:
            eligible_actions = list(MICRO_ACTIONS.keys())

    action_values = {}

    # --- Evaluate each action ---
    for action_name in eligible_actions:
        total_expected = 0.0
        sim_entity = entity.copy_for_simulation()

        for t in range(horizon):
            # Apply micro-action (sentiment-only)
            delta = simulate_behavioral_response(sim_entity, action_name)
            # execute_actions(sim_entity, chosen_actions)  # leave as before, unchanged

            # Find next-step eligible actions
            sim_actions = [
                a for a in eligible_actions
                if sim_entity.micro_state.can_perform(a)
            ]
            if not sim_actions:
                break

            # Derived latent variables
            momentum = derived_momentum(sim_entity)
            friction = derived_friction(sim_entity)

            # Compute expected reward
            if sim_entity.stage == "Negotiation":
                p = compute_close_probability(sim_entity)
            else:
                p = compute_opportunity_probability(sim_entity)

            total_expected += p * sim_entity.revenue * rep.comp_rate

            # --- Next-step action (greedy over eligible actions) ---
            sim_action = max(
                sim_actions,
                key=lambda a: compute_opportunity_probability(sim_entity) * sim_entity.revenue
            )

        action_values[action_name] = total_expected / horizon

    # --- Softmax selection (safe against empty arrays) ---
    names = list(action_values.keys())
    if not names:
        # pick a basic fallback action if somehow still empty
        return np.random.choice(["send_email", "make_call", "research_account"])

    deltas = np.array(list(action_values.values()))
    exp_deltas = np.exp(deltas - np.max(deltas))
    probs = exp_deltas / exp_deltas.sum()
    return np.random.choice(names, p=probs)

def simulate_behavioral_response(entity, action_type):
    """
    Return a *delta dict* representing what would happen if the action is applied,
    WITHOUT mutating the real MicroState or sentiment.
    Respects gating / can_perform.
    """
    # Ensure all known micro actions exist in delta
    all_actions = [
        "send_email", "make_call", "hold_meeting", "follow_up",
        "send_proposal", "internal_prep", "research_account",
        "solution_design", "stakeholder_alignment"
    ]
    delta = {a: 0 for a in all_actions}

    if entity.micro_state.can_perform(action_type):
        delta[action_type] += 1

    return delta

def execute_actions(entity, actions):
    """
    Take a micro action dict or sequence and perform them individually.
    """
    if actions is None:
        return
    # If it's a dict with micro action counts
    if all(isinstance(v, int) for v in actions.values()):
        for k, v in actions.items():
            entity.micro_state.record_action(k, v)
        return

    # If it's a sequence node
    if "sequence" in actions:
        for step in actions["sequence"]:
            execute_actions(entity, step)
        return

    # If it's AND/OR
    if "and" in actions or "or" in actions:
        key = "and" if "and" in actions else "or"
        for step in actions[key]:
            execute_actions(entity, step)
        return

    # If it's chance node
    if "chance" in actions:
        if random.random() < actions["chance"]:
            execute_actions(entity, actions.get("req", {}))
        return
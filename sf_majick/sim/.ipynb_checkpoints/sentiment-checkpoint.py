import random
import numpy as np
# from .utils import clamp

def clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))

TOUCH_ACTIONS = [
    "email",
    "call",
    "meeting",
    "follow_up"
]

ACTION_FATIGUE_K = {
    "email": 0.45,
    "call": 0.35,
    "follow_up": 0.30,
    "meeting": 0.12
}


def action_fatigue(action_type, entity):

    if action_type not in ACTION_FATIGUE_K:
        return 1.0

    k = ACTION_FATIGUE_K[action_type]

    count = entity.micro_state.get(action_type, 0)

    fatigue = np.exp(-k * count * 1.4)

    return max(0.1, fatigue)


def stage_fatigue(entity):

    touches = sum(
        entity.micro_state.get(a, 0)
        for a in TOUCH_ACTIONS
    )
    
    fatigue = np.exp(-0.04 * touches)

    
    
    return max(0.15, fatigue)

# ---------------------------------------------------------------------
# Sentiment System
# ---------------------------------------------------------------------
def compute_sentiment_delta(action_type, rep, entity, decay_days = 0):

    # -----------------------------
    # 1️⃣ Passive decay
    # -----------------------------
    if action_type == "no_touch":
        base = -0.05 * decay_days**1.35
            
        stage_multiplier = {
            "Prospecting": 0.7,
            "Qualification": 1.0,
            "Proposal": 1.3,
            "Negotiation": 1.5
        }.get(entity.stage, 1.0)

        base *= stage_multiplier
        
        if hasattr(entity, "personality"):
            p = entity.personality
            base -= 0.12 * p.skepticism
            base -= 0.1 * p.urgency

        return base
        
    if rep is None:
        return 0.0

    s = rep.strategy
    p = entity.personality

    # -----------------------------
    # 2️⃣ Base action strengths
    # -----------------------------
    action_base = {
        "email": 0.05,
        "call": 0.10,
        "meeting": 0.20,
        "follow_up": 0.05,
        "research_account": 0.0,
        "internal_prep": 0.0,
        "solution_design": 0.03,
        "stakeholder_alignment": 0.06,
        "send_proposal": 0.15,
    }.get(action_type, 0.0)

    # -----------------------------
    # 3️⃣ Personality alignment
    # -----------------------------
    if action_type == "email":
        alignment = 0.7 * p.openness - 0.9 * p.skepticism

    elif action_type == "call":
        alignment = 0.9 * p.urgency - 1.0 * p.skepticism

    elif action_type == "meeting":
        alignment = 0.6 * p.openness + 0.8 * p.urgency - 1.1 * p.skepticism

    elif action_type == "send_proposal":
        alignment = 0.7 * p.urgency - 1.2 * p.price_sensitivity

    elif action_type == "solution_design":
        alignment = 0.2 * p.openness - 0.3 * p.skepticism

    elif action_type == "stakeholder_alignment":
        alignment = 0.5 * p.openness + 0.4 * p.urgency - 0.8 * p.skepticism

    else:
        alignment = 0.0
    # -----------------------------
    # 4️⃣ Strategy modulation
    # -----------------------------
    strategy_boost = (
        0.15 * (s.communicativeness - 0.5)
        + 0.10 * (getattr(s, "focus", 0) - 0.5)
    )

    # -----------------------------
    # 5️⃣ Acceleration (trend continuation)
    # -----------------------------
    # replaces old momentum mutation
    trend_amp = s.momentum_bias * entity.last_sentiment_delta

    # -----------------------------
    # 6️⃣ Diminishing returns
    # -----------------------------
    saturation_penalty = -0.35 * entity.sentiment

    # -----------------------------
    # 7️⃣ Noise (keep small)
    # -----------------------------
    noise_scale = 0.25 if action_type in ["solution_design", "internal_prep", "research_account"] else 0.35
    noise = random.gauss(0, noise_scale)
    delta = (
        action_base
        + alignment
        + strategy_boost
        + trend_amp
        + saturation_penalty
        + noise
    )

    # -----------------------------
    # Memory effect (recent interactions compound)
    # -----------------------------
    memory = 0
    if hasattr(entity, "sentiment_history") and entity.sentiment_history:
        recent = entity.sentiment_history[-3:]
        memory = sum(recent) * 0.15

    delta += memory


    # -----------------------------
    # Random negative events
    # -----------------------------
    bad_event = 0
    r = random.random()

    if r < 0.10:
        bad_event -= random.uniform(0.3, 0.8)  # annoyance
    elif r < 0.15:
        bad_event -= random.uniform(0.8, 1.5)  # serious friction

    delta += bad_event


    # -----------------------------
    # Rare major shocks
    # -----------------------------
    shock = 0
    if random.random() < 0.03:
        shock = random.choice([-2.5, -2.0, -1.5, 1.5, 2.0, 2.5])

    delta += shock


    # -----------------------------
    # Emotional regime multiplier
    # -----------------------------
    if entity.sentiment < -2:
        regime_mult = 1.6
    elif entity.sentiment < 1:
        regime_mult = 1.0
    elif entity.sentiment < 3:
        regime_mult = 1.2
    else:
        regime_mult = 1.4

    delta *= regime_mult


    # -----------------------------
    # Fatigue penalties
    # -----------------------------
    delta *= action_fatigue(action_type, entity)
    delta *= stage_fatigue(entity)
    
    drift = -0.015
    delta += drift
    if action_type == "stakeholder_alignment" and random.random() < 0.25:
        delta += 0.4
    return clamp(delta, -2.5, 2.5)


def apply_sentiment(action_type: str, rep, entity, decay_days = 1) -> float:
    delta = compute_sentiment_delta(action_type, rep, entity, decay_days = decay_days)

    entity.sentiment = clamp(entity.sentiment + delta, -5, 5)
    entity.last_sentiment_delta = delta

    if not hasattr(entity, "sentiment_history"):
        entity.sentiment_history = []

    entity.sentiment_history.append(delta)

    return delta
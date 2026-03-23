import random
import numpy as np


def clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))


# Full canonical action names used throughout the sim
TOUCH_ACTIONS = [
    "send_email",
    "make_call",
    "hold_meeting",
    "follow_up",
]

ACTION_FATIGUE_K = {
    "send_email":  0.45,
    "make_call":   0.35,
    "follow_up":   0.30,
    "hold_meeting":0.12,
}


def action_fatigue(action_type, entity):
    if action_type not in ACTION_FATIGUE_K:
        return 1.0
    k     = ACTION_FATIGUE_K[action_type]
    count = entity.micro_state.get(action_type, 0)
    return max(0.1, np.exp(-k * count * 1.4))


def stage_fatigue(entity):
    touches = sum(entity.micro_state.get(a, 0) for a in TOUCH_ACTIONS)
    return max(0.15, np.exp(-0.04 * touches))


# ------------------------------------------------------------------
# Core delta computation
# ------------------------------------------------------------------

def compute_sentiment_delta(action_type, rep, entity, decay_days=0):
    """
    Compute the sentiment delta for a single action.

    Can be called two ways:
      1. Live (during simulation):
            compute_sentiment_delta("hold_meeting", rep, entity)
         rep and entity are live objects; fatigue/memory read from entity.

      2. Replay (from sentiment_effects.py analysis):
            compute_sentiment_delta(
                action_type, rep_stub, entity_stub,
            )
         Pass lightweight stub objects with the fields this function
         reads: rep.strategy, entity.personality, entity.sentiment,
         entity.last_sentiment_delta, entity.sentiment_history,
         entity.micro_state, entity.stage.
         See ReplaySentimentContext below.
    """

    # ------------------------------------------------------------------
    # 1. Passive decay
    # ------------------------------------------------------------------
    if action_type == "no_touch":
        base = -0.05 * decay_days ** 1.35
        stage_multiplier = {
            "Prospecting":  0.7,
            "Qualification":1.0,
            "Proposal":     1.3,
            "Negotiation":  1.5,
        }.get(getattr(entity, "stage", "Prospecting"), 1.0)
        base *= stage_multiplier
        if hasattr(entity, "personality") and entity.personality is not None:
            p = entity.personality
            base -= 0.12 * p.skepticism
            base -= 0.10 * p.urgency
        return base

    if rep is None:
        return 0.0

    s = rep.strategy
    p = entity.personality

    # ------------------------------------------------------------------
    # 2. Base action strengths
    # ------------------------------------------------------------------
    action_base = {
        "send_email":            0.05,
        "make_call":             0.10,
        "hold_meeting":          0.20,
        "follow_up":             0.05,
        "research_account":      0.00,
        "internal_prep":         0.00,
        "solution_design":       0.03,
        "stakeholder_alignment": 0.06,
        "send_proposal":         0.15,
    }.get(action_type, 0.0)

    # ------------------------------------------------------------------
    # 3. Personality alignment
    # ------------------------------------------------------------------
    if action_type == "send_email":
        alignment = 0.7 * p.openness - 0.9 * p.skepticism

    elif action_type == "make_call":
        alignment = 0.9 * p.urgency - 1.0 * p.skepticism

    elif action_type == "hold_meeting":
        alignment = 0.6 * p.openness + 0.8 * p.urgency - 1.1 * p.skepticism

    elif action_type == "send_proposal":
        alignment = 0.7 * p.urgency - 1.2 * p.price_sensitivity

    elif action_type == "solution_design":
        alignment = 0.2 * p.openness - 0.3 * p.skepticism

    elif action_type == "stakeholder_alignment":
        alignment = 0.5 * p.openness + 0.4 * p.urgency - 0.8 * p.skepticism

    else:
        alignment = 0.0

    # ------------------------------------------------------------------
    # 4. Strategy modulation
    # ------------------------------------------------------------------
    strategy_boost = (
        0.15 * (s.communicativeness - 0.5)
        + 0.10 * (getattr(s, "focus", 0.5) - 0.5)
    )

    # ------------------------------------------------------------------
    # 5. Trend continuation
    # ------------------------------------------------------------------
    trend_amp = s.momentum_bias * entity.last_sentiment_delta

    # ------------------------------------------------------------------
    # 6. Saturation penalty
    # ------------------------------------------------------------------
    saturation_penalty = -0.35 * entity.sentiment

    # ------------------------------------------------------------------
    # 7. Noise
    # ------------------------------------------------------------------
    noise_scale = (
        0.25 if action_type in {"solution_design", "internal_prep", "research_account"}
        else 0.35
    )
    noise = random.gauss(0, noise_scale)

    delta = (
        action_base
        + alignment
        + strategy_boost
        + trend_amp
        + saturation_penalty
        + noise
    )

    # ------------------------------------------------------------------
    # 8. Memory effect
    # ------------------------------------------------------------------
    if hasattr(entity, "sentiment_history") and entity.sentiment_history:
        recent = entity.sentiment_history[-3:]
        delta += sum(recent) * 0.15

    # ------------------------------------------------------------------
    # 9. Random negative events
    # ------------------------------------------------------------------
    r = random.random()
    if r < 0.10:
        delta -= random.uniform(0.3, 0.8)
    elif r < 0.15:
        delta -= random.uniform(0.8, 1.5)

    # ------------------------------------------------------------------
    # 10. Rare major shocks
    # ------------------------------------------------------------------
    if random.random() < 0.03:
        delta += random.choice([-2.5, -2.0, -1.5, 1.5, 2.0, 2.5])

    # ------------------------------------------------------------------
    # 11. Emotional regime multiplier
    # ------------------------------------------------------------------
    if entity.sentiment < -2:
        regime_mult = 1.6
    elif entity.sentiment < 1:
        regime_mult = 1.0
    elif entity.sentiment < 3:
        regime_mult = 1.2
    else:
        regime_mult = 1.4
    delta *= regime_mult

    # ------------------------------------------------------------------
    # 12. Fatigue
    # ------------------------------------------------------------------
    delta *= action_fatigue(action_type, entity)
    delta *= stage_fatigue(entity)

    # ------------------------------------------------------------------
    # 13. Baseline drift
    # ------------------------------------------------------------------
    delta -= 0.015

    # ------------------------------------------------------------------
    # 14. Stakeholder alignment bonus
    # ------------------------------------------------------------------
    if action_type == "stakeholder_alignment" and random.random() < 0.25:
        delta += 0.4

    return clamp(delta, -2.5, 2.5)


def apply_sentiment(action_type: str, rep, entity, decay_days=1) -> float:
    delta = compute_sentiment_delta(action_type, rep, entity, decay_days=decay_days)
    entity.sentiment = clamp(entity.sentiment + delta, -5, 5)
    entity.last_sentiment_delta = delta
    if not hasattr(entity, "sentiment_history"):
        entity.sentiment_history = []
    entity.sentiment_history.append(delta)
    return delta


# ------------------------------------------------------------------
# Replay context — lightweight stubs for analysis without live objects
# ------------------------------------------------------------------

class _ReplayMicroState:
    """Minimal micro_state stub for replay. Holds action counts."""
    def __init__(self, counts: dict):
        self._counts = counts

    def get(self, key, default=0):
        return self._counts.get(key, default)


class _ReplayPersonality:
    def __init__(self, openness, urgency, skepticism, price_sensitivity):
        self.openness           = openness
        self.urgency            = urgency
        self.skepticism         = skepticism
        self.price_sensitivity  = price_sensitivity


class _ReplayStrategy:
    def __init__(self, communicativeness=0.5, focus=0.5, momentum_bias=0.5):
        self.communicativeness  = communicativeness
        self.focus              = focus
        self.momentum_bias      = momentum_bias


class ReplayRep:
    """
    Lightweight rep stub for replay analysis.
    Pass to compute_sentiment_delta instead of a live SalesRep.
    """
    def __init__(
        self,
        communicativeness: float = 0.5,
        focus: float = 0.5,
        momentum_bias: float = 0.5,
    ):
        self.strategy = _ReplayStrategy(communicativeness, focus, momentum_bias)


class ReplayEntity:
    """
    Lightweight entity stub for replay analysis.
    Reconstructed from a row of the micro log + entity context.

    Parameters
    ----------
    sentiment           : entity sentiment at time of action
    last_sentiment_delta: previous delta (for trend continuation)
    sentiment_history   : list of recent deltas (for memory effect)
    action_counts       : dict of {action_name: count_so_far}
    stage               : pipeline stage at time of action
    personality_params  : dict with openness, urgency, skepticism, price_sensitivity
    """
    def __init__(
        self,
        sentiment: float = 0.0,
        last_sentiment_delta: float = 0.0,
        sentiment_history: list = None,
        action_counts: dict = None,
        stage: str = "Prospecting",
        personality_params: dict = None,
    ):
        self.sentiment            = sentiment
        self.last_sentiment_delta = last_sentiment_delta
        self.sentiment_history    = sentiment_history or []
        self.stage                = stage
        self.micro_state          = _ReplayMicroState(action_counts or {})

        params = personality_params or {
            "openness": 0.5, "urgency": 0.5,
            "skepticism": 0.5, "price_sensitivity": 0.5,
        }
        self.personality = _ReplayPersonality(**params)

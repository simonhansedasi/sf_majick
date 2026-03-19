import numpy as np
from .theta import theta
from .entities import Lead, Opportunity, Account
from .micro_actions import derived_momentum, derived_friction


def dynamic_closed_lost_probability(entity, rep: 'SalesRep' = None):
    if isinstance(entity, Opportunity):
        return 1 - compute_opportunity_probability(entity)
    if isinstance(entity, Lead):
        return 1 - compute_lead_probability(entity)
    
    

def simulate_macro_probability(entity, rep=None) -> float:
    """
    Estimate probability that a macro (stage advancement or lead conversion) succeeds.
    Works for both Leads and Opportunities.
    Returns a number between 0 and 1.
    """
    if getattr(entity, "is_closed", False):
        return 0.0

    # Base daily probabilities for each stage
    stage_probs = {
        "Lead": 0.05,
        "Prospecting": 0.08,
        "Qualification": 0.04,
        "Proposal": 0.02,
        "Negotiation": 0.01,
    }
    base = stage_probs.get(getattr(entity, "stage", "Lead"), 0.05)

    # Behavioral modifiers (scaled)
    momentum = getattr(entity, "momentum", 0.0) * 0.25
    friction = getattr(entity, "friction", 0.0) * 0.25
    sentiment = getattr(entity, "sentiment", 0.0)
    sentiment_factor = np.clip(sentiment / 5, -1, 1) * 0.2

    # Combine factors
    prob = base + momentum - friction + sentiment_factor
    return np.clip(prob, 0.0, 1.0)
    
# -----------------------------
# 1️⃣ compute_opportunity_probability
# -----------------------------
def compute_opportunity_probability(op: Opportunity, rep=None) -> float:
    stage_base = {
        "Prospecting": theta["base_prob_prospecting"],
        "Qualification": theta["base_prob_qualification"],
        "Proposal": theta["base_prob_proposal"],
        "Negotiation": theta["base_prob_negotiation"],
        "Closed Won": 0.0,
        "Closed Lost": 0.0,
    }.get(op.stage, theta["base_prob_default"])
    
    
    
    
    revenue = getattr(op, "revenue", 1000.0) or 1000.0
    difficulty = getattr(op, "difficulty", 1.0) or 1.0

    difficulty_scaled = difficulty * (revenue / theta["revenue_base"]) ** theta["revenue_exponent"]

    sentiment = getattr(op, "sentiment", 0.0)
    momentum = derived_momentum(op)
    friction = derived_friction(op)

    prob = (
        stage_base
        - difficulty_scaled
        + theta["sentiment_beta_opportunity"] * sentiment
        + theta["momentum_beta_opportunity"] * momentum
        - theta["friction_beta_opportunity"] * friction
    )

    if op.personality:
        p = op.personality
        prob += (
            theta["personality_skepticism_beta"] * p.skepticism
            + theta["personality_urgency_beta"] * p.urgency
            + theta["personality_price_beta"] * p.price_sensitivity
        )

    prob += np.random.normal(0, theta["noise_sigma_opportunity"])
    return np.clip(prob, 0.0, 1.0)



# -----------------------------
# 2️⃣ compute_lead_probability
# -----------------------------
def compute_lead_probability(entity, rep=None) -> float:
    if not isinstance(entity, Lead) or entity.is_closed:
        return 0.0

    ms = getattr(entity, "micro_state", {})
    emails_sent = ms.get('send_email', 0)
    meetings_held = ms.get('hold_meeting', 0)
    follow_ups = ms.get('follow_up', 0)

    if emails_sent + meetings_held < theta["lead_min_engagement"]:
        return 0.0

    micro_score = (
        theta["micro_weight_email"] * emails_sent +
        theta["micro_weight_meeting"] * meetings_held +
        theta["micro_weight_followup"] * follow_ups
    )

    momentum = derived_momentum(entity)
    friction = derived_friction(entity)
    
    
    personality_factor = 0.0
    if entity.personality:
        p = entity.personality
        personality_factor = (
            theta["personality_skepticism_beta_lead"] * p.skepticism +
            theta["personality_urgency_beta_lead"] * p.urgency +
            theta["personality_price_beta_lead"] * p.price_sensitivity
        )

    revenue = getattr(entity, "revenue", 1000.0) or 1000.0
    difficulty = getattr(entity, "difficulty", 1.0) or 1.0

    difficulty_scaled = difficulty * (revenue / theta["revenue_base"]) ** theta["revenue_exponent"]
    sentiment_factor = np.clip(getattr(entity, "sentiment", 0) / theta["sentiment_scale"], -1,1) * theta["sentiment_beta_lead"]
    base_prob = theta["base_prob_lead_conversion"]

    
    
    
    prob = (
        base_prob
        + micro_score
        + theta["momentum_beta_lead"] * momentum
        - theta["friction_beta_lead"] * friction
        - difficulty_scaled
        + personality_factor
        + sentiment_factor
    )
    
    
#     print(
    
#         f'base: {base_prob}\n'
#         f'micro score: {micro_score}\n'
#         f'momentum: {theta["momentum_beta_lead"] * momentum}\n'
#         f'friction: {theta["friction_beta_lead"] * friction}\n'
#         f'difficulty: {difficulty_scaled}\n'
#         f'personality factor: {personality_factor}\n'
#         f'sentiment factor: {sentiment_factor}\n'
    
    
    
#     )
    
    
    
    prob *= theta["scale_factor_lead_conversion"]
    prob += np.random.normal(0, theta["noise_sigma_lead"])
    # print(prob)
    return np.clip(prob, 0.0, 1.0)

# # -----------------------------
# 5️⃣ prob_lost
# -----------------------------
def prob_lost(entity, rep=None) -> float:
    base = theta["base_prob_lost"]

    days_in_stage = getattr(entity, "days_in_stage", 0)
    days_since_touch = getattr(entity, "days_since_touch", 0)
    
    
    momentum = derived_momentum(entity)
    friction = derived_friction(entity)
    
    
    sentiment = getattr(entity, "sentiment", 0)
    stage = getattr(entity, "stage", "Lead")

    stage_factor = theta["stage_multipliers"].get(stage, 1.0)

    inactivity_factor = theta["inactivity_alpha"] * np.log1p(days_since_touch)
    stagnation_factor = theta["stagnation_alpha"] * np.log1p(days_in_stage)
    
    
    momentum_factor = theta["momentum_beta_lost"] * momentum
    friction_factor = theta["friction_beta_lost"] * friction

    prob = base + inactivity_factor + stagnation_factor + momentum_factor + friction_factor

    if getattr(entity, "personality", None):
        p = entity.personality
        prob *= (
            1
            + theta["personality_skepticism_beta_lost"] * p.skepticism
            + theta["personality_urgency_beta_lost"] * p.urgency
        )

    prob += np.random.normal(0, theta["noise_sigma_lost"])
    return np.clip(prob * stage_factor, 0.0, theta["max_prob_lost"])





def sigmoid(x):
    return 1 / (1 + np.exp(-x))




def compute_stage_progress_probability(entity):
    sentiment = entity.sentiment
    momentum = derived_momentum(entity)
    friction = derived_friction(entity)

    prob = (
        theta['base_prob_opportunity']
        + theta['sentiment_beta_opportunity'] * sentiment
        + theta['momentum_beta_opportunity'] * momentum
        - theta['friction_beta_opportunity'] * friction
    )

    return sigmoid(prob)


def compute_close_probability(entity):
    sentiment = entity.sentiment
    momentum = derived_momentum(entity)
    friction = derived_friction(entity)
    difficulty_scaled = entity.difficulty * (entity.revenue / theta["revenue_base"]) ** theta["revenue_exponent_macro"]
    score = (
        theta['base_prob_close']
        + theta['sentiment_beta_close'] * sentiment
        + theta['momentum_beta_close'] * momentum
        - theta['friction_beta_close'] * friction
        - difficulty_scaled
    )

    return sigmoid(score)


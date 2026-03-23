
theta = {
    # -----------------------------
    # Macro / Opportunity Probabilities
    # -----------------------------
    "base_prob_lead": 0.05,
    "base_prob_prospecting": 0.08,
    "base_prob_qualification": 0.04,
    "base_prob_proposal": 0.02,
    "base_prob_negotiation": 0.01,
    "base_prob_default": 0.05,           # fallback probability for unknown stages
    "macro_base_nudge": 0.15,
    "momentum_beta_macro": 0.75,
    "friction_beta_macro": 0.55,
    "sentiment_beta_macro": 0.2,
    "macro_noise_sigma": 0.02,

    # -----------------------------
    # Opportunity Dynamics
    # -----------------------------
    "base_prob_opportunity": 0.15,

    "revenue_base": 10_000_000,
    "revenue_exponent": 0.15,             # for compute_opportunity_probability
    "revenue_exponent_macro": 0.05,       # for prob_advance
    "momentum_beta_opportunity": 0.75,
    "friction_beta_opportunity": 0.5,
    "personality_skepticism_beta": -0.15,
    "personality_urgency_beta": 0.13,
    "personality_price_beta": -0.12,
    "sentiment_beta_opportunity": 0.2,
    "noise_sigma_opportunity": 0.05,

    # -----------------------------
    # Lead Probabilities
    # -----------------------------
    "base_prob_lead_conversion": 0.25,
    "micro_weight_email": 0.2,
    "micro_weight_meeting": 0.30,
    "micro_weight_followup": 0.5,
    "momentum_beta_lead": 0.6,
    "friction_beta_lead": 0.16,
    "personality_skepticism_beta_lead": -0.1,
    "personality_urgency_beta_lead": 0.15,
    "personality_price_beta_lead": -0.05,
    "sentiment_beta_lead": 0.1,
    "scale_factor_lead_conversion": 0.35,
    "noise_sigma_lead": 0.02,
    "lead_min_engagement": 2,             # minimum sum of emails + meetings

    # -----------------------------
    # Close / Lost Probabilities
    # -----------------------------
    "base_prob_close": 0.15,
    "momentum_beta_close": 0.95,
    "friction_beta_close": 0.45,
    "personality_skepticism_beta_close": -0.1,
    "personality_urgency_beta_close": 0.1,
    "personality_price_beta_close": -0.05,
    "sentiment_beta_close": 0.05,
    "noise_sigma_close": 0.02,

    "base_prob_lost": 0.035,
    "stage_loss_multiplier": {
        "Lead": 0.6,
        "Prospecting": 0.7,
        "Qualification": 0.9,
        "Proposal": 1.0,
        "Negotiation": 1.15,
    },
    "stage_multipliers": {
        "Lead": 0.6,
        "Prospecting": 0.7,
        "Qualification": 0.9,
        "Proposal": 1.0,
        "Negotiation": 1.15,
    },
    "inactivity_beta": 0.02,
    "stagnation_beta": 0.015,
    "momentum_beta_lost": 0.03,
    "friction_beta_lost": 0.03,
    "sentiment_beta_lost": -0.02,
    "personality_skepticism_beta_lost": 0.1,
    "personality_urgency_beta_lost": -0.05,
    "noise_sigma_lost": 0.005,
    "max_prob_lost": 0.35,

    # -----------------------------
    # Micro Actions / Behavioral Response
    # -----------------------------
    # Momentum base values
    "momentum_email_base": 0.07,
    "momentum_email_skepticism": -0.2,
    "momentum_email_urgency": 0.2,
    "momentum_email_strategy": 0.3,
    "momentum_email_risk": -0.1,

    "momentum_meeting_base": 0.09,
    "momentum_meeting_skepticism": -0.3,
    "momentum_meeting_urgency": 0.25,
    "momentum_meeting_strategy": 0.5,

    "momentum_call_base": 0.05,
    "momentum_call_skepticism": -0.15,
    "momentum_call_urgency": 0.1,
    "momentum_call_strategy": 0.2,

    "momentum_followup_base": 0.09,
    "momentum_followup_skepticism": -0.2,
    "momentum_followup_urgency": 0.15,
    "momentum_followup_strategy": 0.3,

    "momentum_internal_research_base": 0.002,
    "momentum_internal_research_skepticism": 0.0,
    "momentum_internal_research_urgency": 0.0,
    "momentum_internal_research_strategy": 0.0,

    "momentum_internal_base": 0.002,
    "momentum_internal_skepticism": 0.0,
    "momentum_internal_urgency": 0.0,
    "momentum_internal_strategy": 0.0,

    "momentum_research_base": 0.002,
    "momentum_research_skepticism": 0.0,
    "momentum_research_urgency": 0.0,
    "momentum_research_strategy": 0.0,

    "momentum_proposal_base": 0.06,
    "momentum_proposal_skepticism": -0.2,
    "momentum_proposal_urgency": 0.15,
    "momentum_proposal_strategy": 0.4,

    # Friction decay
    "friction_decay_email": 0.98,
    "friction_decay_meeting": 0.95,
    "friction_decay_call": 0.99,
    "friction_decay_followup": 0.97,
    "friction_decay_internal_research": 1.1,
    "friction_decay_proposal": 0.85,

    # Micro action momentum rep biases
    "momentum_email_rep_bias": 0.3,
    "momentum_meeting_rep_bias": 0.5,
    "momentum_call_rep_bias": 0.2,
    "momentum_followup_rep_bias": 0.3,
    "momentum_proposal_rep_bias": 0.4,

    # Micro action friction multipliers
    "friction_email_mult": 0.93,
    "friction_meeting_mult": 0.92,
    "friction_call_mult": 0.9,
    "friction_followup_mult": 0.9,
    "friction_internal_mult": 0.99,
    "friction_research_mult": 0.99,
    "friction_proposal_mult": 0.85,
    "friction_research_skepticism": 1.1,

    # Micro action rep / strategy scaling
    "momentum_meeting_focus": 0.5,
    "momentum_call_communicativeness": 0.2,
    "momentum_research_focus": 0.02,
    "momentum_internal_focus": 0.02,

    # Sentiment scaling
    "sentiment_scale": 5,

    # Urgency scaling across all actions
    "momentum_beta_urgency": 0.05,

    # Noise
    "noise_sigma_macro": 0.03,

    # Loss / decay hazard factors
    # Halved from 0.02/0.015: with the per-type damper fix the raw prob_lost
    # growth was still too aggressive for leads (90% dead by day 30). These
    # values give ~50% lead survival at day 30 for a neglected lead, which is
    # realistic — a cold lead should fade but not die in the first month.
    "inactivity_alpha": 0.010,
    "stagnation_alpha": 0.008,
    
    'momentum_carryover': 0.25,
    'friction_carryover': 0.15,
    "momentum_cap": 15,
    "friction_momentum_drag": 0.01,
}




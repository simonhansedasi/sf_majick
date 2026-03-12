from typing import Sequence, TypeVar, Callable, List
import random
import string
import uuid

import numpy as np
T = TypeVar('T')



# --- UTILS ---
def generate_id() -> str:
    """Generate a unique ID for simulation entities."""
    return str(uuid.uuid4())




# ---------------------------------------------------------------------
# Numeric Helpers
# ---------------------------------------------------------------------

def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    '''
    Restrict value to [low, high].
    '''
    if low > high:
        raise ValueError('Low bound cannot exceed high bound.')
    return max(low, min(high, value))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    '''
    Division that avoids ZeroDivisionError.
    '''
    if denominator == 0:
        return default
    return numerator / denominator


# ---------------------------------------------------------------------
# Weighted Selection
# ---------------------------------------------------------------------

def weighted_choice(
    items: Sequence[T],
    weight_fn: Callable[[T], float],
) -> T:
    '''
    Select a single item based on weights computed by weight_fn.

    All weights must be >= 0.
    At least one weight must be > 0.
    '''

    weights: List[float] = [max(0.0, weight_fn(item)) for item in items]

    total_weight = sum(weights)

    if total_weight <= 0:
        raise ValueError('All weights are zero; cannot perform weighted choice.')

    threshold = random.random() * total_weight
    cumulative = 0.0

    for item, weight in zip(items, weights):
        cumulative += weight
        if cumulative >= threshold:
            return item

    # Fallback (floating point safety)
    return items[-1]


# ---------------------------------------------------------------------
# Normalization Helpers
# ---------------------------------------------------------------------

def normalize(values: Sequence[float]) -> List[float]:
    '''
    Normalize a list of non-negative values to sum to 1.
    '''
    total = sum(values)

    if total <= 0:
        raise ValueError('Cannot normalize values with non-positive sum.')

    return [v / total for v in values]


def softmax(values: Sequence[float], temperature: float = 1.0) -> List[float]:
    '''
    Softmax transformation.
    Useful for probabilistic selection policies.
    '''

    if temperature <= 0:
        raise ValueError('Temperature must be > 0.')

    scaled = [v / temperature for v in values]
    max_val = max(scaled)

    # Numerical stability shift
    exp_vals = [pow(2.718281828459045, v - max_val) for v in scaled]
    total = sum(exp_vals)

    return [v / total for v in exp_vals]

def generate_random_leads(n: int, min_revenue: int = 100_000, max_revenue: int = 5_000_000) -> list:
    import string
    from .entities import Lead
    leads = []

    for _ in range(n):
        lead_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

        lead = Lead(
            id=lead_id,
            name=f"Contact_{lead_id}",
        )

        # assign personality if not already set
        if not hasattr(lead, "personality") or lead.personality is None:
            lead.personality = Lead.random_personality()

        leads.append(lead)
        # expected_revenue = np.radom
    return leads

# ---------------------------------------------------------------------
# Stage Cooldowns
# ---------------------------------------------------------------------
COOLDOWN_STAGE_MAP = {
    "Prospecting": 2,
    "Qualification": 3,
    "Proposal": 3,
    "Negotiation": 4,
    "Closed Won": 0,
    "Closed Lost": 0,
}

MICRO_REQUIREMENTS_BY_STAGE = {
    "Lead": {
        "and":[
            {
                "min_total":{
                    "actions":["research_account","send_email","make_call"],
                    "count":1
                }
            },
            {
                "or":[
                    {"research_account":1},
                    {"sequence":[{"send_email":1},{"make_call":1}]},
                    {"sequence":[{"make_call":1},{"send_email":1}]},
                    {"chance":0.40, "req":{"send_email":1}}
                ]
            }
        ]
    },

    # -------------------------
    # PROSPECTING
    # -------------------------

    "Prospecting": {
        "and":[
            {
                "min_total":{
                    "actions":["send_email","make_call","research_account"],
                    "count":2
                }
            },
            {
                "or":[
                    {"sequence":[{"send_email":1},{"make_call":1}]},
                    {"sequence":[{"research_account":1},{"send_email":1}]},
                    {"chance":0.35, "req":{"send_email":2}}
                ]
            }
        ]
    },

    # -------------------------
    # QUALIFICATION
    # -------------------------

    "Qualification": {
        "and":[
            {
                "min_total":{
                    "actions":["send_email","make_call","research_account","hold_meeting"],
                    "count":3
                }
            },
            {
                "or":[
                    {"sequence":[{"send_email":2},{"make_call":1},{"hold_meeting":1}]},
                    {"sequence":[{"research_account":1},{"hold_meeting":1}]},
                    {"sequence":[{"make_call":2},{"send_email":1}]},
                    {"chance":0.25, "req":{"hold_meeting":1}}
                ]
            }
        ]
    },

    # -------------------------
    # PROPOSAL
    # -------------------------

    "Proposal": {
        "and":[
            {"min_total":{
                "actions":["follow_up","hold_meeting","internal_prep","solution_design","stakeholder_alignment"],
                "count":2
            }},
            {
                "or":[
                    {"sequence":[{"solution_design":1},{"stakeholder_alignment":1}]},
                    {"sequence":[{"hold_meeting":1},{"follow_up":1},{"solution_design":1}]},
                    {"chance":0.2, "req":{"internal_prep":1}}
                ]
            },
            {"send_proposal":1}
        ]
    },

    # -------------------------
    # NEGOTIATION
    # -------------------------

    "Negotiation": {
        "and":[
            {"min_total":{
                "actions":["research_account","internal_prep","follow_up","hold_meeting","solution_design","stakeholder_alignment"],
                "count":3
            }},
            {
                "or":[
                    {"sequence":[{"solution_design":1},{"internal_prep":1},{"follow_up":1}]},
                    {"sequence":[{"hold_meeting":1},{"stakeholder_alignment":1}]},
                    {"sequence":[{"internal_prep":1},{"make_call":1},{"send_email":1}]},
                    {"chance":0.25, "req":{"follow_up":1}}
                ]
            },
            {"send_proposal":1}
        ]
    }

}




# --- PIPELINE STAGES ---
PIPELINE_STAGES: List[str] = [
    'Lead',
    'Prospecting',
    'Qualification',
    'Proposal',
    'Negotiation',
    'Closed Won',
    'Closed Lost',
    'Closed Converted'
]
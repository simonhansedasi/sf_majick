from dataclasses import dataclass
from typing import Dict, Callable, Optional, Any
import random
from .utils import clamp
# from .entities import Opportunity, Lead, MicroState
from .theta import theta
from .sentiment import apply_sentiment
# ---------------------------------------------------------------------
# Micro Action Definition
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class MicroAction:
    """
    Defines a micro action.

    - name: label
    - cost: attention cost
    - effect: function that mutates the entity
    """
    name: str
    cost: int
    effect: Callable[['Entity', 'SalesRep'], None]
    requirements: Optional[Dict[str, Any]] = None
    
    
    
# # # ---------------------------------------------------------------------
# # # Micro Effects
# # # ---------------------------------------------------------------------


def derived_momentum(entity, alpha: float = 0.4):
    """
    Compute latent momentum from recent sentiment deltas.
    
    Momentum is an EMA of last_sentiment_delta.
    If sentiment_history exists, use it.
    Otherwise fallback to last_sentiment_delta.
    """

    if hasattr(entity, "sentiment_history") and entity.sentiment_history:
        ema = 0.0
        for delta in entity.sentiment_history[-5:]:  # small window for stability
            ema = alpha * delta + (1 - alpha) * ema
        return ema

    # Fallback
    return getattr(entity, "last_sentiment_delta", 0.0)

def derived_friction(entity, window: int = 5):
    """
    Friction represents accumulated negative sentiment pressure.
    
    Computed as the magnitude of negative rolling average sentiment.
    """

    if hasattr(entity, "sentiment_history") and entity.sentiment_history:
        recent = entity.sentiment_history[-window:]
        avg = sum(recent) / len(recent)
        return max(0.0, -avg)

    # Fallback: if no history, derive from current sentiment
    return max(0.0, -entity.sentiment)


def send_email(entity, rep) -> None:
    entity.micro_state.record_action('send_email')
    entity.days_since_touch = 0
    entity.touched_today = True
    apply_sentiment("email", rep, entity)
    
def hold_meeting(entity, rep) -> None:
    entity.micro_state.record_action('hold_meeting')
    entity.days_since_touch = 0
    entity.touched_today = True
    apply_sentiment("meeting", rep, entity)
    
def make_call(entity, rep) -> None:
    entity.micro_state.record_action('make_call')
    entity.days_since_touch = 0
    entity.touched_today = True
    apply_sentiment("call", rep, entity)
    
def follow_up(entity, rep) -> None:
    entity.micro_state.record_action('follow_up')
    entity.days_since_touch = 0
    entity.touched_today = True
    apply_sentiment("follow_up", rep, entity)
    
def research_account(entity, rep) -> None:
    entity.micro_state.record_action('research_account')
    apply_sentiment("research_account", rep, entity)
    
def internal_prep(entity, rep) -> None:
    entity.micro_state.record_action('internal_prep')
    apply_sentiment("internal_prep", rep, entity)
    
def send_proposal(entity, rep) -> None:
    entity.micro_state.record_action('send_proposal')
    entity.days_since_touch = 0
    entity.touched_today = True
    apply_sentiment("send_proposal", rep, entity)
    
def solution_design(entity, rep) -> None:
    entity.micro_state.record_action('solution_design')
    apply_sentiment("solution_design", rep, entity)


def stakeholder_alignment(entity, rep) -> None:
    entity.micro_state.record_action('stakeholder_alignment')
    apply_sentiment("stakeholder_alignment", rep, entity)


# ---------------------------------------------------------------------
# Action Registry
# ---------------------------------------------------------------------
MICRO_ACTIONS = {

    "send_email": MicroAction(
        "send_email",
        15,
        send_email,
        requirements=None
    ),

    "make_call": MicroAction(
        "make_call",
        15,
        make_call,
        requirements=None
    ),

    "research_account": MicroAction(
        "research_account",
        25,
        research_account,
        requirements={
            "or":[
                {"chance":0.60, "req":{}},   # proactive research
                {"send_email":1},
                {"make_call":1}
            ]
        }
    ),
    
    "internal_prep": MicroAction(
        "internal_prep",
        25,
        internal_prep,
        requirements={
            "or":[
                {"hold_meeting":1},
                {"follow_up":1},
                {"solution_design":1}
            ]
        }
    ),

    "solution_design": MicroAction(
        "solution_design",
        35,
        solution_design,
        requirements={
            "or":[
                {"internal_prep":1},
                {"hold_meeting":1},
                {"follow_up":1}
            ]
        }
    ),

    "stakeholder_alignment": MicroAction(
        "stakeholder_alignment",
        40,
        stakeholder_alignment,
        requirements={
            "or":[
                {"solution_design":1},
                {"min_total":{
                    "actions":["make_call","send_email","follow_up"],
                    "count":4
                }}
            ]
        }
    ),

    "hold_meeting": MicroAction(
        "hold_meeting",
        40,
        hold_meeting,
        requirements={
            "or":[
                {
                    "and":[
                        {"research_account":1},
                        {"min_total":{
                            "actions":["send_email","make_call"],
                            "count":3
                        }}
                    ]
                },
                {
                    "sequence":[
                        {"send_email":2},
                        {"make_call":1}
                    ]
                },
                {
                    "chance":0.015,
                    "req":{"make_call":2}
                }
            ]
        }
    ),

    "follow_up": MicroAction(
        "follow_up",
        30,
        follow_up,
        requirements={
            "or":[
                {
                    "and":[
                        {"hold_meeting":1},
                        {"min_total":{
                            "actions":["send_email","make_call"],
                            "count":3
                        }}
                    ]
                },
                {
                    "sequence":[
                        {"hold_meeting":1},
                        {"internal_prep":1},
                        {"send_email":1}
                    ]
                },
                {
                    "chance":0.012,
                    "req":{
                        "and":[
                            {"send_email":4},
                            {"make_call":2}
                        ]
                    }
                }
            ]
        }
    ),

    "send_proposal": MicroAction(
        "send_proposal",
        50,
        send_proposal,
        requirements={
            "or":[
                # Standard B2B progression
                {
                    "sequence":[
                        {"research_account":1},
                        {"send_email":18},
                        {"make_call":17},
                        {"hold_meeting":3},
                        {"follow_up":3},
                        {"internal_prep":2},
                        {"solution_design":1},
                        {"stakeholder_alignment":1}
                    ]
                },
                # Enterprise consultative path
                {
                    "sequence":[
                        {"internal_prep":5},
                        {"send_email":19},
                        {"make_call":16},
                        {"hold_meeting":3},
                        {"follow_up":3},
                        {"solution_design":1}
                    ]
                },
                # Long nurture conversion
                {
                    "sequence":[
                        {"send_email":28},
                        {"make_call":29},
                        {"follow_up":5},
                        {"hold_meeting":2},
                        {"solution_design":1}
                    ]
                },
                # Rare stochastic close
                {
                    "chance":0.002,
                    "req":{
                        "and":[
                            {"hold_meeting":10},
                            {"follow_up":3},
                            {"make_call":27},
                            {"send_email":44},
                            {"stakeholder_alignment":1}
                        ]
                    }
                }
            ]
        }
    ),
}
# ---------------------------------------------------------------------
# Execution Engine
# ---------------------------------------------------------------------
def execute_micro_action(entity, action_name: str, available_attention: int, rep) -> Dict:

    action = MICRO_ACTIONS[action_name]

    # -----------------------------
    # CHECK COOLDOWN
    # -----------------------------
    if not hasattr(entity, "cooldowns"):
        entity.cooldowns = {}  # track per action

    if entity.cooldowns.get(action_name, 0) > 0:
        # Cannot perform yet
        return {
            'success': False,
            'action': action_name,
            'cost': 0,
            'remaining_attention': available_attention,
            'reason': f'{action_name} on cooldown ({entity.cooldowns[action_name]} interactions remaining)'
        }

    # -----------------------------
    # Check dependencies / attention
    # -----------------------------
    can_do = True
    if hasattr(entity.micro_state, "can_perform"):
        can_do = entity.micro_state.can_perform(action_name)

    if not can_do:
        return {
            'success': False,
            'action': action_name,
            'cost': 0,
            'remaining_attention': available_attention,
            'reason': 'Requirements not met'
        }

    if available_attention < action.cost:
        return {
            'success': False,
            'action': action_name,
            'cost': action.cost,
            'remaining_attention': available_attention,
            'reason': 'Insufficient attention'
        }

    # -----------------------------
    # PERFORM ACTION
    # -----------------------------
    remaining_attention = available_attention - action.cost
    action.effect(entity, rep)

    # consume requirements
    reqs = getattr(action, "requirements", None)
    entity.micro_state.consume_requirements(reqs)

    # -----------------------------
    # SET COOLDOWN if applicable
    # -----------------------------
    if hasattr(action, "cooldown") and action.cooldown > 0:
        entity.cooldowns[action_name] = action.cooldown

    return {
        'success': True,
        'action': action_name,
        'cost': action.cost,
        'remaining_attention': remaining_attention,
        'sentiment_delta': getattr(entity, 'last_sentiment_delta', 0.0),
        'sentiment_total': getattr(entity, 'sentiment', 0.0),
        'reason': None
    }

def micro_actions_allowed(entity):
    """
    Returns a list of micro action functions this entity can receive.
    """
    return [action.effect for action in MICRO_ACTIONS.values()]

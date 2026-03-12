from dataclasses import dataclass
from typing import Callable, Dict, Optional, List
import random
import numpy as np
from .entities import Lead, Opportunity, Account
from .utils import clamp, MICRO_REQUIREMENTS_BY_STAGE, generate_id, PIPELINE_STAGES, COOLDOWN_STAGE_MAP
from .micro_actions import derived_momentum, derived_friction
from .theta import theta
from .economics import CommissionPlan
from .probabilities import dynamic_closed_lost_probability, compute_opportunity_probability, compute_lead_probability, prob_lost, compute_stage_progress_probability, compute_close_probability
# ---------------------------------------------------------------------
# Macro Action Definition
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class MacroAction:
    """
    Defines a macro event attempt.

    - name: label for telemetry
    - condition: determines if macro is eligible
    - probability: computes probability of firing
    - effect: performs advancement
    """
    name: str
    condition: Callable[[object], bool]           # Accepts any entity
    probability: Callable[[object, 'SalesRep'], float]
    effect: Callable[[object, 'SalesRep', Optional[List]], Optional[str]]



# --------------------------------------------------------------------- 
# Conditions 
# --------------------------------------------------------------------- 
def can_attempt_advancement(entity):
    if not entity.can_advance or entity.stage in ("Closed Won", "Closed Lost", "Closed Converted", "Closed Dead"): 
        return False 
    
    requirements = get_scaled_micro_requirements(entity, theta)

    if requirements is None:
        return True

    return requirements_satisfied(requirements, entity.micro_state)


def can_attempt_close(entity: Opportunity) -> bool:
    """Only Negotiation-stage opportunities can close.""" 
    return entity.stage == "Negotiation" and not entity.is_closed 


# ---------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------
def advance_stage(
    entity: Opportunity, 
    rep: 'SalesRep',
    accounts: Optional[List] = None,
    opportunities: Optional[List] = None
) -> Optional[str]:
    """Advance an opportunity one stage, applying cooldown."""
    if not can_attempt_advancement(entity):
        return None

    old_stage = entity.stage

    entity.advance_stage()
    # consume_micro_for_stage(entity, entity.stage)

    apply_cooldown(entity)
    return old_stage


def attempt_close(entity, rep=None, accounts=None, opportunities=None):
    """
    Attempt to close a Negotiation-stage Opportunity.
    Uses prob_close to randomly determine outcome.
    """
    if not isinstance(entity, Opportunity) or entity.stage != "Negotiation":
        return None

    p_win = compute_close_probability(entity)
    if random.random() < p_win:
        # entity.stage = "Closed Won"
        entity.mark_won()

        result = "won"
    else:
        entity.stage = "Closed Lost"
        result = "lost"
        entity.mark_lost()
    # optional: update commissions if Closed Won
    if entity.stage == "Closed Won" and hasattr(entity, "revenue") and rep:
        commission = CommissionPlan.commission_on(entity.revenue, rep.comp_rate)
        rep.add_commission(commission)
        entity.commission = commission

    return result


def convert_lead(
    entity: Lead,
    rep: 'SalesRep',
    accounts: List[Account],
    opportunities: List[Opportunity],
) -> Optional[Opportunity]:
    if not entity.can_convert():
        return None

    new_account = Account(
        id=generate_id(),
        name=entity.account_name,
        rep_id=rep.id
    )

    accounts.append(new_account)

    
    new_op = new_account.create_opportunity()
    
    new_op.sentiment = 1
    new_op.last_sentiment_delta = 0.5
    
    
    opportunities.append(new_op)

    entity.mark_converted()
    
    return new_account, new_op



def _close_lost_effect(op, rep=None, day=None, accounts = None, opportunities = None):
    old_stage = op.stage
    op.mark_lost()  # call the new setter method


# ---------------------------------------------------------------------
# Macro Registry
# ---------------------------------------------------------------------
MACRO_ACTIONS = [
    MacroAction(
        name='Advance Stage',
        condition=can_attempt_advancement,
        probability=compute_stage_progress_probability,
        effect=advance_stage
    ),
    MacroAction(
        name='Close Opportunity',
        condition=can_attempt_close,
        probability=compute_close_probability,
        effect=attempt_close
    ),
MacroAction(
    name='Lead Conversion',
    condition=lambda e: (
        isinstance(e, Lead)
        and not e.is_closed
        and getattr(e, "micro_state", {}).get('send_email', 0) >= 3
        and getattr(e, "micro_state", {}).get('hold_meeting', 0) >= 3
        and getattr(e, "micro_state", {}).get('make_call', 0) >= 2
        and getattr(e, "micro_state", {}).get('internal_prep', 0) >= 1
        # and getattr(e, "micro_state", {}).get('hold_meeting', 0) >= 3
    ),
    probability=compute_lead_probability,
    effect=convert_lead
),
    
    MacroAction(
        name='Decay Lost',
        condition=lambda e: (
            isinstance(e, Lead) and               # only Leads
            not e.is_closed and                    # not already closed
            getattr(e, 'sentiment', 0) < -1 and # negative sentiment threshold
            getattr(e, 'days_since_touch', 0) > 14 # days since last touch
        ),       
        probability=prob_lost,
        effect=_close_lost_effect
    ),
]


# ---------------------------------------------------------------------
# Macro Engine
# ---------------------------------------------------------------------
def attempt_macro_for_entity(entity, rep: 'SalesRep' = None,
                             accounts: Optional[list] = None,
                             opportunities: Optional[list] = None) -> list:
    """
    Attempt all macros in order:
      1. Decay / Lost
      2. Lead Conversion
      3. Close Opportunity
      4. Stage Advancement

    Uses sentiment-driven derived variables. Returns list of macro results for telemetry.
    """
    macros_fired = []
    old_stage = getattr(entity, "stage", getattr(entity, "lead_stage", "Lead"))

    # Skip closed entities
    if getattr(entity, "is_closed", False):
        return []

    # Cache derived variables for telemetry
    old_momentum = derived_momentum(entity)
    old_friction = derived_friction(entity)

    # -----------------------------
    # 1️⃣ Decay / Lost
    # -----------------------------
    if isinstance(entity, (Lead, Opportunity)):
        loss_prob = prob_lost(entity, rep)
        if random.random() < max(0, loss_prob - 0.25):  # optional decay adjustment
            result = _close_lost_effect(entity, rep, accounts=accounts, opportunities=opportunities)
            macros_fired.append({
                'advanced': getattr(entity, "stage", old_stage) != old_stage,
                'old_stage': old_stage,
                'new_stage': getattr(entity, "stage", old_stage),
                'macro_name': 'Decay / Lost',
                'probability': loss_prob,
                'result': result,
                'momentum': derived_momentum(entity),
                'friction': derived_friction(entity),
                'momentum_delta': derived_momentum(entity) - old_momentum,
                'friction_delta': derived_friction(entity) - old_friction
            })
            old_stage = getattr(entity, "stage", old_stage)

    # -----------------------------
    # 2️⃣ Lead Conversion
    # -----------------------------
    if isinstance(entity, Lead) and not getattr(entity, "is_closed", False):
        convert_prob = compute_lead_probability(entity) + 0.3  # optional boost
        if random.random() < convert_prob:
            result = convert_lead(entity, rep, accounts, opportunities)
            advanced = True
        else:
            entity.mark_lost()
            result = None
            advanced = False

        macros_fired.append({
            'advanced': advanced,
            'old_stage': old_stage,
            'new_stage': getattr(entity, "stage", old_stage),
            'macro_name': 'Lead Conversion',
            'probability': convert_prob,
            'result': {
                "account": result[0] if result else None,
                "opportunity": result[1] if result else None
            },
            'momentum': derived_momentum(entity),
            'friction': derived_friction(entity),
            'momentum_delta': derived_momentum(entity) - old_momentum,
            'friction_delta': derived_friction(entity) - old_friction
        })
        old_stage = getattr(entity, "stage", old_stage)

    # -----------------------------
    # 3️⃣ Close Opportunity
    # -----------------------------
    if isinstance(entity, Opportunity) and getattr(entity, "stage", None) == "Negotiation":
        close_prob = compute_close_probability(entity)
        if random.random() < close_prob:
            result = attempt_close(entity, rep, accounts, opportunities)
            advanced = getattr(entity, "stage", old_stage) != old_stage
            macros_fired.append({
                'advanced': advanced,
                'old_stage': old_stage,
                'new_stage': getattr(entity, "stage", old_stage),
                'macro_name': 'Close Opportunity',
                'probability': close_prob,
                'result': result,
                'momentum': derived_momentum(entity),
                'friction': derived_friction(entity),
                'momentum_delta': derived_momentum(entity) - old_momentum,
                'friction_delta': derived_friction(entity) - old_friction
            })
            old_stage = getattr(entity, "stage", old_stage)

    # -----------------------------
    # 4️⃣ Stage Advancement
    # -----------------------------
    if isinstance(entity, Opportunity):
        advance_prob = compute_stage_progress_probability(entity)
        if random.random() < advance_prob:
            result = advance_stage(entity, rep, accounts, opportunities)
            advanced = getattr(entity, "stage", old_stage) != old_stage
            macros_fired.append({
                'advanced': advanced,
                'old_stage': old_stage,
                'new_stage': getattr(entity, "stage", old_stage),
                'macro_name': 'Advance Stage',
                'probability': advance_prob,
                'result': result,
                'momentum': derived_momentum(entity),
                'friction': derived_friction(entity),
                'momentum_delta': derived_momentum(entity) - old_momentum,
                'friction_delta': derived_friction(entity) - old_friction
            })
            old_stage = getattr(entity, "stage", old_stage)

    return macros_fired

# # ---------------------------------------------------------------------
# # Utilities
# # ---------------------------------------------------------------------
def scale_requirement_tree(req, scale):
    if req is None:
        return None

    if not isinstance(req, dict):
        raise ValueError(f"Invalid requirement node: {req}")

    # -------------------------
    # AND node
    # -------------------------
    if "and" in req:
        return {"and": [scale_requirement_tree(r, scale) for r in req["and"]]}

    # -------------------------
    # OR node
    # -------------------------
    if "or" in req:
        return {"or": [scale_requirement_tree(r, scale) for r in req["or"]]}

    # -------------------------
    # CHANCE node
    # -------------------------
    if "chance" in req:
        # print(req)
        return {"chance": req["chance"], "req": scale_requirement_tree(req["req"], scale)}

    # -------------------------
    # MIN TOTAL node
    # -------------------------
    if "min_total" in req:
        node = req["min_total"]
        return {
            "min_total": {
                "actions": node["actions"],
                "count": max(1, int(round(node["count"] * scale))),
            }
        }

    # -------------------------
    # SEQUENCE node
    # -------------------------
    if "sequence" in req:
        seq = req["sequence"]
        # scale each element in the sequence (each element is a dict of action counts)
        scaled_seq = []
        for elem in seq:
            if not isinstance(elem, dict):
                raise ValueError(f"Invalid sequence element: {elem}")
            scaled_elem = {}
            for action, count in elem.items():
                if not isinstance(count, (int, float)):
                    raise ValueError(f"Invalid sequence element count: {action}: {count}")
                scaled_elem[action] = max(1, int(round(count * scale)))
            scaled_seq.append(scaled_elem)
        return {"sequence": scaled_seq}

    # -------------------------
    # LEAF action counts
    # -------------------------
    node_keys = {"and", "or", "chance", "min_total", "sequence"}
    scaled = {}
    for action, count in req.items():
        if action in node_keys:
            continue
        if not isinstance(count, (int, float)):
            raise ValueError(f"Invalid leaf requirement: {action}: {count}")
        scaled[action] = max(1, int(round(count * scale)))

    return scaled






def get_scaled_micro_requirements(entity, theta):

    base_requirements = MICRO_REQUIREMENTS_BY_STAGE.get(entity.stage)

    if base_requirements is None:
        return None

    difficulty_scaled = entity.difficulty * (
        entity.revenue / theta["revenue_base"]
    ) ** theta["revenue_exponent"]
    # easier entities require fewer actions
    scale = 1.0 + difficulty_scaled

    return scale_requirement_tree(base_requirements, scale)



def requirements_satisfied(req, micro_state) -> bool:
    if req is None:
        return True

    if not isinstance(req, dict):
        raise ValueError(f"Invalid requirement node: {req}")

    # -------------------------
    # AND
    # -------------------------
    if "and" in req:
        return all(requirements_satisfied(r, micro_state) for r in req["and"])

    # -------------------------
    # OR
    # -------------------------
    if "or" in req:
        return any(requirements_satisfied(r, micro_state) for r in req["or"])

    # -------------------------
    # CHANCE node
    # -------------------------
    if "chance" in req:
        sub = req.get("req")
        if sub is None:
            raise ValueError(f"Chance node missing 'req': {req}")
        # Check requirement only probabilistically
        if random.random() < req["chance"]:
            return requirements_satisfied(sub, micro_state)
        return False

    # -------------------------
    # MIN TOTAL node
    # -------------------------
    if "min_total" in req:
        data = req["min_total"]
        actions = data["actions"]
        count = data["count"]
        total = sum(getattr(micro_state, a, 0) for a in actions)
        return total >= count

    # -------------------------
    # SEQUENCE node
    # -------------------------
    if "sequence" in req:
        seq = req["sequence"]
        if not hasattr(micro_state, "history"):
            return False
        history = micro_state.history
        pos = 0
        for action in history:
            needed_action = list(seq[pos].keys())[0]
            if action == needed_action:
                pos += 1
                if pos == len(seq):
                    return True
        return False

    # -------------------------
    # FLAT leaves
    # -------------------------
    node_keys = {"and", "or", "chance", "min_total", "sequence"}
    for action_name, count in req.items():
        if action_name in node_keys:
            continue
        if not isinstance(count, (int, float)):
            raise ValueError(f"Invalid leaf requirement: {action_name}: {count}")
        if getattr(micro_state, action_name, 0) < count:
            return False

    return True

def apply_cooldown(entity: Opportunity):
    """Set cooldown days based on the entity's current stage."""
    entity.micro_state.days_until_next_stage = COOLDOWN_STAGE_MAP.get(entity.stage, 2)


    
    
def decrement_cooldowns(opportunities):
    """
    Call this once per day in the simulation loop to reduce cooldowns.
    """
    for op in opportunities:
        if op.micro_state.days_until_next_stage > 0:
            op.micro_state.days_until_next_stage -= 1




            
            
            
            

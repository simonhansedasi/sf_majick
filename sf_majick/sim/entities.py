from dataclasses import dataclass, field
from typing import List, Optional
import random
import copy
import numpy as np
from .economics import CommissionPlan
from .theta import theta
from .sentiment import apply_sentiment
from .micro_actions import MICRO_ACTIONS
from .utils import generate_id, PIPELINE_STAGES




# --- MICROSTATE ---
@dataclass
class MicroState:
    send_email: int = 0
    make_call: int = 0
    hold_meeting: int = 0
    follow_up: int = 0
    send_proposal: int = 0
    research_account: int = 0
    internal_prep: int = 0
    days_until_next_stage: int = 0
    solution_design: int = 0
    stakeholder_alignment: int = 0
    
    
    
    import random

    def meets_requirements_prob(self, req, base_prob=0.2):
        """
        Returns True if:
        - Requirements are fully met, or
        - Requirements are partially met, with probability based on progress
        """
        if self.meets_requirements(req):
            return True
        
        # Compute partial progress ratio (0..1)
        progress_ratio = self.compute_progress_ratio(req)
        # Scale probability
        prob = base_prob + 0.8 * progress_ratio
        return random.random() < prob
    
    
    def compute_progress_ratio(self, req) -> float:
        """
        Returns fraction of requirements satisfied.
        For AND: average of sub-requirements
        For OR: max of sub-requirements
        For flat: fraction of action counts completed
        """
        if req is None:
            return 1.0
        if "and" in req:
            return sum(self.compute_progress_ratio(r) for r in req["and"]) / len(req["and"])
        if "or" in req:
            return max(self.compute_progress_ratio(r) for r in req["or"])
        # flat requirement
        ratios = []
        for action_name, count in req.items():
            actual = self.get(action_name, 0)
            ratios.append(min(actual / count, 1.0))
        return sum(ratios) / len(ratios)
    
    
    import random

    def meets_requirements(self, req):
        if req is None:
            return True

        if not isinstance(req, dict):
            raise ValueError(f"Invalid requirement format: {req}")

        # -------------------------
        # AND node
        # -------------------------
        if "and" in req:
            return all(self.meets_requirements(r) for r in req["and"])

        # -------------------------
        # OR node
        # -------------------------
        if "or" in req:
            return any(self.meets_requirements(r) for r in req["or"])

        # -------------------------
        # CHANCE node
        # -------------------------
        if "chance" in req:
            p = req["chance"]
            sub = req.get("req", None)  # make sure matches scaled tree
            if sub is None:
                raise ValueError(f"Chance node missing 'req': {req}")
            if random.random() < p:
                return self.meets_requirements(sub)
            return True  # If chance fails, we treat requirement as "skipped"

        # -------------------------
        # MIN TOTAL node
        # -------------------------
        if "min_total" in req:
            data = req["min_total"]
            actions = data["actions"]
            count = data["count"]
            total = sum(self.get(a, 0) for a in actions)
            return total >= count

        # -------------------------
        # SEQUENCE node
        # -------------------------
        if "sequence" in req:
            seq = req["sequence"]
            if not hasattr(self, "history"):
                return False
            history = self.history
            pos = 0
            for action in history:
                needed_action = list(seq[pos].keys())[0]
                if action == needed_action:
                    pos += 1
                    if pos == len(seq):
                        return True
            return False

        # -------------------------
        # LEAF: flat action counts
        # -------------------------
        # Only include keys that are not node types
        node_keys = {"and", "or", "chance", "min_total", "sequence"}
        for action_name, count in req.items():
            if action_name in node_keys:
                continue  # already handled above
            if not isinstance(count, (int, float)):
                raise ValueError(f"Invalid leaf requirement: {action_name}: {count}")
            actual_count = self.get(action_name, 0)
            if actual_count < count:
                return False

        return True
    
    
    
    
            
    def can_perform(self, action_name: str) -> bool:
        from .micro_actions import MICRO_ACTIONS
        action = MICRO_ACTIONS.get(action_name)
        if not action:
            return False

        # Stage cooldown
        if self.days_until_next_stage > 0 and action_name not in {
            "send_email", "make_call", "internal_prep", "research_account"
        }:
            return False

        # Check requirements recursively
        reqs = getattr(action, "requirements", None)
        return self.meets_requirements(reqs)
    
    
    
    def consume_requirements(self, req):
        if req is None:
            return

        if not isinstance(req, dict):
            raise ValueError(f"Invalid requirement node: {req}")
            for r in req["or"]:
                if self.meets_requirements(r):
                    self.consume_requirements(r)
                    return
            # if none are met, do nothing
            return
        # -------------------------
        # AND node
        # -------------------------
        if "and" in req:
            for r in req["and"]:
                if self.meets_requirements(r):
                    self.consume_requirements(r)
                    return
            # if none are met, do nothing
            return
        # -------------------------
        # OR node
        # -------------------------
        if "or" in req:
            # pick the first sub-requirement that is met
            options = list(req["or"])
            random.shuffle(options)

            for r in options:
                self.consume_requirements(r)
            return

        # -------------------------
        # CHANCE node
        # -------------------------
        if "chance" in req:
            sub = req.get("req")
            if sub and random.random() < req["chance"]:
                self.consume_requirements(sub)
            return

        # -------------------------
        # MIN TOTAL node
        # -------------------------
        if "min_total" in req:
            # consume proportionally from actions until count is reached
            data = req["min_total"]
            actions = data["actions"]
            count = data["count"]
            # sum current available touches
            total_available = sum(self.get(a, 0) for a in actions)
            to_consume = min(count, total_available)
            # simple proportional consumption
            while to_consume > 0:
                for a in actions:
                    current = self.get(a, 0)
                    if current > 0:
                        setattr(self, a, current - 1)
                        to_consume -= 1
                        if to_consume == 0:
                            break
                # setattr(self, a, current - take)
                # to_consume -= take
                # if to_consume <= 0:
                #     break
            return

        # -------------------------
        # SEQUENCE node
        # -------------------------
        if "sequence" in req:
            seq = req["sequence"]

            # Only consume if the sequence is actually satisfied
            if self.meets_requirements({"sequence": seq}):
                for elem in seq:
                    self.consume_requirements(elem)

            return

        # -------------------------
        # LEAF node: flat action counts
        # -------------------------
        node_keys = {"and", "or", "chance", "min_total", "sequence"}
        for action_name, count in req.items():
            if action_name in node_keys:
                continue
            if not isinstance(count, (int, float)):
                raise ValueError(f"Invalid leaf requirement: {action_name}: {count}")
            current = self.get(action_name, 0)
            setattr(self, action_name, max(0, current - count))
            
            
    
    def get(self, key: str, default=0) -> int:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> int:
        return getattr(self, key, 0)

    def __setitem__(self, key: str, value: int):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            raise ValueError(f"Unknown micro action type: {key}")
            
    def record_action(self, action_type: str, count: int = 1):
        if hasattr(self, action_type):
            setattr(self, action_type, getattr(self, action_type) + count)

            # ensure history exists
            if not hasattr(self, "history"):
                self.history = []

            for _ in range(count):
                self.history.append(action_type)

        else:
            raise ValueError(f"Unknown micro action type: {action_type}")

    def copy(self):
        new_entity = self.__class__.__new__(self.__class__)  # skip __init__
        new_entity.__dict__.update(self.__dict__)
        return new_entity
    def copy_for_simulation(entity):
        new_entity = entity.__class__.__new__(entity.__class__)
        # shallow copy other attributes
        for k, v in entity.__dict__.items():
            if k == "micro_state":
                new_entity.micro_state = copy.deepcopy(v)  # <-- deep copy MicroState
            else:
                setattr(new_entity, k, v)
        return new_entity
# --- BASE ENTITY ---
@dataclass
class SimEntity:
    account_id: str = ''
    id: str = field(default_factory=generate_id)
    micro_state: MicroState = field(default_factory=MicroState)
    # momentum: float = 0.0
    # friction: float = 0.0
    stage_advanced_today: bool = False
    difficulty: float = None

    def reset_daily_flags(self) -> None:
        self.stage_advanced_today = False


@dataclass
class LeadPersonality:
    name: str
    openness: float
    urgency: float
    skepticism: float
    price_sensitivity: float
    
    
@dataclass  # or remove frozen=True if it exists
class Lead:
    id: str
    name: str = ""
    stage: str = "Lead"
    # is_closed: bool = False
    rep_id: Optional[str] = None
    current_rep: Optional[object] = None
    micro_state: object = field(default_factory=MicroState)
    sentiment: float = 0.0
    last_sentiment_delta: float = 0.0
    sentiment_history: list = field(default_factory=list)
    revenue: float = None
    commission: float = None
    difficulty: float = None
    account_name: str = ''
    personality: Optional[LeadPersonality] = None
    stage_advanced_today: bool = False
    days_in_stage: int = 0
    days_since_touch: int = 0
    touched_today: bool = False

    def __post_init__(self):
        # Randomize revenue if needed
        if self.revenue is None:
            # self.revenue = random.randint(10_000, 500_000)
            
            
            
            # new log-normal line
            # mean=0, sigma=0.6 gives a realistic spread; scale to the mid-point ~250k
            base = 350_000  # center of revenue
            sigma = 0.6     # controls spread / skew
            self.revenue = base * np.random.lognormal(mean=3, sigma=sigma)

            # optional: clamp to min/max if you want hard bounds
            # self.revenue = max(15_000, min(self.revenue, 1_750_000))
            # print(self.revenue)
            
            
            
            
            
            
            
#         # Randomize initial momentum & friction
#         self.momentum = random.uniform(0.0, 0.1)
#         self.friction = random.uniform(0.0, 0.05)
#         self.sentiment_history = []
        
        
        
    def can_convert(self) -> bool:
        """
        Determines if the lead is eligible for conversion to opportunity/account.
        """
        return (
            not self.is_closed
            and self.stage in ("Lead")
        )
        
        
        
        
    @property
    def is_closed(self) -> bool:
        return self.stage in ("Closed Won", "Closed Lost", 'Closed Converted', 'Closed Dead')

    @property
    def stage_index(self) -> int:
        return PIPELINE_STAGES.index(self.stage)

    @property
    def can_advance(self) -> bool:
        return (not self.is_closed) and (not self.stage_advanced_today) and (self.stage_index < len(PIPELINE_STAGES) - 3)

    @staticmethod
    def random_personality() -> LeadPersonality:
        archetypes = [
            "Analytical Skeptic",
            "Urgent Pragmatist",
            "Price-Sensitive Opportunist",
            "Easy-Going Follower"
        ]
        weights = [0.3, 0.4, 0.2, 0.1]
        selected = random.choices(archetypes, weights=weights, k=1)[0]
        params_map = {
            "Analytical Skeptic": {"openness":0.4, "urgency":0.2, "skepticism":0.8, "price_sensitivity":0.5},
            "Urgent Pragmatist": {"openness":0.7, "urgency":0.9, "skepticism":0.3, "price_sensitivity":0.4},
            "Price-Sensitive Opportunist": {"openness":0.6, "urgency":0.5, "skepticism":0.5, "price_sensitivity":0.9},
            "Easy-Going Follower": {"openness":0.8, "urgency":0.6, "skepticism":0.2, "price_sensitivity":0.3},
        }
        return LeadPersonality(name=selected, **params_map[selected])

    def assign_commission(self, plan: CommissionPlan):
        self.commission = np.round(plan.commission_on(self.revenue), 2)

    def advance_stage(self) -> Optional[str]:
        if self.is_closed or self.stage_advanced_today or self.stage == "Negotiation":
            return None
        next_index = self.stage_index + 1
        if next_index >= len(PIPELINE_STAGES):
            return None
        self.stage = PIPELINE_STAGES[next_index]
        self.stage_advanced_today = True
        self.days_in_stage = 0

        return self.stage

    def mark_lost(self):
        if not self.is_closed:
            self.stage = "Closed Lost"

    def mark_won(self):
        if not self.is_closed:
            self.stage = "Closed Won"
            
    def mark_converted(self):
        if not self.is_closed:
            self.stage = 'Closed Converted'

    def force_close(self, won: bool) -> str:
        if self.is_closed:
            return self.stage
        self.stage = "Closed Won" if won else "Closed Lost"
        self.stage_advanced_today = True
        self.days_in_stage = 0
        return self.stage
    
    
    

    def apply_behavioral_response(self, rep, action_type, theta=None):
        """
        Update entity (Lead or Opportunity) in response to a micro-action.
        Records the micro-action in MicroState and updates sentiment.
        Momentum and friction are derived dynamically elsewhere.
        """

        # 1️⃣ Record micro-action directly if MicroState has the attribute
        if hasattr(self, "micro_state") and hasattr(self.micro_state, action_type):
            self.micro_state.record_action(action_type)
        else:
            raise ValueError(f"Unknown micro action type: {action_type}")

        # 2️⃣ Determine rep for sentiment calculation
        rep_for_sentiment = rep if rep is not None else getattr(self, "current_rep", None)

        # 3️⃣ Apply sentiment delta
        apply_sentiment(action_type, rep_for_sentiment, self)

        # 4️⃣ Optional: reset days since last touch
        if action_type != "no_touch":
            self.days_since_touch = 0


    def reset_daily_flags(self):
        self.stage_advanced_today = False    
    
    def increment_day(self):
        """
        Increment per-day counters. Only increase days_since_touch if the entity
        wasn't interacted with today.
        """
        self.days_in_stage += 1

        # If the entity wasn't touched today (no micro or macro action advanced stage)
        if not getattr(self, "touched_today", False):
            self.days_since_touch += 1
        else:
            self.days_since_touch = 0

        # Reset per-day flags
        self.stage_advanced_today = False
        self.touched_today = False  # will be set to True when micro/macro actions occur

    
    def copy(self):
        new_entity = self.__class__.__new__(self.__class__)  # skip __init__
        new_entity.__dict__.update(self.__dict__)
        return new_entity
    def copy_for_simulation(entity):
        new_entity = entity.__class__.__new__(entity.__class__)
        # shallow copy other attributes
        for k, v in entity.__dict__.items():
            if k == "micro_state":
                new_entity.micro_state = copy.deepcopy(v)  # <-- deep copy MicroState
            else:
                setattr(new_entity, k, v)
        return new_entity
    
    
@dataclass
class OpportunityPersonality:
    name: str
    openness: float
    urgency: float
    skepticism: float
    price_sensitivity: float

@dataclass
class Opportunity(SimEntity):
    account_id: Optional[str] = None
    rep_id: Optional[str] = None
    stage: str = 'Prospecting'
    revenue: float = 0.0
    difficulty: float = None
    # friction: float = 0.0
    commission: float = 0.0
    days_in_stage: int = 0
    days_since_touch: int = 0
    personality: Optional[OpportunityPersonality] = None
    sentiment: float = 0.0
    last_sentiment_delta: float = 0.0
    sentiment_history: list = field(default_factory=list)
    account_name: str = ''
    touched_today: bool = False

    def __post_init__(self):
        if self.stage not in PIPELINE_STAGES:
            raise ValueError(f"Invalid stage: {self.stage}")
        self.assign_commission(CommissionPlan())
        if self.personality is None:
            self.personality = self.random_personality()

    @property
    def is_closed(self) -> bool:
        return self.stage in ("Closed Won", "Closed Lost", 'Closed Converted', 'Closed Dead')

    @property
    def stage_index(self) -> int:
        return PIPELINE_STAGES.index(self.stage)

    @property
    def can_advance(self) -> bool:
        return (not self.is_closed) and (not self.stage_advanced_today) and (self.stage_index < len(PIPELINE_STAGES) - 3)

    @staticmethod
    def random_personality() -> OpportunityPersonality:
        archetypes = [
            "Analytical Skeptic",
            "Urgent Pragmatist",
            "Price-Sensitive Opportunist",
            "Easy-Going Follower"
        ]
        weights = [0.3, 0.4, 0.2, 0.1]
        selected = random.choices(archetypes, weights=weights, k=1)[0]
        params_map = {
            "Analytical Skeptic": {"openness":0.4, "urgency":0.2, "skepticism":0.8, "price_sensitivity":0.5},
            "Urgent Pragmatist": {"openness":0.7, "urgency":0.9, "skepticism":0.3, "price_sensitivity":0.4},
            "Price-Sensitive Opportunist": {"openness":0.6, "urgency":0.5, "skepticism":0.5, "price_sensitivity":0.9},
            "Easy-Going Follower": {"openness":0.8, "urgency":0.6, "skepticism":0.2, "price_sensitivity":0.3},
        }
        return OpportunityPersonality(name=selected, **params_map[selected])

    def assign_commission(self, plan: CommissionPlan):
        self.commission = np.round(plan.commission_on(self.revenue), 2)

    def advance_stage(self) -> Optional[str]:
        if self.is_closed or self.stage_advanced_today or self.stage == "Negotiation":
            return None
        next_index = self.stage_index + 1
        if next_index >= len(PIPELINE_STAGES):
            return None
        self.stage = PIPELINE_STAGES[next_index]
        self.stage_advanced_today = True
        self.days_in_stage = 0
        return self.stage

    def mark_lost(self):
        if not self.is_closed:
            self.stage = "Closed Lost"

    def mark_won(self):
        if not self.is_closed:
            self.stage = "Closed Won"

    def force_close(self, won: bool) -> str:
        if self.is_closed:
            return self.stage
        self.stage = "Closed Won" if won else "Closed Lost"
        self.stage_advanced_today = True
        self.days_in_stage = 0
        return self.stage

    def apply_behavioral_response(self, rep, action_type, theta=None):
        """
        Update entity (Lead or Opportunity) in response to a micro-action.
        Records the micro-action in MicroState and updates sentiment.
        Momentum and friction are derived dynamically elsewhere.
        """

        # 1️⃣ Record micro-action directly if MicroState has the attribute
        if hasattr(self, "micro_state") and hasattr(self.micro_state, action_type):
            self.micro_state.record_action(action_type)
        else:
            raise ValueError(f"Unknown micro action type: {action_type}")

        # 2️⃣ Determine rep for sentiment calculation
        rep_for_sentiment = rep if rep is not None else getattr(self, "current_rep", None)

        # 3️⃣ Apply sentiment delta
        apply_sentiment(action_type, rep_for_sentiment, self)

        # 4️⃣ Optional: reset days since last touch
        if action_type != "no_touch":
            self.days_since_touch = 0

    def increment_day(self):
        """
        Increment per-day counters. Only increase days_since_touch if the entity
        wasn't interacted with today.
        """
        self.days_in_stage += 1

        # If the entity wasn't touched today (no micro or macro action advanced stage)
        if not getattr(self, "touched_today", False):
            self.days_since_touch += 1
        else:
            self.days_since_touch = 0

        # Reset per-day flags
        self.stage_advanced_today = False
        self.touched_today = False  # will be set to True when micro/macro actions occur

    def reset_daily_flags(self):
        self.stage_advanced_today = False
        
        

    def can_close(self) -> bool:
        """
        Return True if this opportunity is eligible to close.
        Only Negotiation-stage, not closed, opportunities can close.
        """
        return self.stage == "Negotiation" and not self.is_closed
        
        
        
    def copy(self):
        new_entity = self.__class__.__new__(self.__class__)  # skip __init__
        new_entity.__dict__.update(self.__dict__)
        return new_entity
    def copy_for_simulation(entity):
        new_entity = entity.__class__.__new__(entity.__class__)
        # shallow copy other attributes
        for k, v in entity.__dict__.items():
            if k == "micro_state":
                new_entity.micro_state = copy.deepcopy(v)  # <-- deep copy MicroState
            else:
                setattr(new_entity, k, v)
        return new_entity

        

@dataclass
class AccountPersonality:
    name: str
    openness: float          # Likelihood to engage
    urgency: float           # Need to solve problem
    skepticism: float        # Resistance to pressure
    price_sensitivity: float # Resistance to price
    
    
    
        
@dataclass
class Account:
    id: str
    name: str = 'Unnamed Company'
    rep_id: Optional[str] = None
    annual_revenue: float = 0.0
    buying_propensity: float = 0.9
    opportunities: List[str] = field(default_factory=list)  
    personality: Optional[AccountPersonality] = None
    days_since_last_opportunity: int = 0
    opportunity_cooldown: int = 3
    
    
    # -----------------------------
    # Post-init personality assignment
    # -----------------------------
    def __post_init__(self):
        if self.personality is None:
            self.personality = self.random_personality()
            
        # Typical revenue distributions are skewed
        self.annual_revenue = np.random.lognormal(mean=15, sigma=1)  # ~ 100k–5M typical
        self.days_since_last_opportunity = 0
        self.opportunity_cooldown = random.randint(15, 20)
        
        
    def effective_buying_propensity(self) -> float:
        """
        Dynamic hazard of spawning a new opportunity.
        Returns daily probability.
        """

        # 1️⃣ Time ramp (builds after cooldown)
        time_factor = min(
            1.0,
            max(0, self.days_since_last_opportunity - self.opportunity_cooldown) / 60
        )

        # 2️⃣ Revenue scaling (larger companies buy more often)
        revenue_factor = np.log(self.annual_revenue) / 15  # ~0.6–1.2 range typically

        # 3️⃣ Personality urgency (mild effect only)
        urgency_factor = 1 + 0.3 * self.personality.urgency

        # 4️⃣ Base intensity (keep small!)
        base_rate = 0.015  # tuned control knob

        propensity = base_rate * time_factor * revenue_factor * urgency_factor

        return min(propensity, 0.72)  # hard cap to prevent explosion

        
    # -----------------------------
    # Opportunity creation
    # -----------------------------
    def create_opportunity(self) -> Opportunity:
        """Create a new Opportunity tied to this account."""
        opp_revenue = self.create_opportunity_revenue()
        size_factor = min(opp_revenue / ((self.annual_revenue + 1) * 0.15), 0.5)
        opp = Opportunity(
            id=generate_id(),
            revenue=opp_revenue,
            stage='Prospecting',
            rep_id=self.rep_id,
            account_id=self.id,
            difficulty=self.base_difficulty + size_factor,
        )
        
        self.opportunities.append(opp.id)
        return opp

    @property
    def base_difficulty(self) -> float:
        """Linear scale: low revenue = easy, high revenue = hard."""
        min_rev = 100_000
        max_rev = 5_000_000
        clamped = max(min(self.annual_revenue, max_rev), min_rev)
        return 0.01 + (clamped - min_rev) / (max_rev - min_rev) * 0.25

    def create_opportunity_revenue(self, fraction=0.01, sigma=0.4) -> float:
        """
        Randomized opportunity revenue based on account revenue.
        Uses a log-normal multiplier to generate skewed opportunity sizes.

        Parameters:
        - fraction: base % of account revenue
        - sigma: controls variability (higher = more spread / bigger tail)
        """
        base = self.annual_revenue * fraction

        # Log-normal multiplier centered around 1.0
        # The mean of the log of the multiplier = 0 → mean multiplier ≈ 1
        multiplier = np.random.lognormal(mean=0, sigma=sigma)

        return base * multiplier

    # -----------------------------
    # Personality assignment
    # -----------------------------
    def assign_archetype(self, archetype_name: str):
        """Assign a personality archetype to this account."""
        archetype_params = {
            "Analytical Skeptic": {"openness":0.4, "urgency":0.2, "skepticism":0.8, "price_sensitivity":0.5},
            "Urgent Pragmatist": {"openness":0.7, "urgency":0.9, "skepticism":0.3, "price_sensitivity":0.4},
            "Price-Sensitive Opportunist": {"openness":0.6, "urgency":0.5, "skepticism":0.5, "price_sensitivity":0.9},
            "Easy-Going Follower": {"openness":0.8, "urgency":0.6, "skepticism":0.2, "price_sensitivity":0.3},
        }
        if archetype_name not in archetype_params:
            raise ValueError(f"Unknown archetype {archetype_name}")
        params = archetype_params[archetype_name]
        self.personality = AccountPersonality(name=archetype_name, **params)

    @staticmethod
    def random_personality() -> AccountPersonality:
        """Assign a random personality archetype using weighted probabilities."""
        archetypes = ["Analytical Skeptic", "Urgent Pragmatist", "Price-Sensitive Opportunist", "Easy-Going Follower"]
        weights = [0.3, 0.4, 0.2, 0.1]  # must sum to 1
        selected = random.choices(archetypes, weights=weights, k=1)[0]
        archetype_params = {
            "Analytical Skeptic": {"openness":0.4, "urgency":0.2, "skepticism":0.8, "price_sensitivity":0.5},
            "Urgent Pragmatist": {"openness":0.7, "urgency":0.9, "skepticism":0.3, "price_sensitivity":0.4},
            "Price-Sensitive Opportunist": {"openness":0.6, "urgency":0.5, "skepticism":0.5, "price_sensitivity":0.9},
            "Easy-Going Follower": {"openness":0.8, "urgency":0.6, "skepticism":0.2, "price_sensitivity":0.3},
        }
        return AccountPersonality(name=selected, **archetype_params[selected])

    # -----------------------------
    # Behavioral response
    #     # -----------------------------
    def apply_behavioral_response(self, rep, action_type, theta=None):
        """
        Update entity (Lead or Opportunity) in response to a micro-action.
        Records the micro-action in MicroState and updates sentiment.
        Momentum and friction are derived dynamically elsewhere.
        """

        # 1️⃣ Record micro-action directly if MicroState has the attribute
        if hasattr(self, "micro_state") and hasattr(self.micro_state, action_type):
            self.micro_state.record_action(action_type)
        else:
            raise ValueError(f"Unknown micro action type: {action_type}")

        # 2️⃣ Determine rep for sentiment calculation
        rep_for_sentiment = rep if rep is not None else getattr(self, "current_rep", None)

        # 3️⃣ Apply sentiment delta
        apply_sentiment(action_type, rep_for_sentiment, self)

        # 4️⃣ Optional: reset days since last touch
        if action_type != "no_touch":
            self.days_since_touch = 0
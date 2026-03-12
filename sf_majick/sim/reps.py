
from dataclasses import dataclass, field
from typing import List, Dict

from .micro_actions import execute_micro_action
from .economics import CommissionPlan

# from .logger import EventLogger

from typing import Optional
from .utility_engine import Strategy
from .macro_actions import attempt_macro_for_entity  # or wherever you put it



hrs_worked = 8

admin = .5
lunch = .5
goofing_off = 0.25
breaks = 0.5

hrs_productive = hrs_worked - admin - lunch - goofing_off - breaks

attention_span = hrs_productive * 60

@dataclass
class SalesRep:
    """
    Represents a sales rep with limited daily attention.
    """
    id: str
    daily_attention: int = attention_span
    strategy: Optional[Strategy] = None
    earnings: float = 0.0
    _attention_remaining: int = field(init=False)
    comp_rate: float = 1

    def __post_init__(self) -> None:
        self._attention_remaining = self.daily_attention

    # -----------------------------------------------------------------
    # Daily Lifecycle
    # -----------------------------------------------------------------
    def reset_day(self) -> None:
        self._attention_remaining = self.daily_attention

    @property
    def attention_remaining(self) -> int:
        return self._attention_remaining

    # -----------------------------------------------------------------
    # Micro + Macro Execution
    # -----------------------------------------------------------------
    def perform_micro_action(self, entity, action_name: str) -> dict:
        """Executes a micro action on any entity."""
        # print(action_name)
        telemetry = execute_micro_action(
            entity=entity,
            action_name=action_name,
            available_attention=self._attention_remaining,
            rep=self
        )
        
        if telemetry['success']:
            self._attention_remaining = telemetry['remaining_attention']
            # print('rep attn remaining: ', self._attention_remaining)
        return telemetry

    def attempt_macro(self, entity, accounts=None, opportunities=None) -> list:
        return attempt_macro_for_entity(
            entity,
            rep=self,
            # logger=EventLogger(),
            accounts=accounts,
            opportunities=opportunities
        )
    
    
    # -----------------------------------------------------------------
    # Unified Work Method
    # -----------------------------------------------------------------
    def work_entity(self, entity, micro_actions: List[str], accounts=None, opportunities = None) -> dict:
        """
        Execute micro actions on an entity, then attempt macro events.
        Works for Opportunities or Leads.
        Returns telemetry for logging.
        """
        # -------------------------
        # Initialize cooldowns if missing
        # -------------------------
        if not hasattr(entity, "cooldowns") or entity.cooldowns is None:
            entity.cooldowns = {}  # dict keyed by action_name

            for action_name in entity.cooldowns:
                if entity.cooldowns[action_name] > 0:
                    entity.cooldowns[action_name] -= 1


        micro_results = []
        for action_name in micro_actions:
            if self._attention_remaining <= 20:
                break
            result = self.perform_micro_action(entity, action_name)
            micro_results.append(result)
        # Attempt macro advancement
        macro_result = self.attempt_macro(entity, accounts=accounts, opportunities = opportunities)

        # Handle Closed Won commission (if Opportunity)
        if getattr(entity, "stage", None) in ["Closed Won", "Closed Lost", 'Closed Dead', 'Closed Converted']:
            if getattr(entity, "stage", None) == "Closed Won" and hasattr(entity, "revenue"):
                commission = CommissionPlan.commission_on(
                    revenue=entity.revenue,
                    rep_comp_rate=self.comp_rate
                )
                self.add_commission(commission)
                entity.commission = commission  # optional

        return {
            "rep_id": self.id,
            "opportunity_id": getattr(entity, "id", None),
            "micro_results": micro_results,
            "macro_result": macro_result,
            "attention_remaining": self._attention_remaining,
        }

    # -----------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------
    def opportunity_score(self, entity) -> float:
        """Score an entity for softmax selection."""
        base = getattr(entity, "compute_win_probability", lambda rep: 0.5)(self) * getattr(entity, "revenue", 0.0)
        stage_weight = {
            "Prospecting": 0.5,
            "Qualification": 0.7,
            "Proposal": 1.0,
            "Negotiation": 1.2,
            "Closed Won": 0.0,
            "Closed Lost": 0.0
        }
        return base * stage_weight.get(getattr(entity, "stage", ""), 1.0)

    def add_commission(self, amount: float) -> None:
        self.earnings += amount



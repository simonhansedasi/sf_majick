from dataclasses import dataclass, field
from typing import List, Dict, Optional
import random
import numpy as np

from .micro_actions import execute_micro_action
from .economics import CommissionPlan
from .utility_engine import Strategy
from .macro_actions import attempt_macro_for_entity


# ------------------------------------------------------------------
# Time budget (unchanged)
# ------------------------------------------------------------------
hrs_worked       = 8
admin            = 0.5
lunch            = 0.5
goofing_off      = 0.25
breaks           = 0.5
hrs_productive   = hrs_worked - admin - lunch - goofing_off - breaks
BASE_ATTENTION   = int(hrs_productive * 60)   # ~360 minutes


# ------------------------------------------------------------------
# Rep Personality
# ------------------------------------------------------------------
@dataclass
class RepPersonality:
    """
    Traits that shape how a rep works and deteriorates over time.

    aggression      – pushes hard toward closes; skips prep/nurture steps
    empathy         – invests in relationship actions (meetings, follow-ups)
    discipline      – how faithfully rep follows the optimal policy vs. drifting
    distraction_rate– daily probability of wasting a chunk of attention on nothing
    burnout_threshold– cumulative stress at which rep enters burnout mode
    resilience      – how fast stress decays per day (0=never recovers, 1=instant)
    """
    name: str
    aggression:          float = 0.5   # [0,1]
    empathy:             float = 0.5   # [0,1]
    discipline:          float = 0.5   # [0,1]
    distraction_rate:    float = 0.1   # [0,1]
    burnout_threshold:   float = 80.0  # stress units
    resilience:          float = 0.15  # stress decay per day


# Named archetypes ― pass archetype_name= to SalesRep.__post_init__
ARCHETYPES: Dict[str, RepPersonality] = {
    "Closer": RepPersonality(
        name="Closer",
        aggression=0.85, empathy=0.25, discipline=0.75,
        distraction_rate=0.08, burnout_threshold=90.0, resilience=0.20,
    ),
    "Nurturer": RepPersonality(
        name="Nurturer",
        aggression=0.20, empathy=0.90, discipline=0.60,
        distraction_rate=0.12, burnout_threshold=70.0, resilience=0.10,
    ),
    "Grinder": RepPersonality(
        name="Grinder",
        aggression=0.55, empathy=0.50, discipline=0.90,
        distraction_rate=0.04, burnout_threshold=110.0, resilience=0.25,
    ),
    "Scattered": RepPersonality(
        name="Scattered",
        aggression=0.50, empathy=0.50, discipline=0.20,
        distraction_rate=0.30, burnout_threshold=60.0, resilience=0.08,
    ),
}


# Deterministic rotation used by build_baseline to tile archetypes across reps
ARCHETYPE_ROTATION = ["Closer", "Nurturer", "Grinder", "Scattered"]


def random_personality() -> RepPersonality:
    weights = [0.30, 0.25, 0.30, 0.15]   # Closer, Nurturer, Grinder, Scattered
    name = random.choices(list(ARCHETYPES), weights=weights, k=1)[0]
    return ARCHETYPES[name]


# ------------------------------------------------------------------
# SalesRep
# ------------------------------------------------------------------
@dataclass
class SalesRep:
    """
    A sales rep with personality, stress/burnout dynamics, and human flaws.
    """
    id: str
    archetype_name: Optional[str]    = None   # if set, overrides random personality
    daily_attention: int             = BASE_ATTENTION
    strategy: Optional[Strategy]     = None
    earnings: float                  = 0.0
    comp_rate: float                 = 1.0

    # --- internal state (not constructor args) ---
    _attention_remaining: int        = field(init=False)
    personality: RepPersonality      = field(init=False)

    # Stress & motivation track rep health over time
    stress:      float = field(init=False, default=0.0)   # 0–∞ (burnout kicks in above threshold)
    motivation:  float = field(init=False, default=1.0)   # 0–1  (decays on stalled deals)
    consecutive_no_close_days: int = field(init=False, default=0)

    # Logged for analysis
    days_burned_out: int  = field(init=False, default=0)
    lifetime_actions: int = field(init=False, default=0)

    # Per-rep learned timing weights: W[action][stage] = EMA of observed deltas
    # Counts track how many observations back each weight, used to scale confidence
    timing_weights: dict = field(init=False)
    timing_counts:  dict = field(init=False)

    def __post_init__(self) -> None:
        if self.archetype_name and self.archetype_name in ARCHETYPES:
            self.personality = ARCHETYPES[self.archetype_name]
        else:
            self.personality = random_personality()

        if self.strategy is None:
            self.strategy = Strategy.from_personality(self.personality)

        self._attention_remaining = self._effective_daily_attention()
        self.timing_weights = {}   # {(action, stage): ema_delta}
        self.timing_counts  = {}   # {(action, stage): n_observations}

    # ------------------------------------------------------------------
    # Timing learning
    # ------------------------------------------------------------------
    def update_timing(self, action: str, stage: str, delta: float, alpha: float = 0.25) -> None:
        """
        Update the rep's learned timing weight for (action, stage) via EMA.

        alpha controls how fast the rep learns:
          - High alpha (0.4+): fast adaptation, forgets old evidence quickly
          - Low alpha (0.1):   slow, stable — rep trusts accumulated history

        Disciplined reps use a lower alpha (more deliberate updating).
        Scattered reps use a higher alpha (react to recent experience).
        """
        discipline = getattr(self.personality, "discipline", 0.5)
        effective_alpha = alpha * (1.2 - 0.4 * discipline)   # 0.17–0.29 range

        key = (action, stage)
        if key not in self.timing_weights:
            # First observation: initialise directly, no EMA blending
            self.timing_weights[key] = delta
            self.timing_counts[key]  = 1
        else:
            self.timing_weights[key] = (
                effective_alpha * delta
                + (1.0 - effective_alpha) * self.timing_weights[key]
            )
            self.timing_counts[key] += 1

    def get_timing_bonus(self, action: str, stage: str) -> float:
        """
        Return the learned timing bonus for (action, stage).

        Scales by a confidence factor that grows with observation count
        and saturates around n=20, so early estimates don't dominate.
        Bonus is clipped to [-0.6, 0.6] so it modulates but never overwhelms
        the base utility signal.
        """
        key = (action, stage)
        if key not in self.timing_weights:
            return 0.0

        ema    = self.timing_weights[key]
        n      = self.timing_counts[key]
        # Confidence: 0 → 1 as n grows, half-saturation at n=10
        confidence = n / (n + 10.0)

        return float(np.clip(ema * confidence, -0.6, 0.6))

    # ------------------------------------------------------------------
    # Attention
    # ------------------------------------------------------------------
    def _effective_daily_attention(self) -> int:
        """
        Burnout and low motivation shrink available attention.
        Distraction randomly eats a chunk at day-start.
        """
        attn = self.daily_attention

        # Burnout penalty: above threshold, attention craters
        if self.stress >= self.personality.burnout_threshold:
            attn = int(attn * 0.45)
            self.days_burned_out += 1
        elif self.stress >= self.personality.burnout_threshold * 0.70:
            # Approaching burnout: moderate penalty
            attn = int(attn * 0.75)

        # Motivation penalty
        attn = int(attn * (0.60 + 0.40 * self.motivation))

        # Distraction: random attention loss at day start
        if random.random() < self.personality.distraction_rate:
            lost = random.randint(20, 60)
            attn = max(0, attn - lost)

        return attn

    @property
    def attention_remaining(self) -> int:
        return self._attention_remaining

    @property
    def is_burned_out(self) -> bool:
        return self.stress >= self.personality.burnout_threshold

    # ------------------------------------------------------------------
    # Daily Lifecycle
    # ------------------------------------------------------------------
    def reset_day(self) -> None:
        """Call once per simulation day per rep."""
        # Stress decays (resilience controls recovery speed)
        self.stress = max(0.0, self.stress * (1.0 - self.personality.resilience))

        # Motivation recovers slightly each morning, decays if no close recently
        if self.consecutive_no_close_days > 5:
            # Demoralisation: motivation slowly erodes
            self.motivation = max(0.10, self.motivation - 0.03)
        else:
            self.motivation = min(1.0, self.motivation + 0.05)

        self._attention_remaining = self._effective_daily_attention()

    def record_close(self, won: bool) -> None:
        """Call whenever an entity closes (win or loss)."""
        self.consecutive_no_close_days = 0
        if won:
            self.motivation = min(1.0, self.motivation + 0.20)
            self.stress = max(0.0, self.stress - 5.0)
        else:
            # A lost deal adds mild stress and dents motivation
            self.stress      += 3.0
            self.motivation   = max(0.10, self.motivation - 0.05)

    def end_of_day(self, actions_taken: int, deals_worked: int) -> None:
        """
        Accumulate daily stress based on workload.
        Call after all work for the day is done.
        """
        self.consecutive_no_close_days += 1
        self.lifetime_actions          += actions_taken

        # Stress load: busy days with many deals cost more
        workload_stress = 0.5 * actions_taken / max(deals_worked, 1)
        self.stress     = min(self.stress + workload_stress, 200.0)

    # ------------------------------------------------------------------
    # Micro + Macro Execution
    # ------------------------------------------------------------------
    def perform_micro_action(self, entity, action_name: str) -> dict:
        telemetry = execute_micro_action(
            entity=entity,
            action_name=action_name,
            available_attention=self._attention_remaining,
            rep=self
        )
        if telemetry["success"]:
            self._attention_remaining = telemetry["remaining_attention"]
        return telemetry

    def attempt_macro(self, entity, accounts=None, opportunities=None) -> list:
        return attempt_macro_for_entity(
            entity,
            rep=self,
            accounts=accounts,
            opportunities=opportunities
        )

    # ------------------------------------------------------------------
    # Unified Work Method
    # ------------------------------------------------------------------
    def work_entity(
        self,
        entity,
        micro_actions: List[str],
        accounts=None,
        opportunities=None,
    ) -> dict:
        """
        Execute micro actions on an entity, then attempt macro events.
        Personality flaws fire here:
          - Distraction mid-work: random chance of skipping an action entirely
          - Aggression short-circuit: closer skips low-value prep actions
          - Empathy over-investment: nurturer doubles down on relationship actions
        """
        # Init cooldowns
        if not hasattr(entity, "cooldowns") or entity.cooldowns is None:
            entity.cooldowns = {}
        # Tick cooldowns down
        for action_name in list(entity.cooldowns):
            if entity.cooldowns[action_name] > 0:
                entity.cooldowns[action_name] -= 1

        micro_results = []
        actions_taken = 0

        for action_name in micro_actions:
            if self._attention_remaining <= 20:
                break

            # --- Personality flaws ---

            # Distraction mid-work: scattered/low-discipline reps lose focus
            mid_distraction_chance = (1.0 - self.personality.discipline) * 0.08
            if random.random() < mid_distraction_chance:
                # Burn some attention on nothing
                self._attention_remaining = max(0, self._attention_remaining - random.randint(10, 25))
                micro_results.append({
                    "success": False,
                    "action": action_name,
                    "cost": 0,
                    "remaining_attention": self._attention_remaining,
                    "reason": "distracted",
                })
                continue

            # Aggression short-circuit: Closers skip internal_prep / research_account
            # when a higher-value action is available
            PREP_ACTIONS = {"internal_prep", "research_account", "solution_design"}
            if (
                action_name in PREP_ACTIONS
                and self.personality.aggression > 0.70
                and random.random() < (self.personality.aggression - 0.70)
            ):
                micro_results.append({
                    "success": False,
                    "action": action_name,
                    "cost": 0,
                    "remaining_attention": self._attention_remaining,
                    "reason": "skipped_by_aggression",
                })
                continue

            # Empathy over-investment: Nurturers sometimes repeat relationship
            # touches (send_email / make_call) an extra time spontaneously
            RELATIONSHIP_ACTIONS = {"send_email", "make_call", "follow_up", "hold_meeting"}
            result = self.perform_micro_action(entity, action_name)
            micro_results.append(result)
            if result["success"]:
                actions_taken += 1
                # Update timing weights from observed sentiment delta
                delta = result.get("sentiment_delta", None)
                stage = getattr(entity, "stage", None)
                if delta is not None and stage is not None:
                    self.update_timing(action_name, stage, delta)

            if (
                result["success"]
                and action_name in RELATIONSHIP_ACTIONS
                and self.personality.empathy > 0.75
                and random.random() < (self.personality.empathy - 0.75)
                and self._attention_remaining > 30
            ):
                # Nurturer sends a second touch they didn't plan
                bonus = self.perform_micro_action(entity, action_name)
                bonus["reason"] = "empathy_bonus_touch"
                micro_results.append(bonus)
                if bonus["success"]:
                    actions_taken += 1

        # Macro advancement
        macro_result = self.attempt_macro(entity, accounts=accounts, opportunities=opportunities)

        # Commission on close
        stage = getattr(entity, "stage", None)
        if stage in ("Closed Won", "Closed Lost", "Closed Dead", "Closed Converted"):
            won = stage == "Closed Won"
            self.record_close(won)
            if won and hasattr(entity, "revenue"):
                commission = CommissionPlan.commission_on(
                    revenue=entity.revenue,
                    rep_comp_rate=self.comp_rate
                )
                self.add_commission(commission)
                entity.commission = commission

        return {
            "rep_id":             self.id,
            "archetype":          self.personality.name,
            "opportunity_id":     getattr(entity, "id", None),
            "micro_results":      micro_results,
            "macro_result":       macro_result,
            "attention_remaining": self._attention_remaining,
            "stress":             self.stress,
            "motivation":         round(self.motivation, 3),
            "burned_out":         self.is_burned_out,
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def opportunity_score(self, entity) -> float:
        """Score an entity for softmax target selection."""
        base = (
            getattr(entity, "compute_win_probability", lambda rep: 0.5)(self)
            * getattr(entity, "revenue", 0.0)
        )
        stage_weight = {
            "Prospecting":   0.5,
            "Qualification": 0.7,
            "Proposal":      1.0,
            "Negotiation":   1.2,
            "Closed Won":    0.0,
            "Closed Lost":   0.0,
        }
        return base * stage_weight.get(getattr(entity, "stage", ""), 1.0)

    def add_commission(self, amount: float) -> None:
        self.earnings += amount

    def __repr__(self) -> str:
        return (
            f"SalesRep({self.id!r}, archetype={self.personality.name!r}, "
            f"stress={self.stress:.1f}, motivation={self.motivation:.2f}, "
            f"burned_out={self.is_burned_out})"
        )
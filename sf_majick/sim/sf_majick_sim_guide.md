# sf_majick Simulation — Complete Reference

This document covers every module in the sim: what it does, how it connects to everything else, and how to use it. It is written against the actual code, not a design sketch.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Module Map](#2-module-map)
3. [Core Data Model](#3-core-data-model)
   - [MicroState](#microstate)
   - [Lead](#lead)
   - [Opportunity](#opportunity)
   - [Account](#account)
4. [Rep Model](#4-rep-model)
   - [RepPersonality & Archetypes](#reppersonality--archetypes)
   - [Strategy](#strategy)
   - [SalesRep](#salesrep)
5. [Simulation Engine](#5-simulation-engine)
   - [run_simulation](#run_simulation)
   - [Daily Loop](#daily-loop)
   - [Pipeline Death](#pipeline-death)
6. [Micro Actions](#6-micro-actions)
   - [Action Registry](#action-registry)
   - [Requirement Trees](#requirement-trees)
   - [Execution Engine](#execution-engine)
7. [Macro Actions](#7-macro-actions)
   - [Stage Advancement](#stage-advancement)
   - [Lead Conversion](#lead-conversion)
   - [Close / Lost](#close--lost)
8. [Micro Policy](#8-micro-policy)
9. [Probabilities](#9-probabilities)
10. [Sentiment Engine](#10-sentiment-engine)
11. [Utility Engine](#11-utility-engine)
12. [Economics](#12-economics)
13. [Logger](#13-logger)
14. [Theta](#14-theta)
15. [OrgConfig](#15-orgconfig)
16. [OrgCalibrator & ExperimentRunner](#16-orgcalibrator--experimentrunner)
17. [RequirementConfig](#17-requirementconfig)
18. [RequirementMiner](#18-requirementminer)
19. [RequirementIntegration](#19-requirementintegration)
20. [build_baseline.py](#20-build_baselinepy)
21. [run_simulation.py](#21-run_simulationpy)
22. [Pipeline Analysis](#22-pipeline-analysis)
23. [Workflows — End to End](#23-workflows--end-to-end)
24. [Theta Reference](#24-theta-reference)
25. [Troubleshooting](#25-troubleshooting)

---

## 1. Architecture Overview

The sim is a **discrete-event agent simulation** of a B2B sales org. Each day, every rep decides which entities (leads or opportunities) to work and what actions to take on them. Those actions accumulate into micro-states that gate macro events (stage advancements, closes, conversions). Sentiment flows through every interaction and influences all probability calculations.

```
                          ┌─────────────┐
                          │  theta.py   │  ← global probability parameters
                          └──────┬──────┘
                                 │ read by
          ┌──────────────────────┼──────────────────────┐
          │                      │                       │
   ┌──────▼──────┐      ┌────────▼────────┐    ┌────────▼────────┐
   │probabilities│      │  micro_actions  │    │  macro_actions  │
   │    .py      │      │      .py        │    │      .py        │
   └──────┬──────┘      └────────┬────────┘    └────────┬────────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │ called by
                          ┌──────▼──────┐
                          │ simulate.py │  ← core loop
                          └──────┬──────┘
                                 │ produces
                          ┌──────▼──────┐
                          │   logger    │  ← micro + macro + opp events
                          └─────────────┘

Calibration layer (optional, sim never imports these):

   SF exports → OrgCalibrator → OrgConfig ──┐
   SF exports → RequirementMiner → RequirementConfig ──┤
                                             └──► build_state_from_config
                                                  + patched_requirements
                                                  ──► simulate.py
```

**Separation guarantee:** `simulate.py` imports nothing from the calibration layer. It accepts `reps`, `leads`, `accounts`, `opportunities` however you build them.

---

## 2. Module Map

| File | Role | Imports from sim |
|---|---|---|
| `entities.py` | `MicroState`, `Lead`, `Opportunity`, `Account`, `SimEntity` | `economics`, `theta`, `sentiment`, `micro_actions`, `utils` |
| `reps.py` | `SalesRep`, `RepPersonality`, `ARCHETYPES` | `micro_actions`, `economics`, `utility_engine`, `macro_actions` |
| `micro_actions.py` | `MICRO_ACTIONS` registry, effect functions, `execute_micro_action` | `theta`, `sentiment`, `utils` |
| `macro_actions.py` | Stage advance, close, lead convert, `attempt_macro_for_entity` | `entities`, `utils`, `micro_actions`, `theta`, `economics`, `probabilities` |
| `micro_policy.py` | `simulate_rep_thinking` — rep decision logic | `entities`, `theta`, `micro_actions`, `macro_actions` |
| `probabilities.py` | All probability functions | `theta`, `entities`, `micro_actions` |
| `sentiment.py` | `compute_sentiment_delta`, `apply_sentiment`, replay stubs | — |
| `utility_engine.py` | `Strategy`, `strategy_weighted_utility`, `choose_targets_with_strategy` | `entities`, `micro_actions`, `probabilities`, `utils` |
| `economics.py` | `CommissionPlan` | — |
| `theta.py` | Global parameter dict | — |
| `logger.py` | `EventLogger` | — |
| `utils.py` | `MICRO_REQUIREMENTS_BY_STAGE`, `PIPELINE_STAGES`, helpers | `entities` |
| `simulate.py` | `run_simulation` — the core daily loop | all of the above |
| `run_simulation.py` | Experiment runner script, pickle-based multi-run | `simulate`, `logger`, `micro_policy` |
| `build_baseline.py` | One-time baseline state builder from live SF | `entities`, `reps`, `utils`, `sf_majick.functions` |
| `pipeline.py` | Post-sim analysis: `build_deals`, `build_sentiment_effects` | — (operates on DataFrames) |
| `sentiment_effects.py` | OLS-based sentiment analysis | `sentiment` |
| `org_config.py` | `OrgConfig`, `RepSlot` dataclasses | — |
| `org_calibrator.py` | `OrgCalibrator`, `ExperimentRunner`, `build_state_from_config` | `org_config`, then sim modules at call time |
| `requirement_config.py` | `RequirementConfig`, `build_micro_actions`, `build_stage_requirements` | `micro_actions` at call time |
| `requirement_miner.py` | `RequirementMiner` — fits `RequirementConfig` from SF exports | `requirement_config` |
| `requirement_integration.py` | `patched_requirements`, `make_state_factory` | `requirement_config`, sim modules at call time |

---

## 3. Core Data Model

### MicroState

`MicroState` is a dataclass that lives inside every `Lead` and `Opportunity`. It tracks the cumulative count of every micro action performed on that entity, plus an ordered history list used for sequence-based requirement checks.

```python
@dataclass
class MicroState:
    send_email:           int = 0
    make_call:            int = 0
    hold_meeting:         int = 0
    follow_up:            int = 0
    send_proposal:        int = 0
    research_account:     int = 0
    internal_prep:        int = 0
    solution_design:      int = 0
    stakeholder_alignment:int = 0
    days_until_next_stage:int = 0  # cooldown counter
```

Key methods:

| Method | What it does |
|---|---|
| `record_action(action_type, count=1)` | Increments the count and appends to `self.history` |
| `get(key, default=0)` | Safe attribute access by string name |
| `can_perform(action_name)` | Checks stage cooldown + requirement tree via `meets_requirements` |
| `meets_requirements(req)` | Recursive AND/OR/sequence/chance/min_total tree evaluator |
| `consume_requirements(req)` | Decrements counts when requirements are consumed after an action |
| `compute_progress_ratio(req)` | Returns 0–1 fraction of requirements satisfied (for probabilistic unlocking) |

### Lead

```python
@dataclass
class Lead:
    id: str
    name: str = ""
    stage: str = "Lead"          # "Lead" → "Closed Converted" or "Closed Dead"
    rep_id: Optional[str] = None
    micro_state: MicroState = field(default_factory=MicroState)
    sentiment: float = 0.0       # range [-5, 5]
    last_sentiment_delta: float = 0.0
    sentiment_history: list = field(default_factory=list)
    revenue: float = None        # drawn from lognormal(50k, σ=0.5) if None
    commission: float = None
    difficulty: float = 0.05
    personality: Optional[LeadPersonality] = None
    days_in_stage: int = 0
    days_since_touch: int = 0
    touched_today: bool = False
```

**Personality archetypes** (assigned randomly via `Lead.random_personality()`):

| Archetype | openness | urgency | skepticism | price_sensitivity | Weight |
|---|---|---|---|---|---|
| Analytical Skeptic | 0.4 | 0.2 | 0.8 | 0.5 | 30% |
| Urgent Pragmatist | 0.7 | 0.9 | 0.3 | 0.4 | 40% |
| Price-Sensitive Opportunist | 0.6 | 0.5 | 0.5 | 0.9 | 20% |
| Easy-Going Follower | 0.8 | 0.6 | 0.2 | 0.3 | 10% |

Key properties: `is_closed`, `can_advance`, `stage_index`. Key methods: `advance_stage()`, `mark_converted()`, `mark_lost()`, `increment_day()`, `reset_daily_flags()`.

### Opportunity

```python
@dataclass
class Opportunity(SimEntity):
    account_id: Optional[str] = None
    rep_id: Optional[str] = None
    stage: str = 'Prospecting'   # starts here when created from Account
    revenue: float = 0.0
    difficulty: float = None     # set by Account.base_difficulty + size_factor
    commission: float = 0.0
    days_in_stage: int = 0
    days_since_touch: int = 0
    personality: Optional[OpportunityPersonality] = None
    sentiment: float = 0.0
    last_sentiment_delta: float = 0.0
    sentiment_history: list = field(default_factory=list)
    touched_today: bool = False
```

Shares the same four personality archetypes and weights as Lead. `difficulty` controls how much revenue size penalises conversion probabilities — set in `Account.create_opportunity()` as `base_difficulty + size_factor`.

Pipeline stages in order: `Lead` → `Lead Qualified` → `Prospecting` → `Qualification` → `Proposal` → `Negotiation` → `Closed Won` / `Closed Lost` / `Closed Converted` / `Closed Dead`.

### Account

```python
@dataclass
class Account:
    id: str
    name: str = 'Unnamed Company'
    rep_id: Optional[str] = None
    annual_revenue: float = 0.0      # overridden in __post_init__ with lognormal
    buying_propensity: float = 0.9
    personality: Optional[AccountPersonality] = None
    days_since_last_opportunity: int = 0
    opportunity_cooldown: int = 3    # overridden to randint(15, 20) in __post_init__
```

`__post_init__` draws `annual_revenue` from `lognormal(mean=15, sigma=1)` (~100k–5M range) and assigns a random `AccountPersonality`.

Key methods:

| Method | What it does |
|---|---|
| `effective_buying_propensity()` | Daily hazard of spawning a new opportunity; combines time ramp, revenue scaling, urgency |
| `create_opportunity()` | Creates an `Opportunity` with revenue = `annual_revenue × 0.01 × lognormal(0, 0.4)` and `difficulty = base_difficulty + size_factor` |
| `assign_archetype(name)` | Sets `AccountPersonality` from the four standard archetypes |
| `base_difficulty` (property) | Linear 0.01–0.26 scale from `min_rev=100k` to `max_rev=5M` |

---

## 4. Rep Model

### RepPersonality & Archetypes

```python
@dataclass
class RepPersonality:
    name: str
    aggression:       float  # pushes hard to close; skips prep
    empathy:          float  # invests in relationship actions
    discipline:       float  # faithfulness to optimal policy
    distraction_rate: float  # daily prob of wasting attention
    burnout_threshold:float  # stress level at which attention craters
    resilience:       float  # stress decay per day
```

| Archetype | aggression | empathy | discipline | distraction_rate | burnout_threshold | resilience |
|---|---|---|---|---|---|---|
| **Closer** | 0.85 | 0.25 | 0.75 | 0.08 | 90.0 | 0.20 |
| **Nurturer** | 0.20 | 0.90 | 0.60 | 0.12 | 70.0 | 0.10 |
| **Grinder** | 0.55 | 0.50 | 0.90 | 0.04 | 110.0 | 0.25 |
| **Scattered** | 0.50 | 0.50 | 0.20 | 0.30 | 60.0 | 0.08 |

Default rotation in `build_baseline.py`: `["Closer", "Nurturer", "Grinder", "Scattered"]` cycling across reps.

### Strategy

`Strategy` is derived automatically from `RepPersonality` via `Strategy.from_personality()` in `SalesRep.__post_init__`. All knobs are `[0, 1]` floats:

| Knob | Derived from | Effect |
|---|---|---|
| `risk_aversion` | `0.3 + 0.5 × aggression` | 0 = chase small deals, 1 = chase large |
| `communicativeness` | `0.3 + 0.4 × empathy` | More actions per day when high |
| `patience` | `1.0 - 0.6 × aggression` | High = keep working older leads |
| `focus` | `0.3 + 0.5 × discipline` | High = concentrate on fewer targets |
| `momentum_bias` | `0.3 + 0.4 × aggression` | Weights macro momentum in deal scoring |
| `recency_bias` | `0.1 + 0.3 × (1 - discipline)` | Overweights recently-touched deals |
| `sunk_cost_bias` | `0.05 + 0.25 × (1 - discipline)` | Overweights heavily-invested deals |
| `aggression` | `personality.aggression` | Boosts Negotiation/Proposal stage weight |
| `empathy` | `personality.empathy` | Boosts high-sentiment entity scoring |

### SalesRep

```python
@dataclass
class SalesRep:
    id: str
    archetype_name: Optional[str] = None   # "Closer", "Nurturer", "Grinder", "Scattered"
    daily_attention: int = 360             # minutes (8h - admin - lunch - breaks)
    strategy: Optional[Strategy] = None    # auto-derived in __post_init__
    earnings: float = 0.0
    comp_rate: float = 1.0                 # commission multiplier
```

Internal state (not constructor args): `_attention_remaining`, `personality`, `stress`, `motivation`, `consecutive_no_close_days`, `days_burned_out`, `lifetime_actions`, `timing_weights`, `timing_counts`.

**Burnout:** when `stress >= burnout_threshold`, `daily_attention` craters to 45%. Between 70%–100% of threshold, moderate 25% penalty. Motivation penalty: `attn = attn × (0.60 + 0.40 × motivation)`.

**Learned timing:** `update_timing(action, stage, delta)` maintains an EMA of observed sentiment deltas per `(action, stage)` pair. `get_timing_bonus(action, stage)` returns this as a `[-0.6, 0.6]` clipped bonus used in `micro_policy.py`.

**Personality flaws in `work_entity()`:**
- **Distraction** (`1 - discipline × 0.08` probability): burns 10–25 attention on nothing
- **Aggression skip**: Closers (`aggression > 0.70`) skip `internal_prep`, `research_account`, `solution_design` with probability `aggression - 0.70`
- **Empathy over-investment**: Nurturers (`empathy > 0.75`) sometimes repeat relationship actions spontaneously

---

## 5. Simulation Engine

### run_simulation

```python
def run_simulation(
    reps: List[SalesRep],
    leads: List[Lead],
    accounts: List[Account],
    opportunities: List[Opportunity],
    days: int,
    logger: EventLogger,
    micro_policy: Callable[[SalesRep, object], str],
    apply_decay: bool = True,
) -> Dict
```

Returns `{'days_run', 'final_stage_distribution', 'total_accounts', 'logger_summary'}`.

### Daily Loop

Each day runs in this order:

1. **Cooldown decrement** — `decrement_cooldowns(opportunities)` ticks `micro_state.days_until_next_stage` down
2. **Rep reset** — each rep calls `reset_day()` to restore attention
3. **Entity flag reset** — `reset_daily_flags()` on all leads and opportunities
4. **Account opportunity spawn** — each account checks `effective_buying_propensity()` against `opportunity_cooldown`; spawns an opportunity if triggered
5. **Lead generation** — every 30 days, `randint(1, 4)` new leads are generated and added to the pool
6. **Entity assignment** — unclaimed entities are assigned to a rep via `strategy_weighted_utility` softmax
7. **Rep work loop** — while `attention_remaining > 20`:
   - `choose_targets_with_strategy` filters entities to actionable ones (respect `rep_id` and focus cap)
   - `pick_entity_for_rep` selects one via softmax on utility scores
   - `micro_policy(rep, entity)` returns the chosen action name
   - `rep.work_entity(entity, micro_actions=[action_name])` executes micro + attempts macro
   - If the micro result failed (blocked/insufficient attention), inner loop breaks
8. **Day increment** — surviving open entities call `increment_day()` and passive decay fires on untouched ones

### Pipeline Death

`compute_pipeline_death(entity)` returns a daily death probability:

```
base = 0.0001
+ inactivity  = min(days_since_touch × 0.000025, 0.10)
+ fatigue     = max(0, touches - 10) × 0.000125
+ sentiment   = max(0, -sentiment) × 0.00125
+ age_penalty = min(days_in_stage × 0.002, 0.0125)
```

Capped at 0.35. If triggered, entity moves to `"Closed Dead"`.

---

## 6. Micro Actions

### Action Registry

`MICRO_ACTIONS` is a module-level dict in `micro_actions.py`. Each entry is a `MicroAction(frozen=True)` dataclass:

```python
@dataclass(frozen=True)
class MicroAction:
    name: str
    cost: int                              # attention units consumed
    effect: Callable[[entity, rep], None]  # mutates entity
    requirements: Optional[Dict] = None   # requirement tree
```

| Action | Cost | Effect on entity |
|---|---|---|
| `send_email` | 15 | Records action, resets `days_since_touch`, applies email sentiment |
| `make_call` | 15 | Records action, resets `days_since_touch`, applies call sentiment |
| `research_account` | 25 | Records action, applies research sentiment (no touch reset) |
| `internal_prep` | 25 | Records action, applies prep sentiment (no touch reset) |
| `solution_design` | 35 | Records action, applies design sentiment (no touch reset) |
| `stakeholder_alignment` | 40 | Records action, applies alignment sentiment |
| `hold_meeting` | 40 | Records action, resets `days_since_touch`, applies meeting sentiment |
| `follow_up` | 30 | Records action, resets `days_since_touch`, applies follow-up sentiment |
| `send_proposal` | 50 | Records action, resets `days_since_touch`, applies proposal sentiment |

### Requirement Trees

Requirements are nested dicts evaluated recursively by `MicroState.meets_requirements()`. Node types:

| Node | Syntax | Semantics |
|---|---|---|
| `and` | `{"and": [req, req, ...]}` | All sub-requirements must be met |
| `or` | `{"or": [req, req, ...]}` | At least one sub-requirement must be met |
| `chance` | `{"chance": 0.5, "req": req}` | Sub-requirement evaluated probabilistically; if random < p → check req, else skip (counts as met) |
| `min_total` | `{"min_total": {"actions": [...], "count": N}}` | Sum of named action counts must be ≥ N |
| `sequence` | `{"sequence": [{"action": N}, ...]}` | Actions must appear in this order in `micro_state.history` |
| leaf | `{"send_email": 3}` | `micro_state.send_email >= 3` |

Stage requirements (`MICRO_REQUIREMENTS_BY_STAGE` in `utils.py`) gate macro advancement for each pipeline stage. These are separate from micro action requirements — they control whether `can_attempt_advancement` returns True.

Stage cooldown: after advancing, `micro_state.days_until_next_stage` is set from `COOLDOWN_STAGE_MAP`. While > 0, only `send_email`, `make_call`, `internal_prep`, `research_account` can be performed.

### Execution Engine

`execute_micro_action(entity, action_name, available_attention, rep)`:

1. Checks entity cooldowns (`entity.cooldowns` dict)
2. Calls `entity.micro_state.can_perform(action_name)` — checks stage cooldown + requirements
3. Checks `available_attention >= action.cost`
4. Calls `action.effect(entity, rep)` — records action, applies sentiment
5. Calls `entity.micro_state.consume_requirements(action.requirements)` — decrements consumed counts
6. Returns telemetry dict: `{success, action, cost, remaining_attention, sentiment_delta, sentiment_total, reason}`

---

## 7. Macro Actions

`attempt_macro_for_entity(entity, rep, accounts, opportunities)` runs on every entity worked by a rep. It attempts macros in this order:

### Stage Advancement

Condition: `can_attempt_advancement(entity)` — entity not closed, `can_advance == True`, and `get_scaled_micro_requirements(entity, theta)` satisfied.

`get_scaled_micro_requirements` scales the stage requirement counts by `min(1.0 + difficulty_scaled, 1.5)` where `difficulty_scaled = difficulty × (revenue / revenue_base) ^ revenue_exponent`. Harder deals need more activity before they advance.

Probability: `compute_stage_progress_probability(entity)` — a sigmoid on `base_prob_opportunity + sentiment_beta × sentiment + momentum_beta × momentum - friction_beta × friction`.

Effect: `entity.advance_stage()` → `apply_cooldown(entity)` → sets `days_until_next_stage` from `COOLDOWN_STAGE_MAP`.

### Lead Conversion

Condition: `can_convert_lead(entity)` — `send_email >= 1` and (`hold_meeting >= 1` or `make_call >= 2`).

Probability: `compute_lead_probability(entity)` — combines base probability, micro score (weighted email + meeting + follow_up counts), momentum, friction, difficulty, personality factors, and sentiment.

Effect: Creates a new `Account` and linked `Opportunity`. Lead moves to `"Closed Converted"`. New opportunity gets `sentiment=1`, `last_sentiment_delta=0.5` (conversion warmth bonus).

### Close / Lost

**Close attempt** (Negotiation stage only): probability from `compute_close_probability(entity)` — sigmoid on `base_prob_close + sentiment + momentum - friction - difficulty`. If successful → `mark_won()`, commission calculated. If failed → `mark_lost()`.

**Decay lost**: probability from `prob_lost(entity)` — `base + inactivity_factor + stagnation_factor + momentum + friction`, modulated by personality skepticism/urgency and stage multiplier. Leads get a grace period (untouched leads with 0 touches in first 10 days have `adjusted_loss_prob = 0`). Leads damped by `max(0, loss_prob - 0.05)`, opportunities damped by `max(0, loss_prob - 0.25)`. Hard cap at 0.35.

---

## 8. Micro Policy

`simulate_rep_thinking(rep, entity, horizon=3)` is the rep's decision function. It returns a single action name.

**Decision flow:**

1. Build candidate pool (Opportunity gets all 9 actions; Lead gets 6 — no `send_proposal`, `solution_design`, `stakeholder_alignment`)
2. Filter to `eligible_actions` via `entity.micro_state.can_perform(action)`
3. If empty, fall back to `["send_email", "make_call", "research_account", "internal_prep"]`
4. Scattered-rep distraction: if `discipline < 0.35`, with probability `0.35 - discipline`, pick a comfort action (`send_email` or `make_call`) and return immediately
5. Score each action via a 3-step lookahead:
   - Simulate the behavioral response (delta dict)
   - Compute `p × revenue × comp_rate` at each horizon step using `compute_opportunity_probability` or `compute_close_probability`
   - Average across horizon: `base_value = total_expected / horizon`
6. Apply `_personality_action_weight(action, personality)` — multiplier [0.5, 3.0] based on aggression/empathy/discipline affinity tables
7. Add `_context_action_bonus(action, entity, rep)` — heuristics for momentum/friction/sentiment/stage context, plus rep's learned timing weights
8. Softmax selection with temperature = `0.5 + 1.5 × (1 - discipline)`, then raised by `1 + 0.5 × (1 - motivation)` for demoralized reps

---

## 9. Probabilities

All functions read from the module-level `theta` dict. Patching `theta` at runtime changes all probability calculations in the live sim.

| Function | Input | Output | Key drivers |
|---|---|---|---|
| `compute_opportunity_probability(op)` | Opportunity | [0,1] | `stage_base - difficulty_scaled + sentiment_beta×sentiment + momentum_beta×momentum - friction_beta×friction + personality_terms + noise` |
| `compute_lead_probability(entity)` | Lead | [0,1] | `base + micro_score(email+meeting+followup) + momentum - friction - difficulty + personality + sentiment` — scaled by `scale_factor_lead_conversion` |
| `prob_lost(entity)` | Lead or Opportunity | [0,1] | `base + log1p(days_since_touch)×inactivity_alpha + log1p(days_in_stage)×stagnation_alpha + momentum + friction` × `stage_multiplier` |
| `compute_stage_progress_probability(entity)` | Any entity | sigmoid output | `base_prob_opportunity + sentiment_beta×sentiment + momentum_beta×momentum - friction_beta×friction` |
| `compute_close_probability(entity)` | Opportunity | sigmoid output | `base_prob_close + sentiment + momentum - friction - difficulty` |
| `simulate_macro_probability(entity)` | Lead or Opportunity | [0,1] | Stage-aware base from theta + momentum/friction/sentiment — used for strategy scoring in `utility_engine.py` |

**Momentum** and **friction** are dynamically computed by `derived_momentum(entity)` and `derived_friction(entity)` in `micro_actions.py`:
- `derived_momentum`: EMA over last 5 sentiment deltas (α=0.4)
- `derived_friction`: magnitude of negative rolling average sentiment over last 5 deltas

---

## 10. Sentiment Engine

Every micro action and every untouched day changes an entity's sentiment. Sentiment is bounded `[-5, 5]`.

### compute_sentiment_delta

Fourteen sequential steps produce a single delta:

1. **Passive decay** (`no_touch`): `-0.05 × decay_days^1.35 × stage_multiplier × personality_factors`
2. **Base action strength**: meeting=0.20, proposal=0.15, call=0.10, email=0.05, follow_up=0.05, solution_design=0.03, stakeholder=0.06, others=0
3. **Personality alignment**: openness/urgency/skepticism/price_sensitivity weighted by action type
4. **Strategy modulation**: `0.15 × (communicativeness - 0.5) + 0.10 × (focus - 0.5)`
5. **Trend continuation**: `momentum_bias × last_sentiment_delta`
6. **Saturation penalty**: `-0.35 × current_sentiment`
7. **Noise**: `Gauss(0, 0.25)` for low-touch actions; `Gauss(0, 0.35)` for others
8. **Memory effect**: `+0.15 × sum(last 3 sentiment deltas)` if history exists
9. **Random negative events**: 10% chance of -0.3–0.8; 5% chance of -0.8–1.5
10. **Rare major shocks**: 3% chance of ±1.5, ±2.0, or ±2.5
11. **Emotional regime multiplier**: 1.6× if `sentiment < -2`; 1.2× if `sentiment 1–3`; 1.4× if `sentiment > 3`
12. **Action fatigue**: `exp(-k × count × 1.4)` — email decays fastest (k=0.45), meetings slowest (k=0.12)
13. **Stage fatigue**: `exp(-0.04 × total_touch_count)` — affects all touch actions as total grows
14. **Baseline drift**: `-0.015` always applied

Clamped to `[-2.5, 2.5]` per step.

### apply_sentiment

Wrapper that calls `compute_sentiment_delta`, clamps the updated sentiment to `[-5, 5]`, updates `entity.last_sentiment_delta`, and appends to `entity.sentiment_history`. Called by every micro action effect function.

### Replay stubs

`ReplayRep` and `ReplayEntity` are lightweight stub classes for post-hoc analysis. Pass them to `compute_sentiment_delta` instead of live sim objects to replay "what would the delta be if a Closer had fired `hold_meeting` on this lead at this point?" without touching real objects.

---

## 11. Utility Engine

### strategy_weighted_utility

Scores an entity for rep prioritisation. All bias terms are multiplicative:

```
score = expected_commission(entity)
      × risk_modifier       (revenue / 1M) ^ risk_aversion
      × macro_modifier      1 + momentum_bias × macro_probability
      × patience_modifier   = strategy.patience
      × focus_modifier      = strategy.focus
      × recency_modifier    1 + recency_bias × exp(-days_since_touch/4)
      × sunk_cost_modifier  1 + sunk_cost_bias × (1 - exp(-total_actions/50))
      × sentiment_modifier  1 + empathy × clamp((sentiment+1)/2, 0, 1)
      × stage_modifier      stage-specific weight adjusted by aggression
```

### choose_targets_with_strategy

1. Filters entities to those owned by the rep (for opportunities)
2. Gets allowed micro actions via `micro_actions_allowed`
3. Sorts by `strategy_weighted_utility` descending
4. Applies focus cap: `max(3, len × (0.30 + 0.70 × (1 - focus)))` — high-focus reps work top 30% of pipeline

---

## 12. Economics

`CommissionPlan.commission_on(revenue, rep_comp_rate=1.0)` applies tiered rates then multiplies by `comp_rate`:

| Revenue tier | Rate |
|---|---|
| 0 – $1M | 5% |
| $1M – $10M | 8% |
| $10M – $50M | 12% |
| $50M+ | 18% |

Called in `SalesRep.work_entity()` on close and stored on the entity as `entity.commission`.

---

## 13. Logger

`EventLogger` stores three lists of dicts accumulated across the sim:

**`micro_events`** — one row per micro action attempt (including failures):
`{day, rep_id, entity_id, action, cost, success, attention_remaining, sentiment_delta, sentiment_total}`

**`macro_events`** — one row per macro event attempt:
`{day, rep_id, entity_id, macro_name, advanced, old_stage, new_stage, probability}`

**`opportunity_events`** — logged via `log_opportunity_state()` at key points:
`{run_id, opportunity_id, current_stage, total_actions, rep_interactions, emails_frac, calls_frac, proposals_frac, time_to_first_proposal, cycle_length, revenue}`

`logger.summary()` returns quick aggregate counts. `logger.clear()` resets all three lists.

---

## 14. Theta

`theta` is a plain dict in `theta.py`, imported directly by `probabilities.py`, `macro_actions.py`, `micro_policy.py`, and `entities.py`. Patching it at module level changes all probability calculations for all subsequent calls. The calibration layer patches and restores it per-run via `build_state_from_config`.

See [Section 24 — Theta Reference](#24-theta-reference) for every key and its default value.

---

## 15. OrgConfig

`OrgConfig` is the single kwargs schema for parameterising the sim. It has defaults matching the existing sim behaviour, so `OrgConfig()` with no arguments produces a valid, runnable configuration.

```python
from sf_majick.sim.org_config import OrgConfig, RepSlot

# Minimal — all defaults
cfg = OrgConfig()

# Typical experiment config
cfg = OrgConfig(
    label            = "acme_q3_hypothesis",
    n_reps           = 12,
    days             = 90,
    n_seed_accounts  = 20,
    base_prob_close  = 0.20,
    base_prob_lost   = 0.025,
    archetype_weights= {"Closer": 0.50, "Nurturer": 0.10, "Grinder": 0.30, "Scattered": 0.10},
)

# Detailed team via RepSlots (overrides n_reps)
cfg = OrgConfig(
    rep_slots = [
        RepSlot(archetype_name="Grinder", count=4, start_day=0,  comp_rate=1.0),
        RepSlot(archetype_name="Closer",  count=2, start_day=0,  comp_rate=1.1),
        RepSlot(archetype_name="Closer",  count=2, start_day=30, comp_rate=1.0),  # hired later
    ],
    days = 120,
)

# Non-mutating variant
new_cfg = cfg.with_changes(n_reps=14, label="hire_2")

# Persist / load
cfg.save("data/cfg.json")
cfg = OrgConfig.load("data/cfg.json")
print(cfg.describe())
```

`apply_to_theta(theta_dict)` returns a copy of the theta dict with `None`-valued fields skipped. Called inside `build_state_from_config` to patch the theta module before building sim state.

### OrgConfig field summary

**Team:** `n_reps=8`, `rep_slots=[]`, `archetype_weights`, `default_comp_rate=1.0`

**Pipeline:** `n_seed_leads=4`, `n_seed_accounts=10`, `random_account_revenues=True`, `account_revenues=[]`, `account_personality_weights`

**Probability overrides (all default `None` = use theta.py):** `base_prob_lead_conversion`, `base_prob_prospecting`, `base_prob_qualification`, `base_prob_proposal`, `base_prob_negotiation`, `base_prob_close`, `base_prob_lost`, `sentiment_beta_opportunity`, `sentiment_beta_lead`, `momentum_beta_opportunity`, `friction_beta_opportunity`, `inactivity_alpha`, `stagnation_alpha`

**Economics:** `commission_tiers=None`, `default_comp_rate=1.0`

**Sim control:** `days=90`, `n_runs=100`, `seed_offset=0`, `apply_decay=True`

**Metadata:** `label="baseline"`, `notes=""`

---

## 16. OrgCalibrator & ExperimentRunner

### OrgCalibrator

Fits an `OrgConfig` from Salesforce exports. The sim never imports this class.

```python
from sf_majick.sim.org_calibrator import OrgCalibrator
import pandas as pd

cal = OrgCalibrator({
    "opportunities": pd.read_csv("data/sf_opps.csv"),   # required
    "users":         pd.read_csv("data/sf_users.csv"),  # optional
    "accounts":      pd.read_csv("data/sf_accounts.csv"),
    "leads":         pd.read_csv("data/sf_leads.csv"),
})

org_cfg = cal.calibrate(label="acme_q3")
print(cal.validation_report())
org_cfg.save("data/org_config_acme.json")
```

**Minimum required columns in opportunities export:** `StageName` (or `stagename`), `Amount`, `CreatedDate`, `CloseDate`, `OwnerId`.

**What it fits:**

| Fitted field | Source | Method |
|---|---|---|
| `n_reps` | User count or distinct OwnerId count | Direct count |
| `n_seed_accounts` | Account count or distinct AccountId | Direct count |
| `base_prob_lead_conversion` | Lead `IsConverted` fraction | `n_converted / n_leads` |
| `base_prob_close` | Won / total closed fraction | `n_won / n_closed` |
| `base_prob_lost` | Lost rate converted to daily hazard | `lost_rate / avg_cycle_days` |
| `base_prob_prospecting/qualification/proposal/negotiation` | Stage-to-stage advancement rates | `n_at_next / n_at_stage / avg_days_in_stage` |
| `inactivity_alpha`, `stagnation_alpha` | Scaled inversely to avg cycle time | `0.010 × (45 / avg_cycle)` |

Custom stage name mapping:

```python
cal.STAGE_MAP.update({
    "technical eval":  "Qualification",
    "legal review":    "Negotiation",
    "verbal commit":   "Negotiation",
})
```

### ExperimentRunner

Runs Monte Carlo experiments over `OrgConfig` perturbations and returns stacked DataFrames.

```python
from sf_majick.sim.org_calibrator import ExperimentRunner, build_state_from_config
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.micro_policy import simulate_rep_thinking

runner = ExperimentRunner(
    base_config   = org_cfg,
    state_factory = build_state_from_config,   # or make_state_factory(req_cfg)
    sim_fn        = run_simulation,
    micro_policy  = simulate_rep_thinking,
    n_iterations  = 200,
)

# Single experiment
results = runner.run(perturbation={"n_reps": 12}, label="hire_2")

# Multi-experiment comparison
results = runner.compare({
    "baseline":        {},
    "hire_2_closers":  {"n_reps": org_cfg.n_reps + 2},
    "better_close":    {"base_prob_close": 0.22},
    "less_churn":      {"base_prob_lost": 0.020},
})

# Single-lever sensitivity scan
scan = runner.sensitivity_scan(
    param  = "base_prob_close",
    values = [0.10, 0.12, 0.15, 0.18, 0.20, 0.25],
)
```

**Output columns per run:** `label`, `run_id`, `n_won`, `n_lost`, `n_closed`, `revenue_per_run`, `won_rate`, `avg_rep_earnings`, `total_micro_actions`, `total_macro_events`.

### build_state_from_config

```python
from sf_majick.sim.org_calibrator import build_state_from_config

state = build_state_from_config(org_cfg)
# Returns: {"reps": [...], "leads": [...], "accounts": [...], "opportunities": [...]}
```

Builds reps from `rep_slots` or `n_reps + archetype_weights`, creates accounts with personalities drawn from `account_personality_weights`, seeds leads via `generate_random_leads`, and creates one opportunity per account. Patches theta during execution and restores it afterward.

---

## 17. RequirementConfig

`RequirementConfig` holds every integer count threshold in the requirement trees as a named field. Defaults reproduce the current hardcoded behaviour. `RequirementConfig()` with no arguments is a no-op — it changes nothing.

```python
from sf_majick.sim.requirement_config import RequirementConfig, build_micro_actions, build_stage_requirements

# Default — same as current hardcoded trees
req_cfg = RequirementConfig()

# Fitted — loaded from miner output
req_cfg = RequirementConfig.load("data/req_config_acme.json")
print(req_cfg.describe())

# Hand-authored: shorter sales motion hypothesis
lean = RequirementConfig(
    label                           = "lean_motion",
    micro_proposal_min_touches      = 2,   # fewer touches before proposal
    stage_qualification_min_touches = 2,   # faster to qualify
    stage_proposal_min_deep         = 1,   # lighter proposal gate
)
lean.save("data/req_config_lean.json")

# Build live trees from config
MICRO_ACTIONS               = build_micro_actions(req_cfg)
MICRO_REQUIREMENTS_BY_STAGE = build_stage_requirements(req_cfg)
```

### Field groups

**Micro action gates** (`micro_*`): count thresholds controlling when each action becomes available. E.g. `micro_meeting_sequence_emails=2` means the sequence path to `hold_meeting` requires 2 prior emails.

**Stage advancement gates** (`stage_*`): count thresholds in `MICRO_REQUIREMENTS_BY_STAGE`. E.g. `stage_qualification_min_touches=3` means 3 combined email+call+research+meeting before advancing from Qualification.

**Lead conversion gate** (`lead_*`): `lead_min_emails=1`, `lead_min_calls_if_no_meeting=2`.

Full field list is in the [OrgConfig & RequirementConfig Field Tables](#orgconfig-field-summary) above and in the source file docstring.

---

## 18. RequirementMiner

Fits a `RequirementConfig` from Salesforce activity exports by analysing what winning deals actually did.

### Required exports

```sql
-- Tasks (emails, calls, follow-ups)
SELECT Id, WhatId, TaskSubtype, Status, ActivityDate, CreatedDate
FROM Task
WHERE WhatId IN (SELECT Id FROM Opportunity WHERE CreatedDate >= LAST_N_YEARS:2)

-- Events (meetings)
SELECT Id, WhatId, Subject, ActivityDateTime, CreatedDate
FROM Event
WHERE WhatId IN (SELECT Id FROM Opportunity WHERE CreatedDate >= LAST_N_YEARS:2)

-- Stage history (timestamps of every stage change)
SELECT Id, OpportunityId, Field, OldValue, NewValue, CreatedDate
FROM OpportunityFieldHistory
WHERE Field = 'StageName'
AND OpportunityId IN (SELECT Id FROM Opportunity WHERE CreatedDate >= LAST_N_YEARS:2)

-- Opportunities (for outcome filtering)
SELECT Id, StageName, CloseDate, CreatedDate, OwnerId, Amount
FROM Opportunity WHERE CreatedDate >= LAST_N_YEARS:2
```

### Usage

```python
import pandas as pd
from sf_majick.sim.requirement_miner import RequirementMiner

miner = RequirementMiner(
    task_df          = pd.read_csv("data/sf_tasks.csv"),
    event_df         = pd.read_csv("data/sf_events.csv"),
    stage_history_df = pd.read_csv("data/sf_stage_history.csv"),
    opp_df           = pd.read_csv("data/sf_opps.csv"),
)

req_cfg = miner.mine(percentile=25, label="acme_q3")
print(miner.report())
req_cfg.save("data/req_config_acme.json")

# Inspect distributions before committing to a percentile
seq_df   = miner.sequences_df()       # total action counts per won opp
stage_df = miner.stage_activity_df()  # per-stage counts per won opp

print(seq_df.describe(percentiles=[0.10, 0.25, 0.50, 0.75]))
for stage, df in stage_df.items():
    print(f"\n--- {stage} ---")
    print(df.describe(percentiles=[0.25, 0.50]).loc[["25%", "50%"]].to_string())
```

### Percentile guide

| Percentile | What it means | Effect |
|---|---|---|
| `p10` | Fastest 10% of won deals set the floor | Very permissive, high throughput, short cycles |
| `p25` | Bottom quartile of winners *(recommended start)* | Achievable minimum, realistic discipline |
| `p50` | Median winner | Strict; may stall many deals |
| `p75` | Top-quartile behaviour | Only your best reps hit this naturally |

### TaskSubtype mapping

Check your org's actual values first:

```python
print(tasks_df["tasksubtype"].value_counts())
```

Extend the default map before mining if needed:

```python
from sf_majick.sim.requirement_miner import RequirementMiner, TASK_SUBTYPE_MAP

miner = RequirementMiner(
    task_df = tasks_df,
    task_subtype_map = {
        **TASK_SUBTYPE_MAP,
        "LinkedIn Message":  "send_email",
        "Video Call":        "hold_meeting",
        "Pricing Discussion":"send_proposal",
        "Champion Building": "stakeholder_alignment",
    },
    ...
)
```

Event subjects are matched by case-insensitive substring against `EVENT_SUBJECT_MAP`. Events with no subject match default to `hold_meeting`.

---

## 19. RequirementIntegration

Provides two styles for wiring `RequirementConfig` into the live sim without editing any existing files.

### Style A — Context manager (block-level)

```python
from sf_majick.sim.requirement_integration import patched_requirements

req_cfg = RequirementConfig.load("data/req_config_acme.json")

with patched_requirements(req_cfg):
    # Inside this block, MICRO_ACTIONS and MICRO_REQUIREMENTS_BY_STAGE
    # are replaced with trees built from req_cfg.
    # Everything is restored on exit, even if an exception occurs.
    results = run_experiment(n_runs=200, days=90)
```

### Style B — Per-run factory (for ExperimentRunner)

```python
from sf_majick.sim.requirement_integration import make_state_factory

runner = ExperimentRunner(
    base_config   = org_cfg,
    state_factory = make_state_factory(req_cfg),  # patches per-run, restores after
    sim_fn        = run_simulation,
    micro_policy  = simulate_rep_thinking,
)
```

### Standalone: run with only requirement fitting

```python
from sf_majick.sim.requirement_integration import run_with_requirement_config

req_cfg = RequirementConfig.load("data/req_config_acme.json")
results = run_with_requirement_config(
    req_cfg,
    baseline_path = "data/baseline_state.pkl",
    n_runs        = 100,
    days          = 90,
)
# Returns DataFrame: {run_id, n_won, won_rate, revenue_per_run}
```

This lets you isolate the effect of requirement calibration from theta calibration — useful for understanding whether a sim accuracy problem is about *how often* deals advance (theta) vs. *how much activity* is needed to advance them (requirements).

---

## 20. build_baseline.py

One-time script that connects to live Salesforce, creates a realistic starting state, and pickles it to `data/baseline_state.pkl`.

```python
python build_baseline.py
```

**What it does:**
1. Fetches all Users and assigns archetypes via `ARCHETYPE_ROTATION = ["Closer", "Nurturer", "Grinder", "Scattered"]` cycling
2. Fetches all Accounts and assigns each to a rep by `OwnerId` (fallback to random)
3. Generates 4 random leads via `generate_random_leads`
4. Creates one opportunity per account via `account.create_opportunity()`
5. Saves `{reps, leads, opportunities, accounts}` dict as pickle

The pickle is the starting point for `run_simulation.py`. Re-run `build_baseline.py` whenever your Salesforce user/account data changes significantly.

---

## 21. run_simulation.py

Multi-run experiment script. Reads from `data/baseline_state.pkl`, runs N deep-copies in parallel, collects telemetry, saves results.

```bash
python -m sf_majick.sim.run_simulation --runs 100 --days 30
```

**`run_experiment(n_runs, days, seed_offset)`** returns:

```python
{
    "runs":              {run_id: run_summary_dict},
    "micro_logs":        [micro_event_dicts with run_id],
    "macro_logs":        [macro_event_dicts with run_id],
    "opportunity_logs":  [opp_event_dicts with run_id],
    "accounts_state":    [Account objects from baseline],
    "opportunities_state":[Opportunity objects from baseline],
    "leads_state":       [Lead objects from baseline],
}
```

Each `run_summary` contains `reps`, `opportunities`, `accounts`, `leads` dicts keyed by entity id.

Results are saved to `data/simulation_results_{timestamp}.pkl`.

---

## 22. Pipeline Analysis

`pipeline.py` operates on DataFrames produced by `run_experiment`. It is pure analysis — no sim objects, no theta.

### build_deals

```python
from sf_majick.sim.pipeline import build_deals

deals = build_deals(opps_df, macro, micro, n_runs=25)
```

Produces one row per entity × run with these features: `run_id`, `entity`, `rep_id`, `is_lead`, `won`, `stage_final`, `revenue`, `commission`, `n_stages`, `pipeline_depth`, `avg_days_in_stage`, `max_days_in_stage`, `days_in_stage_cv`, `cycle_time`, `activity_count`, `avg_micro_per_stage`, `early_activity`, `late_activity`, `activity_cv`, `activity_velocity`, `stage_velocity`, `action_diversity`, `success_rate`, `momentum_slope`, `touch_recency`, `stall_count`, `prop_late_actions`, `sentiment_final`, `sentiment_median`, `sentiment_std`, `sentiment_range`, `frac_{action}` for each of the 9 action types.

### build_sentiment_effects

```python
from sf_majick.sim.pipeline import build_sentiment_effects

raw, adjusted, by_stage, timeseries = build_sentiment_effects(micro, macro, deals)
```

- `raw`: mean sentiment delta per action with 95% CI and n
- `adjusted`: OLS coefficients relative to `send_email` baseline, controlling for stage + won + run_id
- `by_stage`: mean delta per (action, stage) cell with reliability flag
- `timeseries`: per-opp day-level sentiment aggregation with normalised time `t_norm`

---

## 23. Workflows — End to End

### Workflow 1 — Run the sim unchanged

```bash
python -m sf_majick.sim.run_simulation --runs 100 --days 30
```

Or in Python:

```python
import pickle, copy, random
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.logger import EventLogger
from sf_majick.sim.micro_policy import simulate_rep_thinking

with open("data/baseline_state.pkl", "rb") as f:
    baseline = pickle.load(f)

state  = copy.deepcopy(baseline)
logger = EventLogger()

run_simulation(
    reps=state["reps"], leads=state.get("leads", []),
    opportunities=state.get("opportunities", []),
    accounts=state.get("accounts", []),
    days=90, logger=logger, micro_policy=simulate_rep_thinking,
)
print(logger.summary())
```

### Workflow 2 — Config-driven sim (no fitting)

```python
from sf_majick.sim.org_config import OrgConfig
from sf_majick.sim.org_calibrator import build_state_from_config
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.logger import EventLogger
from sf_majick.sim.micro_policy import simulate_rep_thinking

cfg   = OrgConfig(n_reps=10, days=90, base_prob_close=0.20, label="hypothesis")
state = build_state_from_config(cfg)
logger = EventLogger()

run_simulation(**state, days=cfg.days, logger=logger, micro_policy=simulate_rep_thinking)
print(logger.summary())
```

### Workflow 3 — Fit theta to a real org, then experiment

```python
import pandas as pd
from sf_majick.sim.org_calibrator import OrgCalibrator, ExperimentRunner, build_state_from_config
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.micro_policy import simulate_rep_thinking
from sf_majick.sim.org_config import RepSlot

opps_df = pd.read_csv("data/sf_opps.csv")
cal     = OrgCalibrator({"opportunities": opps_df})
org_cfg = cal.calibrate(label="acme_q3")
print(cal.validation_report())
org_cfg.save("data/org_config_acme.json")

runner = ExperimentRunner(
    base_config=org_cfg, state_factory=build_state_from_config,
    sim_fn=run_simulation, micro_policy=simulate_rep_thinking, n_iterations=200,
)

results = runner.compare({
    "baseline":        {},
    "hire_2_closers":  {"n_reps": org_cfg.n_reps + 2,
                        "rep_slots": [RepSlot("Closer", 2, start_day=0)]},
    "coaching_close":  {"base_prob_close": (org_cfg.base_prob_close or 0.15) + 0.05},
    "pipeline_hygiene":{"inactivity_alpha": (org_cfg.inactivity_alpha or 0.010) * 0.6},
})

print(results.groupby("label")[["won_rate", "revenue_per_run"]].agg(["mean", "std"]).to_string())
```

### Workflow 4 — Fit both theta and requirements, then experiment

```python
import pandas as pd
from sf_majick.sim.org_calibrator import OrgCalibrator, ExperimentRunner
from sf_majick.sim.requirement_miner import RequirementMiner
from sf_majick.sim.requirement_integration import make_state_factory
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.micro_policy import simulate_rep_thinking

# Load all four SF exports
opps_df    = pd.read_csv("data/sf_opps.csv")
tasks_df   = pd.read_csv("data/sf_tasks.csv")
events_df  = pd.read_csv("data/sf_events.csv")
history_df = pd.read_csv("data/sf_stage_history.csv")

# Fit OrgConfig
cal     = OrgCalibrator({"opportunities": opps_df})
org_cfg = cal.calibrate(label="acme_q3")
print(cal.validation_report())

# Fit RequirementConfig
miner   = RequirementMiner(tasks_df, events_df, history_df, opps_df)
req_cfg = miner.mine(percentile=25, label="acme_q3")
print(miner.report())

# Inspect raw distributions before committing
seq_df = miner.sequences_df()
print(seq_df.describe(percentiles=[0.25, 0.50, 0.75]).loc[["25%", "50%", "75%"]].to_string())

# Save both
org_cfg.save("data/org_config_acme.json")
req_cfg.save("data/req_config_acme.json")

# Experiment with both configs active
runner = ExperimentRunner(
    base_config   = org_cfg,
    state_factory = make_state_factory(req_cfg),
    sim_fn        = run_simulation,
    micro_policy  = simulate_rep_thinking,
    n_iterations  = 200,
)

results = runner.compare({
    "baseline":        {},
    "hire_2_closers":  {"n_reps": org_cfg.n_reps + 2},
    "coaching_close":  {"base_prob_close": (org_cfg.base_prob_close or 0.15) + 0.05},
})

scan = runner.sensitivity_scan("base_prob_close", [0.10, 0.15, 0.20, 0.25, 0.30])

print(results.groupby("label")[["won_rate", "revenue_per_run"]].mean().to_string())
print(scan.groupby("label")["won_rate"].mean().to_string())
```

### Workflow 5 — Isolate requirement calibration effect

```python
from sf_majick.sim.requirement_config import RequirementConfig
from sf_majick.sim.requirement_integration import run_with_requirement_config

req_cfg = RequirementConfig.load("data/req_config_acme.json")
results = run_with_requirement_config(req_cfg, n_runs=100, days=90)

# Compare to default requirements (no fitting)
default_cfg = RequirementConfig()
baseline    = run_with_requirement_config(default_cfg, n_runs=100, days=90)

import pandas as pd
both = pd.concat([
    results.assign(label="fitted"),
    baseline.assign(label="default"),
])
print(both.groupby("label")[["won_rate", "revenue_per_run"]].mean())
```

---

## 24. Theta Reference

Every key in `theta.py` with its default value and what uses it.

### Stage advancement probabilities

| Key | Default | Used in |
|---|---|---|
| `base_prob_lead` | 0.05 | `simulate_macro_probability` |
| `base_prob_prospecting` | 0.08 | `compute_opportunity_probability`, `simulate_macro_probability` |
| `base_prob_qualification` | 0.04 | same |
| `base_prob_proposal` | 0.02 | same |
| `base_prob_negotiation` | 0.01 | same |
| `base_prob_default` | 0.05 | fallback for unknown stages |
| `base_prob_opportunity` | 0.15 | `compute_stage_progress_probability` |

### Opportunity dynamics

| Key | Default | Used in |
|---|---|---|
| `revenue_base` | 10,000,000 | difficulty scaling denominator |
| `revenue_exponent` | 0.15 | `compute_opportunity_probability` difficulty scaling |
| `revenue_exponent_macro` | 0.05 | `compute_close_probability` difficulty scaling |
| `momentum_beta_opportunity` | 0.75 | `compute_opportunity_probability` |
| `friction_beta_opportunity` | 0.5 | `compute_opportunity_probability` |
| `sentiment_beta_opportunity` | 0.2 | `compute_opportunity_probability`, `compute_stage_progress_probability` |
| `noise_sigma_opportunity` | 0.05 | `compute_opportunity_probability` |
| `personality_skepticism_beta` | -0.15 | opportunity personality adjustment |
| `personality_urgency_beta` | 0.13 | opportunity personality adjustment |
| `personality_price_beta` | -0.12 | opportunity personality adjustment |

### Lead probabilities

| Key | Default | Used in |
|---|---|---|
| `base_prob_lead_conversion` | 0.25 | `compute_lead_probability` |
| `micro_weight_email` | 0.2 | lead micro score |
| `micro_weight_meeting` | 0.30 | lead micro score |
| `micro_weight_followup` | 0.5 | lead micro score |
| `momentum_beta_lead` | 0.6 | `compute_lead_probability` |
| `friction_beta_lead` | 0.16 | `compute_lead_probability` |
| `sentiment_beta_lead` | 0.1 | `compute_lead_probability` |
| `scale_factor_lead_conversion` | 0.35 | overall lead probability scaling |
| `noise_sigma_lead` | 0.02 | `compute_lead_probability` |
| `lead_min_engagement` | 2 | minimum email+meeting before lead probability > 0 |

### Close / lost probabilities

| Key | Default | Used in |
|---|---|---|
| `base_prob_close` | 0.15 | `compute_close_probability` |
| `momentum_beta_close` | 0.95 | `compute_close_probability` |
| `friction_beta_close` | 0.45 | `compute_close_probability` |
| `sentiment_beta_close` | 0.05 | `compute_close_probability` |
| `base_prob_lost` | 0.035 | `prob_lost` |
| `inactivity_alpha` | 0.010 | `prob_lost` inactivity factor = `inactivity_alpha × log1p(days_since_touch)` |
| `stagnation_alpha` | 0.008 | `prob_lost` stagnation factor = `stagnation_alpha × log1p(days_in_stage)` |
| `momentum_beta_lost` | 0.03 | `prob_lost` |
| `friction_beta_lost` | 0.03 | `prob_lost` |
| `max_prob_lost` | 0.35 | hard cap on `prob_lost` output |
| `stage_multipliers` | Lead:0.6, Prospecting:0.7, Qualification:0.9, Proposal:1.0, Negotiation:1.15 | `prob_lost` stage factor |
| `sentiment_scale` | 5 | sentiment normalisation denominator |

### Macro / decay

| Key | Default | Used in |
|---|---|---|
| `macro_base_nudge` | 0.15 | macro engine nudge |
| `momentum_beta_macro` | 0.75 | macro engine |
| `friction_beta_macro` | 0.55 | macro engine |
| `macro_noise_sigma` | 0.02 | macro engine noise |
| `momentum_carryover` | 0.25 | momentum accumulation |
| `friction_carryover` | 0.15 | friction accumulation |
| `momentum_cap` | 15 | momentum ceiling |
| `friction_momentum_drag` | 0.01 | friction dragging on momentum |

---

## 25. Troubleshooting

### Sim produces 0 closes

Stage gates are too strict relative to attention budget. Diagnose by checking how many opportunities reach Negotiation:

```python
from collections import Counter
stages = Counter(o.stage for o in state["opportunities"])
print(stages)
```

If most are stuck in Prospecting or Qualification, either lower the stage advancement requirements (`RequirementConfig`) or raise the advancement probabilities (`OrgConfig.base_prob_prospecting`). If using `build_state_from_config`, check `n_seed_accounts` — too few accounts means too few entities for reps to work.

### theta patches not restoring after kernel interrupt

Restart the kernel and check:

```python
from sf_majick.sim.theta import theta
print(theta["base_prob_close"])  # should be 0.15 if restored correctly
```

If stuck patched, restore manually:

```python
from sf_majick.sim.theta import theta
theta["base_prob_close"] = 0.15
# ... restore any other fields that were patched
```

### RequirementMiner: "No activity records matched to won opportunities"

Salesforce exports often use 18-character IDs in the opportunity export and 15-character IDs in task/event `WhatId` (or vice versa). Fix:

```python
opps_df["id"]       = opps_df["id"].str[:15]
tasks_df["whatid"]  = tasks_df["whatid"].str[:15]
events_df["whatid"] = events_df["whatid"].str[:15]
```

### RequirementMiner produces inflated counts

Your task/event export includes activities on all opportunities, not just won ones. Pre-filter:

```python
won_ids = opps_df[opps_df["stagename"].str.lower() == "closed won"]["id"].tolist()
tasks_df  = tasks_df[tasks_df["whatid"].isin(won_ids)]
events_df = events_df[events_df["whatid"].isin(won_ids)]
```

### OrgCalibrator validation report shows mostly "(not available)"

Column names aren't being matched. Check:

```python
print(opps_df.columns.tolist())
```

The calibrator auto-lowercases column names. If your export has spaces (`"Stage Name"`) rather than Salesforce API names (`"StageName"`), normalise first:

```python
opps_df.columns = opps_df.columns.str.lower().str.replace(" ", "")
```

### Attention bottleneck — reps exhausting attention before working all entities

This is expected behaviour. Each rep has 360 attention units. Actions cost 15–50 each. A rep with 20 entities can only deeply work 3–4 per day at the Proposal level. If you want reps to cover more entities, reduce `focus` in their strategy or lower the `micro_proposal_min_touches` requirement so mid-stage work is cheaper.

### `build_deals` in pipeline.py fails with KeyError on `days_in_stage`

The macro log doesn't have a `days_in_stage` column — it's not emitted by the logger. `build_deals` computes this from stage-window timestamps. If stage history is sparse (few advancements), `days_per_stage` can be empty. The function handles this gracefully with `if len(days_per_stage) > 0` guards, but if you see errors, check that `macro_logs` is not empty and contains `new_stage` values.

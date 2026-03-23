# sf_majick Org Simulator — Local Version

A standalone HTML simulator for the sf_majick sales org engine. No server,
no dependencies, no install. Open the file and go.

```
open simulator.html
```

---

## Why this exists

The Python `run_simulation.py` is the real engine — full requirement trees,
softmax lookahead, recursive micro-state evaluation. It's accurate and slow
(minutes per experiment run). This simulator is a fast scratchpad: tune an
org shape, see plausible outcomes in under a second, then export a fitted
`OrgConfig` to drive the Python sim with sensible starting parameters.

The two tools are complementary. Use this to explore; use Python to validate.

---

## Setup tab

Everything that controls the sim lives here. Changes take effect the next
time you click **Run simulation** — there's no live recalculation.

### Simulation control

| Slider | Range | What it does |
|---|---|---|
| Sim days | 30–365 | Length of the simulated period |
| Seed accounts | 2–60 | Opportunities created at day 0, one per account |
| Seed leads | 0–30 | Leads injected at day 0 |

### Team — rep count & archetype mix

| Slider | What it does |
|---|---|
| Total reps | Headcount. Accounts are distributed round-robin across reps. |
| Closer % | Weight toward aggressive, direct reps (high aggression, high discipline) |
| Nurturer % | Weight toward relationship reps (high empathy, lower burnout threshold) |
| Grinder % | Weight toward systematic, high-volume reps (highest discipline, slowest burnout) |
| Scattered % | Weight toward unfocused reps (low discipline, high distraction rate) |
| Comp rate | Commission multiplier applied on top of the base commission rate |

Archetype weights don't need to sum to 100% — they're normalised automatically.

### Account personality mix

Controls the distribution of buyer archetypes across seeded accounts.

| Archetype | Urgency | Skepticism | Price sensitivity |
|---|---|---|---|
| Analytical Skeptic | Low | High | Medium |
| Urgent Pragmatist | High | Low | Low |
| Price-Sensitive Opportunist | Medium | Medium | High |
| Easy-Going Follower | Low | Low | Low |

Higher skepticism reduces sentiment gain per interaction. Higher urgency
amplifies it. Price sensitivity dampens probability in late stages.

### Close & lost probabilities

| Slider | Mirrors | Notes |
|---|---|---|
| Base close rate | `base_prob_close` | Daily probability of closing a Negotiation-stage deal that meets action requirements |
| Base lost rate (daily) | `base_prob_lost` | Daily baseline hazard applied to all open deals |
| Inactivity alpha | `inactivity_alpha` | Scales how fast lost probability grows with days since last touch (`alpha × log1p(days_since_touch)`) |
| Stagnation alpha | `stagnation_alpha` | Same but for days stuck in current stage |

### Stage advancement base probs

Per-stage daily probability of advancing once action requirements are met.
These are the `base_prob_*` fields in `theta.py`.

| Slider | Default | Typical fitted range |
|---|---|---|
| Prospecting | 8% | 2–15% |
| Qualification | 4% | 1–10% |
| Proposal | 2% | 0.5–6% |
| Negotiation | 1% | 0.2–4% |
| Lead conversion | 25% | 5–50% |

All stage probabilities are further modulated by sentiment, momentum,
friction, and deal difficulty on every tick.

### Sentiment sensitivity

Controls how strongly rep–account interactions move stage and close
probabilities.

| Slider | Mirrors | Effect |
|---|---|---|
| Sentiment beta (opp) | `sentiment_beta_opportunity` | Weight of cumulative sentiment on opportunity advancement |
| Sentiment beta (lead) | `sentiment_beta_lead` | Weight on lead conversion probability |
| Momentum beta (opp) | `momentum_beta_opportunity` | Weight of recent positive sentiment trend |
| Friction beta (opp) | `friction_beta_opportunity` | Weight of recent negative sentiment trend |

Raising momentum beta rewards reps who build consistent positive streaks.
Raising friction beta punishes neglected or poorly-handled deals more.

### Deal economics

| Slider | What it controls |
|---|---|
| Revenue log-mean (ln$) | `mu` of the lognormal deal size distribution. This is the natural log of the median deal value. `ln(10000) ≈ 9.21`, `ln(50000) ≈ 10.82`, `ln(100000) ≈ 11.51`, `ln(1000000) ≈ 13.82`. |
| Revenue log-sigma | Spread of the distribution. `0.5` = tight cluster near the median. `1.5` = wide range with frequent outliers. |
| Difficulty mean | Average deal difficulty. Scales the probability penalty for large deals (`difficulty × (revenue / revenue_base)^exponent`). |
| Commission rate | Fraction of deal revenue paid as commission on close. Applied on top of comp rate. |

A live preview below these sliders shows the p10 / median / p90 deal sizes
from your current parameters so you can sanity-check before running.

**Common revenue presets:**

| Segment | rev-mu | Median deal |
|---|---|---|
| SMB | 9.21 | ~$10K |
| Mid-market (default) | 10.82 | ~$50K |
| Enterprise | 11.51 | ~$100K |
| Large enterprise | 12.21 | ~$200K |

---

## Simulation tab

Runs the daily loop and shows results immediately.

**Summary metrics:** closed won count, win rate, total won revenue, average
cycle length in days.

**Team panel:** each rep's archetype, win/loss record, earnings, and a stress
bar. Stress above the burnout threshold (varies by archetype) reduces
available attention by 55% and causes distracted behaviour.

**Stage distribution:** bar chart of how many deals are in each stage at end
of sim. A pipeline bunched in Prospecting usually means stage advancement
probabilities are too low or sim days too short relative to deal complexity.

**Deal sample:** up to 20 deals with stage, account personality, revenue,
and current sentiment score. Sentiment range is −5 to +5.

**Daily activity chart:** last 30 days of micro action volume. Green dots
mark days when at least one deal closed won.

---

## Org fitter tab

Click **Fit org from sim data** after running a simulation. The fitter
intentionally does not look at your slider inputs — it only observes pipeline
outcomes, exactly as `OrgCalibrator.calibrate()` does with a real Salesforce
export.

**What it derives:**

- `base_prob_close` — from observed win rate
- `base_prob_lost` — from lost rate divided by average cycle length
- `base_prob_prospecting/qualification/proposal` — from fraction of deals
  that advanced past each stage, divided by average days spent there
- `inactivity_alpha` / `stagnation_alpha` — scaled inversely with observed
  cycle length (slow orgs get a lower inactivity penalty)
- Archetype and account personality distributions — from what was actually
  assigned during the sim

**Fitted vs. default column:** green = higher than theta default,
red = lower, gray = within 5%.

**Export options:**
- **Copy JSON** — paste directly into Python
- **Download as .json** — save as `fitted_config.json` for `OrgConfig.load()`
- **Python snippet** — copy-paste ready experiment runner code

---

## Using the fitted config in Python

```python
from sf_majick.sim.org_config import OrgConfig
from sf_majick.sim.org_calibrator import ExperimentRunner, build_state_from_config
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.micro_policy import simulate_rep_thinking

cfg = OrgConfig.load("fitted_config.json")
print(cfg.describe())

runner = ExperimentRunner(
    base_config   = cfg,
    state_factory = build_state_from_config,
    sim_fn        = run_simulation,
    micro_policy  = simulate_rep_thinking,
    n_iterations  = 200,
)

results = runner.compare({
    "baseline":      {},
    "hire_2_closers":{"n_reps": cfg.n_reps + 2},
    "coaching":      {"base_prob_close": (cfg.base_prob_close or 0.15) + 0.05},
    "pipeline_hygiene": {
        "inactivity_alpha": (cfg.inactivity_alpha or 0.010) * 0.6,
        "stagnation_alpha": (cfg.stagnation_alpha or 0.008) * 0.6,
    },
})

print(results.groupby("label")[["won_rate","revenue_per_run","avg_rep_earnings"]].mean())
```

---

## Why the HTML sim runs so much faster than Python

The HTML sim trades accuracy for speed. Each day each rep picks 2–5 actions
from a flat weighted pool. There is no lookahead, no requirement tree
evaluation, no softmax target selection.

The Python engine runs `simulate_rep_thinking` for every rep × entity × day,
which does a 3-step lookahead: for each candidate action it simulates the
world 3 ticks forward, scores expected value, then runs softmax. On top of
that, `MicroState.can_perform()` walks a recursive AND/OR/sequence tree on
every action candidate, and `choose_targets_with_strategy` scores and
softmax-samples the entire pipeline before any actions are chosen.

With 100 runs × 90 days × 8 reps × 20 entities, that's ~1.4M rep-entity-day
ticks at full fidelity. The HTML sim runs the same scenario in under a second
because it skips all of it.

Use this to find a plausible parameter region quickly. Use Python to validate
it properly.

---

## Files

```
simulator.html   — complete simulator, single file, no dependencies
README.md        — this file
```

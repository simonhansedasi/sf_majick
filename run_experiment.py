#!/usr/bin/env python3
"""
Local experiment runner. Uses the full Python sim engine.

Usage:
    python3 run_experiment.py data/fitted_configs/acme_q3.json

Edit the SCENARIOS dict below to define what you want to test.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sf_majick.sim.org_config import OrgConfig
from sf_majick.sim.org_calibrator import ExperimentRunner, build_state_from_config
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.micro_policy import simulate_rep_thinking

# ── Load config ───────────────────────────────────────────────────
cfg_path = sys.argv[1] if len(sys.argv) > 1 else "data/fitted_configs/fitted.json"
cfg = OrgConfig.load(cfg_path)
print(cfg.describe())

# ── Define scenarios ──────────────────────────────────────────────
# Each entry: label → dict of OrgConfig field overrides.
# Empty dict {} = baseline. Omitted fields use the calibrated values.

SCENARIOS = {
    "baseline":         {},
    "hire_2_reps":      {"n_reps": cfg.n_reps + 2},
    "coaching":         {"base_prob_close": (cfg.base_prob_close or 0.15) + 0.05},
    "pipeline_hygiene": {
        "inactivity_alpha": (cfg.inactivity_alpha or 0.010) * 0.6,
        "stagnation_alpha": (cfg.stagnation_alpha or 0.008) * 0.6,
    },
}

N_ITERATIONS = 100   # iterations per scenario
DAYS         = cfg.days   # sim length — use calibrated value by default

# ── Run ───────────────────────────────────────────────────────────
cfg_run = cfg.with_changes(days=DAYS, n_runs=N_ITERATIONS)

runner = ExperimentRunner(
    base_config   = cfg_run,
    state_factory = build_state_from_config,
    sim_fn        = run_simulation,
    micro_policy  = simulate_rep_thinking,
    n_iterations  = N_ITERATIONS,
)

print(f"\nRunning {len(SCENARIOS)} scenarios × {N_ITERATIONS} iterations ({DAYS} days each)…\n")
results = runner.compare(SCENARIOS)

summary = (
    results
    .groupby("label")[["won_rate", "revenue_per_run", "avg_rep_earnings", "n_won"]]
    .agg(["mean", "std", "median"])
    .round(4)
)
print(summary.to_string())

# Save results next to the config
import pandas as pd
out_path = cfg_path.replace(".json", "_results.csv")
results.to_csv(out_path, index=False)
print(f"\nFull results saved to: {out_path}")

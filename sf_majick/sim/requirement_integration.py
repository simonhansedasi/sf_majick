"""
requirement_integration.py
==========================
Shows how to wire RequirementConfig into the live sim.

The sim currently reads MICRO_ACTIONS and MICRO_REQUIREMENTS_BY_STAGE as
module-level imports.  This shim patches those at runtime so you don't have
to edit micro_actions.py or utils.py.

There are two integration styles — pick whichever fits your workflow:

Style A: Patch-on-startup (recommended for experiment runs)
    Patch once before any simulation code imports the action registries.
    All subsequent imports will see the patched values.

Style B: Per-run patching via build_state_from_config
    Patch inside the state factory so each ExperimentRunner iteration
    gets independently configured registries.  Useful when you're
    comparing runs with different RequirementConfigs in the same session.

Both styles automatically restore the originals on exit / exception.
"""

from __future__ import annotations

import contextlib
from typing import Optional

from .requirement_config import RequirementConfig, build_micro_actions, build_stage_requirements


# ---------------------------------------------------------------------------
# Style A: patch-on-startup context manager
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def patched_requirements(req_cfg: RequirementConfig):
    """
    Context manager that patches MICRO_ACTIONS and MICRO_REQUIREMENTS_BY_STAGE
    for the duration of the with-block, then restores originals.

    Usage
    -----
        from sf_majick.sim.requirement_integration import patched_requirements
        from sf_majick.sim.requirement_config import RequirementConfig

        req_cfg = RequirementConfig.load("data/req_config_acme.json")

        with patched_requirements(req_cfg):
            results = run_experiment(n_runs=200, days=90)
    """
    import sf_majick.sim.micro_actions as micro_mod
    import sf_majick.sim.utils as utils_mod
    import sf_majick.sim.macro_actions as macro_mod

    # Save originals
    orig_micro = dict(micro_mod.MICRO_ACTIONS)
    orig_stage = dict(utils_mod.MICRO_REQUIREMENTS_BY_STAGE)

    # Build and install new registries
    new_micro = build_micro_actions(req_cfg)
    new_stage = build_stage_requirements(req_cfg)

    micro_mod.MICRO_ACTIONS.clear()
    micro_mod.MICRO_ACTIONS.update(new_micro)

    utils_mod.MICRO_REQUIREMENTS_BY_STAGE.clear()
    utils_mod.MICRO_REQUIREMENTS_BY_STAGE.update(new_stage)

    try:
        yield
    finally:
        # Restore
        micro_mod.MICRO_ACTIONS.clear()
        micro_mod.MICRO_ACTIONS.update(orig_micro)

        utils_mod.MICRO_REQUIREMENTS_BY_STAGE.clear()
        utils_mod.MICRO_REQUIREMENTS_BY_STAGE.update(orig_stage)


# ---------------------------------------------------------------------------
# Style B: build a state factory that patches per-run
# ---------------------------------------------------------------------------

def make_state_factory(req_cfg: Optional[RequirementConfig] = None):
    """
    Returns a state_factory function compatible with ExperimentRunner that
    patches requirement registries before building the sim state, then
    restores them.

    If req_cfg is None, uses RequirementConfig defaults (= current hardcoded
    behaviour).

    Usage
    -----
        from sf_majick.sim.org_config import OrgConfig
        from sf_majick.sim.org_calibrator import ExperimentRunner, build_state_from_config
        from sf_majick.sim.requirement_config import RequirementConfig
        from sf_majick.sim.requirement_integration import make_state_factory

        req_cfg = RequirementConfig.load("data/req_config_acme.json")

        runner = ExperimentRunner(
            base_config   = org_cfg,
            state_factory = make_state_factory(req_cfg),   # <-- wired here
            sim_fn        = run_simulation,
            micro_policy  = simulate_rep_thinking,
        )
    """
    effective_cfg = req_cfg or RequirementConfig()

    def _factory(org_cfg):
        with patched_requirements(effective_cfg):
            from sf_majick.sim.org_calibrator import build_state_from_config
            return build_state_from_config(org_cfg)

    return _factory


# ---------------------------------------------------------------------------
# Full combined calibration example
# ---------------------------------------------------------------------------

def full_calibration_example():
    """
    End-to-end: fit both OrgConfig (theta) and RequirementConfig (counts),
    then run experiments with both applied.

    Copy-paste this into a notebook or script and swap in your real CSVs.
    """
    import pandas as pd
    from sf_majick.sim.org_calibrator import OrgCalibrator, ExperimentRunner
    from sf_majick.sim.org_config import OrgConfig
    from sf_majick.sim.requirement_miner import RequirementMiner
    from sf_majick.sim.simulate import run_simulation
    from sf_majick.sim.micro_policy import simulate_rep_thinking

    # ------------------------------------------------------------------
    # 1. Load Salesforce exports
    # ------------------------------------------------------------------
    opps_df    = pd.read_csv("data/sf_opps.csv")
    tasks_df   = pd.read_csv("data/sf_tasks.csv")
    events_df  = pd.read_csv("data/sf_events.csv")
    history_df = pd.read_csv("data/sf_stage_history.csv")

    # ------------------------------------------------------------------
    # 2. Fit OrgConfig (theta — probabilities, team size, cycle time)
    # ------------------------------------------------------------------
    cal      = OrgCalibrator({"opportunities": opps_df})
    org_cfg  = cal.calibrate(label="acme_q3")
    print(cal.validation_report())
    org_cfg.save("data/org_config_acme.json")

    # ------------------------------------------------------------------
    # 3. Fit RequirementConfig (action counts — micro + macro gates)
    # ------------------------------------------------------------------
    miner   = RequirementMiner(
        task_df          = tasks_df,
        event_df         = events_df,
        stage_history_df = history_df,
        opp_df           = opps_df,
    )
    req_cfg = miner.mine(percentile=25, label="acme_q3")
    print(miner.report())
    req_cfg.save("data/req_config_acme.json")

    # Optionally inspect the raw distributions before committing
    seq_df   = miner.sequences_df()         # per-opp total action counts
    stage_df = miner.stage_activity_df()    # per-stage action counts
    print("\nWinning deal action count distributions (p25 / p50 / p75):")
    print(seq_df.describe(percentiles=[0.25, 0.50, 0.75]).loc[
        ["25%", "50%", "75%"]
    ].to_string())

    # ------------------------------------------------------------------
    # 4. Run experiments with both configs active
    # ------------------------------------------------------------------
    runner = ExperimentRunner(
        base_config   = org_cfg,
        state_factory = make_state_factory(req_cfg),   # patches requirements per-run
        sim_fn        = run_simulation,
        micro_policy  = simulate_rep_thinking,
        n_iterations  = 200,
    )

    results = runner.compare({
        "baseline":           {},
        "hire_2_closers":     {"n_reps": org_cfg.n_reps + 2},
        "looser_gates":       {},   # run again with a more permissive req_cfg to compare
        "tighter_gates":      {},
    })

    print("\nExperiment results:")
    print(
        results
        .groupby("label")[["won_rate", "revenue_per_run", "avg_rep_earnings"]]
        .agg(["mean", "std"])
        .to_string()
    )

    return org_cfg, req_cfg, results


# ---------------------------------------------------------------------------
# Standalone: run the sim with only requirement fitting (no theta fitting)
# ---------------------------------------------------------------------------

def run_with_requirement_config(
    req_cfg: RequirementConfig,
    baseline_path: str = "data/baseline_state.pkl",
    n_runs: int = 100,
    days: int = 90,
):
    """
    Run your existing baseline_state.pkl with a fitted RequirementConfig
    but without touching theta at all.  Good for isolating the effect of
    requirement calibration independently from probability calibration.

    Usage
    -----
        req_cfg = RequirementConfig.load("data/req_config_acme.json")
        results = run_with_requirement_config(req_cfg, n_runs=100, days=90)
    """
    import pickle, copy, random
    from tqdm import tqdm
    from sf_majick.sim.simulate import run_simulation
    from sf_majick.sim.logger import EventLogger
    from sf_majick.sim.micro_policy import simulate_rep_thinking

    with open(baseline_path, "rb") as f:
        baseline = pickle.load(f)

    all_runs = []

    with patched_requirements(req_cfg):
        for run_id in tqdm(range(n_runs)):
            random.seed(run_id)
            state  = copy.deepcopy(baseline)
            logger = EventLogger()

            run_simulation(
                reps         = state["reps"],
                leads        = state.get("leads", []),
                opportunities= state.get("opportunities", []),
                accounts     = state.get("accounts", []),
                days         = days,
                logger       = logger,
                micro_policy = simulate_rep_thinking,
            )

            opps  = state.get("opportunities", [])
            n_won = sum(1 for o in opps if getattr(o, "stage", "") == "Closed Won")
            n_cl  = sum(1 for o in opps if "Closed" in getattr(o, "stage", ""))
            rev   = sum(getattr(o, "revenue", 0) for o in opps if getattr(o, "stage", "") == "Closed Won")

            all_runs.append({
                "run_id":          run_id,
                "n_won":           n_won,
                "won_rate":        n_won / max(n_cl, 1),
                "revenue_per_run": rev,
            })

    import pandas as pd
    return pd.DataFrame(all_runs)

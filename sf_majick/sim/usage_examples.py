"""
usage_examples.py
=================
Three independent workflows — import and run whichever you need.
None of these are required to use the others.
"""

# ===========================================================================
# WORKFLOW 1: Pure sim — no fitting, full control
# ===========================================================================
# This is exactly how you ran the sim before. Nothing changes.

def workflow_1_standalone_sim():
    import pickle, copy, random
    from sf_majick.sim.simulate import run_simulation
    from sf_majick.sim.logger import EventLogger
    from sf_majick.sim.micro_policy import simulate_rep_thinking

    with open("data/baseline_state.pkl", "rb") as f:
        baseline = pickle.load(f)

    state  = copy.deepcopy(baseline)
    logger = EventLogger()

    run_simulation(
        reps         = state["reps"],
        leads        = state.get("leads", []),
        opportunities= state.get("opportunities", []),
        accounts     = state.get("accounts", []),
        days         = 90,
        logger       = logger,
        micro_policy = simulate_rep_thinking,
    )

    print(logger.summary())


# ===========================================================================
# WORKFLOW 2: Parameterised sim via OrgConfig — no fitting required
# ===========================================================================
# Use OrgConfig to explore synthetic org shapes without any real data.

def workflow_2_config_driven_sim():
    from sf_majick.sim.org_config import OrgConfig, RepSlot
    from sf_majick.sim.org_calibrator import build_state_from_config
    from sf_majick.sim.simulate import run_simulation
    from sf_majick.sim.logger import EventLogger
    from sf_majick.sim.micro_policy import simulate_rep_thinking

    # Hand-craft any org shape you want to explore
    cfg = OrgConfig(
        label            = "exploratory_grinder_heavy",
        n_reps           = 10,
        archetype_weights= {"Closer": 0.1, "Nurturer": 0.1, "Grinder": 0.7, "Scattered": 0.1},
        days             = 90,
        base_prob_close  = 0.20,    # hypothesize better close rate
        base_prob_lost   = 0.025,   # hypothesize lower churn
        n_seed_accounts  = 15,
        n_seed_leads     = 6,
    )

    state  = build_state_from_config(cfg)
    logger = EventLogger()

    run_simulation(
        reps         = state["reps"],
        leads        = state["leads"],
        opportunities= state["opportunities"],
        accounts     = state["accounts"],
        days         = cfg.days,
        logger       = logger,
        micro_policy = simulate_rep_thinking,
    )

    print(logger.summary())


# ===========================================================================
# WORKFLOW 3: Fit → experiment — use a real org export as the baseline
# ===========================================================================

def workflow_3_fit_and_experiment():
    import pandas as pd
    from sf_majick.sim.org_config import RepSlot
    from sf_majick.sim.org_calibrator import OrgCalibrator, ExperimentRunner, build_state_from_config
    from sf_majick.sim.simulate import run_simulation
    from sf_majick.sim.micro_policy import simulate_rep_thinking

    # ----------------------------------------------------------------
    # Step 1: Load your Salesforce exports
    # ----------------------------------------------------------------
    # Minimum: just the opportunities DataFrame.
    # Column names should be lower-cased Salesforce field API names.
    opps_df = pd.read_csv("data/sf_opportunities_export.csv")

    # Optional — richer fits when available:
    # users_df    = pd.read_csv("data/sf_users_export.csv")
    # accounts_df = pd.read_csv("data/sf_accounts_export.csv")
    # leads_df    = pd.read_csv("data/sf_leads_export.csv")

    export = {
        "opportunities": opps_df,
        # "users":         users_df,
        # "accounts":      accounts_df,
        # "leads":         leads_df,
    }

    # ----------------------------------------------------------------
    # Step 2: Calibrate — produces an OrgConfig matched to this org
    # ----------------------------------------------------------------
    cal     = OrgCalibrator(export)
    base_cfg = cal.calibrate(label="acme_q3_2025")

    print(cal.validation_report())
    print(base_cfg.describe())

    # Optionally persist the fitted config for later use
    base_cfg.save("data/fitted_config_acme_q3.json")

    # ----------------------------------------------------------------
    # Step 3: Run experiments — the sim never needs to know about fitting
    # ----------------------------------------------------------------
    runner = ExperimentRunner(
        base_config   = base_cfg,
        state_factory = build_state_from_config,
        sim_fn        = run_simulation,
        micro_policy  = simulate_rep_thinking,
        n_iterations  = 200,
    )

    results = runner.compare({
        # Control: the org as-is
        "baseline":                 {},

        # Hypothesis 1: hire 2 more Closers
        "hire_2_closers":           {
            "n_reps":     base_cfg.n_reps + 2,
            "rep_slots":  [RepSlot("Closer", 2, start_day=0)],
            "label":      "hire_2_closers",
        },

        # Hypothesis 2: improve close rate by 5pp (coaching intervention)
        "coaching_close_rate":      {
            "base_prob_close": (base_cfg.base_prob_close or 0.15) + 0.05,
        },

        # Hypothesis 3: reduce stagnation (better pipeline hygiene)
        "pipeline_hygiene":         {
            "inactivity_alpha": (base_cfg.inactivity_alpha or 0.010) * 0.6,
            "stagnation_alpha": (base_cfg.stagnation_alpha or 0.008) * 0.6,
        },

        # Hypothesis 4: shift team toward Grinders
        "grinder_heavy_team":       {
            "archetype_weights": {
                "Closer": 0.15, "Nurturer": 0.10,
                "Grinder": 0.65, "Scattered": 0.10,
            },
        },
    })

    # ----------------------------------------------------------------
    # Step 4: Summarise distributions — not just point estimates
    # ----------------------------------------------------------------
    summary = (
        results
        .groupby("label")[["won_rate", "revenue_per_run", "avg_rep_earnings"]]
        .agg(["mean", "std", "median"])
    )
    print("\nExperiment results:")
    print(summary.to_string())

    # ----------------------------------------------------------------
    # Optional: sensitivity scan on a single lever
    # ----------------------------------------------------------------
    scan = runner.sensitivity_scan(
        param  = "base_prob_close",
        values = [0.10, 0.12, 0.15, 0.18, 0.20, 0.25],
    )
    print("\nClose rate sensitivity scan:")
    print(scan.groupby("label")["won_rate"].mean().to_string())

    return results, scan


# ===========================================================================
# WORKFLOW 4: Load a saved config and experiment from it directly
# ===========================================================================

def workflow_4_load_and_experiment():
    from sf_majick.sim.org_config import OrgConfig
    from sf_majick.sim.org_calibrator import ExperimentRunner, build_state_from_config
    from sf_majick.sim.simulate import run_simulation
    from sf_majick.sim.micro_policy import simulate_rep_thinking

    cfg = OrgConfig.load("data/fitted_config_acme_q3.json")
    print(cfg.describe())

    runner = ExperimentRunner(
        base_config   = cfg,
        state_factory = build_state_from_config,
        sim_fn        = run_simulation,
        micro_policy  = simulate_rep_thinking,
        n_iterations  = 100,
    )

    results = runner.compare({
        "baseline":      {},
        "higher_quota":  {"default_comp_rate": 0.85},   # lower comp → proxy for higher quota pressure
        "more_nurturers":{"archetype_weights": {"Closer":0.2,"Nurturer":0.5,"Grinder":0.2,"Scattered":0.1}},
    })

    print(results.groupby("label")[["won_rate","revenue_per_run"]].mean())
    return results

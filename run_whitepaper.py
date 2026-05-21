"""
run_whitepaper.py
=================
Whitepaper experiment: AND-gate bottleneck diagnosis and repair.

Three conditions:
  tight_and     — high touch + sequence requirements (the "broken" Meridian org)
  default_gates — sim defaults
  loose_or      — relaxed thresholds (the repaired org)

Outputs:
  data/whitepaper_results.csv   — one row per run per condition
  data/whitepaper_summary.csv   — mean metrics by condition
  data/whitepaper_funnel.csv    — mean stage distribution by condition
  data/whitepaper_transitions.csv — mean stage advancement counts by condition

Run:
  cd /home/simonhans/coding/sf_majick
  python run_whitepaper.py
"""

import random
import numpy as np
import pandas as pd
from tqdm import tqdm

from sf_majick.sim.org_config import OrgConfig
from sf_majick.sim.org_calibrator import build_state_from_config
from sf_majick.sim.requirement_config import RequirementConfig
from sf_majick.sim.requirement_integration import patched_requirements
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.micro_policy import simulate_rep_thinking
from sf_majick.sim.logger import EventLogger


# ── Requirement configs ───────────────────────────────────────────────────────

TIGHT_AND = RequirementConfig(
    label="tight_and",
    notes="Meridian-like org: over-engineered gates block Qualification→Proposal",
    # Qualification → Proposal: heavy activity + 2 meetings in sequence
    stage_qualification_min_touches=6,
    stage_qualification_sequence_emails=3,
    stage_qualification_sequence_calls=2,
    stage_qualification_sequence_meetings=2,
    # Proposal → Negotiation: requires 4 deep actions + 2 solution cycles + 2 stakeholder cycles
    stage_proposal_min_deep=4,
    stage_proposal_sequence_solutions=2,
    stage_proposal_sequence_stakeholders=2,
    stage_proposal_min_proposal_sent=2,
    # Negotiation → Close: requires 5 deep actions
    stage_negotiation_min_deep=5,
    stage_negotiation_sequence_solutions=2,
    stage_negotiation_sequence_internals=2,
    stage_negotiation_sequence_followups=2,
)

DEFAULT_GATES = RequirementConfig(label="default_gates")

LOOSE_OR = RequirementConfig(
    label="loose_or",
    notes="Repaired org: gates loosened to OR-equivalent minimum thresholds",
    # Qualification → Proposal: 2 touches, any qualifying sequence
    stage_qualification_min_touches=2,
    stage_qualification_sequence_emails=1,
    stage_qualification_sequence_calls=1,
    stage_qualification_sequence_meetings=1,
    # Proposal → Negotiation: 1 deep action, minimal sequence
    stage_proposal_min_deep=1,
    stage_proposal_sequence_solutions=1,
    stage_proposal_sequence_stakeholders=1,
    stage_proposal_min_proposal_sent=1,
    # Negotiation → Close: 2 deep actions
    stage_negotiation_min_deep=2,
    stage_negotiation_sequence_solutions=1,
    stage_negotiation_sequence_internals=1,
    stage_negotiation_sequence_followups=1,
)


# ── Org config ────────────────────────────────────────────────────────────────

ORG_CFG = OrgConfig(
    label="meridian_base",
    n_reps=3,
    days=60,
    n_seed_accounts=5,
    n_seed_leads=3,
    archetype_weights={
        "Closer":    0.33,
        "Nurturer":  0.17,
        "Grinder":   0.33,
        "Scattered": 0.17,
    },
)

PIPELINE_STAGE_ORDER = [
    "Prospecting", "Qualification", "Proposal", "Negotiation",
    "Closed Won", "Closed Lost",
]


# ── Single run ────────────────────────────────────────────────────────────────

def run_one(org_cfg: OrgConfig, req_cfg: RequirementConfig, run_id: int) -> dict:
    random.seed(run_id)
    np.random.seed(run_id)

    with patched_requirements(req_cfg):
        state  = build_state_from_config(org_cfg)
        logger = EventLogger()
        run_simulation(
            reps         = state["reps"],
            leads        = state.get("leads", []),
            opportunities= state.get("opportunities", []),
            accounts     = state.get("accounts", []),
            days         = org_cfg.days,
            logger       = logger,
            micro_policy = simulate_rep_thinking,
            apply_decay  = org_cfg.apply_decay,
        )

    opps = state.get("opportunities", [])
    reps = state["reps"]

    # Final stage distribution
    stage_counts = {s: 0 for s in PIPELINE_STAGE_ORDER}
    for opp in opps:
        s = getattr(opp, "stage", "Unknown")
        if s in stage_counts:
            stage_counts[s] += 1

    n_won    = stage_counts.get("Closed Won", 0)
    n_closed = stage_counts.get("Closed Won", 0) + stage_counts.get("Closed Lost", 0)
    revenue  = sum(
        getattr(o, "revenue", 0) for o in opps
        if getattr(o, "stage", "") == "Closed Won"
    )

    # Burnout: reps who accumulated any burned-out days
    burnout_reps = sum(1 for r in reps if r.days_burned_out > 0)

    # Stage transition counts from macro log
    transitions = {}
    for e in logger.macro_events:
        if e.get("macro_name") == "Advance Stage" and e.get("advanced"):
            key = f"{e.get('old_stage', '?')}→{e.get('new_stage', '?')}"
            transitions[key] = transitions.get(key, 0) + 1

    record = {
        "run_id":           run_id,
        "won_rate":         n_won / max(n_closed, 1),
        "n_won":            n_won,
        "n_closed":         n_closed,
        "revenue":          revenue,
        "avg_rep_earnings": float(np.mean([r.earnings for r in reps])),
        "burnout_reps":     burnout_reps,
        **{f"stage_{s.replace(' ', '_')}": v for s, v in stage_counts.items()},
        **{f"trans_{k.replace(' ', '_').replace('→', '_to_')}": v
           for k, v in transitions.items()},
    }
    return record


# ── Main experiment loop ──────────────────────────────────────────────────────

N_RUNS = 20

CONDITIONS = [
    ("tight_and",     TIGHT_AND),
    ("default_gates", DEFAULT_GATES),
    ("loose_or",      LOOSE_OR),
]

def main():
    all_records = []

    for label, req_cfg in CONDITIONS:
        print(f"\n[{label}]  {N_RUNS} iterations × {ORG_CFG.days} days")
        for i in tqdm(range(N_RUNS), desc=label):
            # offset seed per condition so runs are independent
            seed = i + abs(hash(label)) % 100_000
            record = run_one(ORG_CFG, req_cfg, run_id=seed)
            record["condition"] = label
            all_records.append(record)

    df = pd.DataFrame(all_records).fillna(0)
    df.to_csv("data/whitepaper_results.csv", index=False)
    print(f"\nSaved {len(df)} rows → data/whitepaper_results.csv")

    # ── Summary metrics ───────────────────────────────────────────────────────
    metrics = ["won_rate", "revenue", "avg_rep_earnings", "burnout_reps"]
    summary = df.groupby("condition")[metrics].agg(["mean", "std"]).round(4)
    summary.to_csv("data/whitepaper_summary.csv")

    # Flatten for readable print
    summary_mean = df.groupby("condition")[metrics].mean().round(4)
    print("\n── Mean metrics by condition ──────────────────────────────────────────")
    print(summary_mean.to_string())

    # ── Funnel shape ──────────────────────────────────────────────────────────
    stage_cols = [f"stage_{s.replace(' ', '_')}" for s in PIPELINE_STAGE_ORDER]
    stage_cols = [c for c in stage_cols if c in df.columns]
    funnel = df.groupby("condition")[stage_cols].mean().round(2)
    funnel.columns = [c.replace("stage_", "") for c in funnel.columns]
    funnel.to_csv("data/whitepaper_funnel.csv")

    print("\n── Mean final stage distribution (deals/run) ──────────────────────────")
    print(funnel.to_string())

    # ── Stage transitions ────────────────────────────────────────────────────
    trans_cols = [c for c in df.columns if c.startswith("trans_")]
    if trans_cols:
        transitions = df.groupby("condition")[trans_cols].mean().round(2)
        transitions.columns = [c.replace("trans_", "").replace("_to_", "→") for c in transitions.columns]
        transitions.to_csv("data/whitepaper_transitions.csv")
        print("\n── Mean stage transitions per run ─────────────────────────────────────")
        print(transitions.to_string())

    # ── Back-fit demonstration ────────────────────────────────────────────────
    # Compute implied stage advancement rates from tight_and run.
    # This mirrors what OrgCalibrator recovers from a SOQL export.
    print("\n── Back-fit: implied advancement rates (tight_and) ────────────────────")
    tight_df = df[df["condition"] == "tight_and"]

    for from_stage, to_stage in [
        ("Prospecting",   "Qualification"),
        ("Qualification", "Proposal"),
        ("Proposal",      "Negotiation"),
        ("Negotiation",   "Closed_Won"),
    ]:
        from_col = f"stage_{from_stage}"
        to_col   = f"stage_{to_stage}"
        if from_col in tight_df.columns and to_col in tight_df.columns:
            from_mean = tight_df[from_col].mean()
            to_mean   = tight_df[to_col].mean()
            denom = from_mean + to_mean
            rate  = to_mean / denom if denom > 0 else float("nan")
            print(f"  {from_stage:15s} → {to_stage:15s}  "
                  f"remaining={from_mean:.2f}  advanced={to_mean:.2f}  "
                  f"implied_rate={rate:.2%}")

    print("\nAll outputs saved to data/")


if __name__ == "__main__":
    main()

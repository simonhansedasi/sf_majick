# run_experiment.py

import pickle
import copy
import random
import argparse
from datetime import datetime
from tqdm import tqdm

from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.logger import EventLogger
from sf_majick.sim.micro_policy import simulate_rep_thinking

def load_baseline(path="data/baseline_state.pkl"):
    """Load baseline state: reps, opportunities, accounts, leads."""
    with open(path, "rb") as f:
        return pickle.load(f)


def run_experiment(n_runs=100, days=30, seed_offset=45):
    """Run multiple simulations and capture detailed telemetry."""
    baseline = load_baseline()

    all_runs = {}
    micro_logs_all = []
    macro_logs_all = []
    opportunity_logs_all = []

    for run_id in tqdm(range(n_runs)):

        # deterministic seed per run
        random.seed(run_id + seed_offset)

        # deep copy baseline state for this run
        state = copy.deepcopy(baseline)
        # print(state.keys())
        # break
        logger = EventLogger()

        # -----------------------------
        # Run simulation
        # -----------------------------
        # print(state.get('accounts',[]))
        run_simulation(
            reps=state["reps"],
            leads=state.get("leads", []),
            opportunities=state.get("opportunities", []),
            accounts=state.get("accounts", []),
            days=days,
            logger=logger,
            micro_policy=simulate_rep_thinking
        )

        # -----------------------------
        # Store full logs
        # -----------------------------
        # Micro events
        for e in logger.micro_events:
            entry = e.copy()
            entry["run_id"] = run_id
            micro_logs_all.append(entry)

        # Macro events
        for e in logger.macro_events:
            entry = e.copy()
            entry["run_id"] = run_id
            macro_logs_all.append(entry)

        # Opportunity-level snapshots
        for e in logger.opportunity_events:
            entry = e.copy()
            entry["run_id"] = run_id
            opportunity_logs_all.append(entry)

        # -----------------------------
        # Lightweight summary
        # -----------------------------
        # print(state.get('leads'))
        run_summary = {
            "reps": {
                r.id: {
                    "earnings": r.earnings,
                    "strategy": getattr(r.strategy, "name", None)
                } for r in state.get("reps", [])
            },
            "opportunities": {
                o.id: {
                    "stage_final": o.stage,
                    "won": o.stage == "Closed Won",
                    "rep_id": o.rep_id,
                    "revenue": o.revenue,
                    'commission': o.commission,
                    "sentiment": o.sentiment,
                    "sentiment_history": o.sentiment_history
                } for o in state.get("opportunities", [])
            },            
            "accounts": {
                a.id: {
                    "personality": getattr(a.personality, "name", None),
                    "rep_id": a.rep_id,
                    "annual_revenue": a.annual_revenue,
                    "opportunities": a.opportunities
                } for a in state.get("accounts", [])
            },
            "leads": {
                l.id: {
                    'rep_id':l.rep_id,
                    'revenue':l.revenue,
                    'commission':l.commission,
                    "stage_final": l.stage,
                    "converted": l.stage == "Closed Converted",
                    "sentiment": l.sentiment,
                    "sentiment_history": l.sentiment_history
                } for l in state.get("leads", [])
            }
        }

        all_runs[f"{run_id}"] = run_summary

    # -----------------------------
    # Return consolidated results
    # -----------------------------
    return {
        "runs": all_runs,
        "micro_logs": micro_logs_all,
        "macro_logs": macro_logs_all,
        "opportunity_logs": opportunity_logs_all,
        "accounts_state": [a for a in baseline.get("accounts", [])],
        "opportunities_state": [o for o in baseline.get("opportunities", [])],
        "leads_state": [l for l in baseline.get("leads", [])],
    }


# ---------------------------------------------------------------------
# Command line entrypoint
# ---------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    results = run_experiment(n_runs=args.runs, days=args.days)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"data/simulation_results_{timestamp}.pkl"

    with open(filename, "wb") as f:
        pickle.dump(results, f)

    print(f"Simulation complete. Saved to {filename}")
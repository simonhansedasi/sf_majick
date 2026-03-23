"""
sentiment_effects.py

Answers: which micro actions move sentiment the most, and by how much?

Produces three dataframes:
  - raw_effects     : mean delta per action (successful only), with CI
  - adjusted_effects: OLS coefficients controlling for stage + rep + run
  - stage_effects   : mean delta per (action, stage) cell

Usage
-----
    from sentiment_effects import build_sentiment_effects
    raw, adjusted, by_stage = build_sentiment_effects(micro, macro, opps_df)
"""

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf
from .sentiment import compute_sentiment_delta, ReplayRep, ReplayEntity


# ------------------------------------------------------------------
# Step 1: Enrich micro log with context
# ------------------------------------------------------------------

def _enrich_micro(
    micro: pd.DataFrame,
    macro: pd.DataFrame,
    opps_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join each micro action row with:
      - the stage the entity was in when the action fired
      - the rep_id (already present, but verify)
      - won outcome and is_lead from opps_df
    
    Returns only successful actions — failed/blocked actions have
    delta=0 by construction and would suppress true effect sizes.
    """

    # Only successful actions have a meaningful sentiment_delta
    m = micro[micro["success"] == True].copy()

    # ------------------------------------------------------------------
    # Assign stage at time of action using macro stage windows
    # macro has: entity_id, day, new_stage, next_day, run_id
    # For each micro row, find the macro row where
    #   macro.day <= micro.day < macro.next_day
    # ------------------------------------------------------------------
    stage_windows = (
        macro[~macro["new_stage"].str.contains("Closed", na=False)]
        [["run_id", "entity_id", "new_stage", "day", "next_day"]]
        .rename(columns={"day": "stage_start", "next_day": "stage_end"})
        .copy()
    )
    # Fill missing stage_end with a large number (entity still in stage at sim end)
    stage_windows["stage_end"] = stage_windows["stage_end"].fillna(99999)

    # Merge on run_id + entity_id, then filter to correct window
    m = m.merge(
        stage_windows,
        left_on=["run_id", "entity_id"],
        right_on=["run_id", "entity_id"],
        how="left",
    )
    m = m[
        (m["day"] >= m["stage_start"]) &
        (m["day"] <  m["stage_end"])
    ].copy()

    # If an action falls in no stage window (e.g. day 0 before first advance),
    # assign "Pre-Stage"
    m["stage"] = m["new_stage"].fillna("Pre-Stage")
    m = m.drop(columns=["new_stage", "stage_start", "stage_end"])

    # ------------------------------------------------------------------
    # Join won / is_lead from opps_df
    # opps_df has entity column = f"{op_id}_{run_id}"
    # ------------------------------------------------------------------
    outcome = opps_df[["entity", "won", "is_lead", "rep_id"]].copy()
    outcome["entity_id"] = outcome["entity"].str.rsplit("_", n=1).str[0]
    outcome["run_id"]    = outcome["entity"].str.rsplit("_", n=1).str[1].astype(int)
    outcome = outcome.drop(columns=["entity"])

    m = m.merge(outcome, on=["run_id", "entity_id"], how="left", suffixes=("", "_snap"))

    # rep_id from micro is ground truth; drop the snapshot version
    if "rep_id_snap" in m.columns:
        m = m.drop(columns=["rep_id_snap"])

    return m


# ------------------------------------------------------------------
# Step 2: Raw effect sizes (mean delta per action, successful only)
# ------------------------------------------------------------------

def _raw_effects(m: pd.DataFrame) -> pd.DataFrame:
    """
    Per action type: mean delta, 95% CI, median, std, n.
    Sorted descending by mean delta.
    """
    records = []
    for action, grp in m.groupby("action"):
        deltas = grp["sentiment_delta"].dropna().values
        n = len(deltas)
        if n == 0:
            continue
        mean   = deltas.mean()
        median = np.median(deltas)
        std    = deltas.std(ddof=1) if n > 1 else 0.0
        se     = std / np.sqrt(n)
        # 95% CI using t-distribution
        t_crit = stats.t.ppf(0.975, df=max(n - 1, 1))
        records.append({
            "action":   action,
            "n":        n,
            "mean_delta":   round(mean,   4),
            "median_delta": round(median, 4),
            "std_delta":    round(std,    4),
            "ci_lower": round(mean - t_crit * se, 4),
            "ci_upper": round(mean + t_crit * se, 4),
            "ci_width":  round(2 * t_crit * se, 4),
        })

    return (
        pd.DataFrame(records)
        .sort_values("mean_delta", ascending=False)
        .reset_index(drop=True)
    )


# ------------------------------------------------------------------
# Step 3: OLS-adjusted effect sizes
# Controls for stage, rep, run_id, and won status
# Coefficient on each action dummy = effect holding context constant
# ------------------------------------------------------------------

def _adjusted_effects(m: pd.DataFrame) -> pd.DataFrame:
    """
    OLS: sentiment_delta ~ action + stage + rep_id + won + run_id

    Returns a dataframe of action coefficients with standard errors,
    t-stats, p-values, and 95% CIs.

    The baseline action (absorbed into intercept) is send_email,
    so all coefficients are relative to send_email's effect.
    """
    # Set send_email as reference so coefficients are intuitive deltas
    # relative to the most common baseline action
    m2 = m.copy()
    m2["action"] = pd.Categorical(
        m2["action"],
        categories=["send_email"] + [
            a for a in sorted(m2["action"].unique()) if a != "send_email"
        ]
    )
    m2["stage"]  = pd.Categorical(m2["stage"])
    m2["won"]    = m2["won"].astype(int)

    # run_id as a categorical fixed effect absorbs run-level variance
    m2["run_id_cat"] = m2["run_id"].astype(str)

    formula = (
        "sentiment_delta ~ C(action) + C(stage) + C(won) + C(run_id_cat)"
    )

    try:
        model  = smf.ols(formula, data=m2).fit()
    except Exception as e:
        print(f"OLS failed: {e}")
        return pd.DataFrame()

    # Extract action coefficients only
    params = model.params
    conf   = model.conf_int()
    pvals  = model.pvalues
    se     = model.bse

    action_rows = [
        idx for idx in params.index if idx.startswith("C(action)")
    ]

    records = []
    # Intercept = send_email baseline
    records.append({
        "action":       "send_email (baseline)",
        "coef":         round(params["Intercept"], 4),
        "se":           round(se["Intercept"], 4),
        "t":            round(model.tvalues["Intercept"], 3),
        "p_value":      round(pvals["Intercept"], 4),
        "ci_lower":     round(conf.loc["Intercept", 0], 4),
        "ci_upper":     round(conf.loc["Intercept", 1], 4),
        "significant":  pvals["Intercept"] < 0.05,
    })

    for idx in action_rows:
        # Parse action name from "C(action)[T.make_call]" etc.
        action_name = idx.split("[T.")[-1].rstrip("]")
        records.append({
            "action":       action_name,
            "coef":         round(params[idx], 4),
            "se":           round(se[idx], 4),
            "t":            round(model.tvalues[idx], 3),
            "p_value":      round(pvals[idx], 4),
            "ci_lower":     round(conf.loc[idx, 0], 4),
            "ci_upper":     round(conf.loc[idx, 1], 4),
            "significant":  pvals[idx] < 0.05,
        })

    result = (
        pd.DataFrame(records)
        .sort_values("coef", ascending=False)
        .reset_index(drop=True)
    )
    result["r_squared"] = round(model.rsquared, 4)
    return result


# ------------------------------------------------------------------
# Step 4: Per-stage breakdown
# ------------------------------------------------------------------

def _stage_effects(m: pd.DataFrame) -> pd.DataFrame:
    """
    Mean sentiment_delta per (action, stage) cell.
    Shows whether an action hits differently depending on pipeline stage.
    Cells with n < 5 are marked unreliable.
    """
    records = []
    for (action, stage), grp in m.groupby(["action", "stage"]):
        deltas = grp["sentiment_delta"].dropna().values
        n = len(deltas)
        if n == 0:
            continue
        mean = deltas.mean()
        std  = deltas.std(ddof=1) if n > 1 else 0.0
        se   = std / np.sqrt(n)
        t_crit = stats.t.ppf(0.975, df=max(n - 1, 1))
        records.append({
            "action":       action,
            "stage":        stage,
            "n":            n,
            "mean_delta":   round(mean, 4),
            "ci_lower":     round(mean - t_crit * se, 4),
            "ci_upper":     round(mean + t_crit * se, 4),
            "reliable":     n >= 5,
        })

    return (
        pd.DataFrame(records)
        .sort_values(["action", "mean_delta"], ascending=[True, False])
        .reset_index(drop=True)
    )


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

def build_sentiment_effects(
    micro: pd.DataFrame,
    macro: pd.DataFrame,
    opps_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Parameters
    ----------
    micro   : raw micro log from run_experiment
    macro   : raw macro log from run_experiment
    opps_df : output of build_opp_df()

    Returns
    -------
    raw_effects     : mean delta per action with 95% CI, n
    adjusted_effects: OLS coefficients relative to send_email baseline
    stage_effects   : mean delta per (action × stage) cell

    Notes
    -----
    Primary path uses the logged sentiment_delta values from the micro log,
    which were produced by sentiment.compute_sentiment_delta() during the sim.

    For counterfactual replay (e.g. "what would delta be if a Closer had fired
    hold_meeting here instead of a Nurturer?"), construct stubs directly:

        rep    = ReplayRep(communicativeness=0.85, focus=0.8, momentum_bias=0.6)
        entity = ReplayEntity(
            sentiment=row.sentiment_total,
            last_sentiment_delta=prev_delta,
            stage=row.stage,
            personality_params={"openness":0.4, "urgency":0.2,
                                 "skepticism":0.8, "price_sensitivity":0.5},
        )
        delta = compute_sentiment_delta(row.action, rep, entity)
    """
    print("Enriching micro log with stage and outcome context...")
    m = _enrich_micro(micro, macro, opps_df)
    print(f"  {len(m):,} successful micro actions retained")

    print("Computing raw effect sizes...")
    raw = _raw_effects(m)

    print("Fitting OLS model...")
    adjusted = _adjusted_effects(m)
    if not adjusted.empty:
        r2 = adjusted["r_squared"].iloc[0]
        print(f"  R² = {r2:.4f}")

    print("Computing per-stage breakdown...")
    by_stage = _stage_effects(m)

    return raw, adjusted, by_stage

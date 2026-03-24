import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
from scipy import stats
from scipy.stats import linregress
import statsmodels.formula.api as smf

# ── Load simulation results ───────────────────────────────────────────────────

results = pd.read_pickle('../sim/data/simulation_results_20260321_231955.pkl')

# ── Build opportunities DataFrame ─────────────────────────────────────────────

rows = []

for run_id, run_data in results['runs'].items():
    accounts = run_data.get("accounts", {})
    account_rep = {a_id: a_data.get("rep_id") for a_id, a_data in accounts.items()}
    for opp_id, opp_data in run_data.get("opportunities", {}).items():
        rep_id = opp_data.get("rep_id")

        rows.append({
            "run_id": run_id,
            "opportunity_id": opp_id,
            "rep_id": rep_id,
            "stage_final": opp_data.get("stage_final"),
            "won": opp_data.get("won"),
            "revenue": opp_data.get("revenue", 0),
            'commission': opp_data['commission'],
            "sentiment": opp_data.get("sentiment", 0),
            "sentiment_history": opp_data.get("sentiment_history", []),
        })

opp_df = pd.DataFrame(rows)
opp_df['run_id'] = opp_df['run_id'].astype(int)

# ── Build leads DataFrame ─────────────────────────────────────────────────────

rows = []

for run_id, run_data in results['runs'].items():
    accounts = run_data.get("accounts", {})

    for opp_id, opp_data in run_data.get("leads", {}).items():
        rep_id = opp_data.get("rep_id")

        history = opp_data.get("sentiment_history", [])
        n = len(history)

        sentiment_mean = sum(history) / max(n, 1)

        if n > 1:
            sentiment_var = sum((x - sentiment_mean) ** 2 for x in history) / (n - 1)
            sentiment_std = sentiment_var ** 0.5
        else:
            sentiment_std = 0

        rows.append({
            "run_id": run_id,
            "opportunity_id": opp_id,
            "rep_id": rep_id,
            "stage_final": opp_data.get("stage_final"),
            "won": opp_data.get("converted"),
            "revenue": opp_data.get("revenue", 0),
            'commission': opp_data.get('commission', 0),
            "sentiment": opp_data.get("sentiment", 0),
            "sentiment_history": opp_data.get("sentiment_history", []),
        })

lead_df = pd.DataFrame(rows)
lead_df['run_id'] = lead_df['run_id'].astype(int)

# ── Concatenate leads and opportunities ───────────────────────────────────────

opps_df = pd.concat([lead_df, opp_df])

# ── Build macro and micro log DataFrames ──────────────────────────────────────

macro = pd.DataFrame(results['macro_logs'])

macro = macro.sort_values(["run_id", "entity_id", "day"])

macro["next_day"] = (
    macro
    .groupby(["run_id", "entity_id"])["day"]
    .shift(-1)
)

macro['days_in_stage'] = macro['next_day'] - macro['day']

micro = pd.DataFrame(results['micro_logs'])

# ── Feature engineering functions ─────────────────────────────────────────────
#
# ==================================================================
# PART 1 — Build terminal state feature dataframe
# Input:  opps_df (raw sim snapshot), macro, micro
# Output: deals  (cleaned terminal state, one row per entity × run)
# ==================================================================

def _action_diversity(micro_opp):
    ALL_ACTIONS = {
        "send_email", "make_call", "hold_meeting", "follow_up",
        "send_proposal", "internal_prep", "research_account",
        "solution_design", "stakeholder_alignment",
    }
    if micro_opp.empty:
        return 0.0
    return len(set(micro_opp["action"].unique()) & ALL_ACTIONS) / len(ALL_ACTIONS)

def _momentum_slope(micro_opp):
    sub = micro_opp[["day", "sentiment_total"]].dropna()
    if len(sub) < 2:
        return 0.0
    slope, *_ = linregress(sub["day"], sub["sentiment_total"])
    return float(slope)

def _touch_recency(micro_opp, close_day):
    if micro_opp.empty:
        return float(close_day)
    return float(close_day - micro_opp["day"].max())

def _stall_count(micro_opp, threshold=5):
    if micro_opp.empty:
        return 0
    days = np.sort(micro_opp["day"].unique())
    if len(days) < 2:
        return 0
    return int((np.diff(days) > threshold).sum())

def _activity_cv(activity_per_stage):
    if len(activity_per_stage) < 2:
        return 0.0
    arr = np.array(activity_per_stage, dtype=float)
    mean = arr.mean()
    return 0.0 if mean == 0 else float(arr.std(ddof=1) / mean)

def _success_rate(micro_opp):
    if micro_opp.empty:
        return 0.0
    return float(micro_opp["success"].mean())

def _prop_late_actions(micro_opp, close_day, window=15):
    if micro_opp.empty:
        return 0.0
    return float((micro_opp["day"] >= close_day - window).sum() / len(micro_opp))


def build_deals(opps_df, macro, micro, n_runs=25, stall_threshold=5, late_window=15):
    """
    Build cleaned terminal-state feature dataframe.

    Parameters
    ----------
    opps_df : raw opportunity/lead snapshot from sim results
    macro   : macro event log
    micro   : micro action log
    n_runs  : number of simulation runs to process

    Returns
    -------
    deals : one row per entity × run, with stage, activity, and sentiment features
    """
    STAGE_ORDER = ["Prospecting", "Qualification", "Proposal", "Negotiation"]
    ACTION_TYPES = [
        "send_email", "make_call", "hold_meeting", "follow_up",
        "send_proposal", "internal_prep", "research_account",
        "solution_design", "stakeholder_alignment",
    ]
    records = []

    for run_id in tqdm(range(n_runs)):
        run_snap  = opps_df[opps_df["run_id"] == run_id]
        run_macro = macro[macro["run_id"] == run_id]
        run_micro = micro[micro["run_id"] == run_id]

        for op in run_snap["opportunity_id"].unique():
            snap      = run_snap[run_snap["opportunity_id"] == op]
            opp_macro = run_macro[run_macro["entity_id"] == op].sort_values("day")
            opp_micro = run_micro[run_micro["entity_id"] == op].sort_values("day")

            if opp_macro.empty:
                continue

            # --- Identity ---
            rep_id      = snap["rep_id"].iloc[0]
            revenue     = snap["revenue"].iloc[0]
            commission  = snap["commission"].iloc[0]
            stage_final = snap["stage_final"].iloc[0]
            won         = bool(snap["won"].iloc[0])
            is_lead     = opp_macro["macro_name"].str.contains("Lead", na=False).any()

            # --- Stage features ---
            stage_rows = opp_macro[
                ~opp_macro["new_stage"].str.contains("Closed", na=False)
            ].copy()
            if stage_rows.empty:
                stage_rows = opp_macro.iloc[[0]]

            n_stages          = len(stage_rows)
            days_per_stage    = stage_rows["days_in_stage"].dropna().values
            avg_days_in_stage = float(np.mean(days_per_stage))    if len(days_per_stage) > 0 else 0.0
            max_days_in_stage = float(np.max(days_per_stage))     if len(days_per_stage) > 0 else 0.0
            days_in_stage_cv  = (
                float(np.std(days_per_stage, ddof=1) / np.mean(days_per_stage))
                if len(days_per_stage) > 1 and np.mean(days_per_stage) > 0 else 0.0
            )

            close_day  = int(opp_macro["day"].max())
            open_day   = int(opp_macro["day"].min())
            cycle_time = close_day - open_day

            deepest = stage_rows["new_stage"].map(
                {s: i for i, s in enumerate(STAGE_ORDER)}
            ).max()
            pipeline_depth = (float(deepest) / (len(STAGE_ORDER) - 1)) if pd.notna(deepest) else 0.0

            # --- Per-stage activity ---
            activity_per_stage = []
            for _, sr in stage_rows.iterrows():
                start = sr["day"]
                end   = sr["next_day"] if pd.notna(sr["next_day"]) else close_day
                activity_per_stage.append(
                    opp_micro[(opp_micro["day"] >= start) & (opp_micro["day"] < end)].shape[0]
                )

            activity_count      = len(opp_micro)
            avg_micro_per_stage = float(np.mean(activity_per_stage)) if activity_per_stage else 0.0
            early_activity      = activity_per_stage[0]  if activity_per_stage else 0
            late_activity       = activity_per_stage[-1] if activity_per_stage else 0
            activity_cv         = _activity_cv(activity_per_stage)
            activity_velocity   = activity_count / cycle_time if cycle_time > 0 else 0.0
            stage_velocity      = n_stages / cycle_time       if cycle_time > 0 else 0.0

            # --- Action quality ---
            total_actions     = max(activity_count, 1)
            action_diversity  = _action_diversity(opp_micro)
            success_rate      = _success_rate(opp_micro)
            momentum_slope    = _momentum_slope(opp_micro)
            touch_recency     = _touch_recency(opp_micro, close_day)
            stall_count       = _stall_count(opp_micro, threshold=stall_threshold)
            prop_late_actions = _prop_late_actions(opp_micro, close_day, window=late_window)
            action_fracs      = {
                f"frac_{a}": opp_micro[opp_micro["action"] == a].shape[0] / total_actions
                for a in ACTION_TYPES
            }

            # --- Sentiment ---
            hist_lists  = snap["sentiment_history"].tolist()
            all_history = [s for sub in hist_lists for s in sub]
            sentiment_final  = float(snap["sentiment"].iloc[-1])
            sentiment_median = float(np.median(all_history))          if all_history else np.nan
            sentiment_std    = float(np.std(all_history, ddof=1))     if len(all_history) > 1 else 0.0
            sentiment_range  = float(np.max(all_history) - np.min(all_history)) if len(all_history) > 1 else 0.0

            records.append({
                "run_id": run_id, "entity": f"{op}_{run_id}",
                "rep_id": rep_id, "is_lead": is_lead,
                "won": won, "stage_final": stage_final,
                "revenue": revenue, "commission": commission,
                "n_stages": n_stages, "pipeline_depth": pipeline_depth,
                "avg_days_in_stage": avg_days_in_stage,
                "max_days_in_stage": max_days_in_stage,
                "days_in_stage_cv": days_in_stage_cv,
                "cycle_time": cycle_time,
                "activity_count": activity_count,
                "avg_micro_per_stage": avg_micro_per_stage,
                "early_activity": early_activity, "late_activity": late_activity,
                "activity_cv": activity_cv,
                "activity_velocity": activity_velocity, "stage_velocity": stage_velocity,
                "action_diversity": action_diversity, "success_rate": success_rate,
                "momentum_slope": momentum_slope, "touch_recency": touch_recency,
                "stall_count": stall_count, "prop_late_actions": prop_late_actions,
                "sentiment_final": sentiment_final, "sentiment_median": sentiment_median,
                "sentiment_std": sentiment_std, "sentiment_range": sentiment_range,
                **action_fracs,
            })

    return pd.DataFrame(records)


# ==================================================================
# PART 2 — Sentiment effect sizes + time series
# Input:  deals (output of build_deals), macro, micro
# Output: raw, adjusted, by_stage, timeseries
# ==================================================================

def _enrich_micro(micro, macro, deals):
    m = micro[micro["success"] == True].copy()

    stage_windows = (
        macro[~macro["new_stage"].str.contains("Closed", na=False)]
        [["run_id", "entity_id", "new_stage", "day", "next_day"]]
        .rename(columns={"day": "stage_start", "next_day": "stage_end"})
        .copy()
    )
    stage_windows["stage_end"] = stage_windows["stage_end"].fillna(99999)

    m = m.merge(stage_windows, on=["run_id", "entity_id"], how="left")
    m = m[(m["day"] >= m["stage_start"]) & (m["day"] < m["stage_end"])].copy()
    m["stage"] = m["new_stage"].fillna("Pre-Stage")
    m = m.drop(columns=["new_stage", "stage_start", "stage_end"])

    outcome = deals[["entity", "won", "is_lead"]].copy()
    outcome["entity_id"] = outcome["entity"].str.rsplit("_", n=1).str[0]
    outcome["run_id"]    = outcome["entity"].str.rsplit("_", n=1).str[1].astype(int)
    outcome = outcome.drop(columns=["entity"])

    m = m.merge(outcome, on=["run_id", "entity_id"], how="left")
    return m


def _raw_effects(m):
    records = []
    for action, grp in m.groupby("action"):
        deltas = grp["sentiment_delta"].dropna().values
        n = len(deltas)
        if n == 0:
            continue
        mean, median = deltas.mean(), np.median(deltas)
        std  = deltas.std(ddof=1) if n > 1 else 0.0
        se   = std / np.sqrt(n)
        tc   = stats.t.ppf(0.975, df=max(n - 1, 1))
        records.append({
            "action": action, "n": n,
            "mean_delta": round(mean, 4), "median_delta": round(median, 4),
            "std_delta": round(std, 4),
            "ci_lower": round(mean - tc * se, 4), "ci_upper": round(mean + tc * se, 4),
            "ci_width": round(2 * tc * se, 4),
        })
    return pd.DataFrame(records).sort_values("mean_delta", ascending=False).reset_index(drop=True)


def _adjusted_effects(m):
    m2 = m.copy()
    m2["action"] = pd.Categorical(
        m2["action"],
        categories=["send_email"] + [a for a in sorted(m2["action"].unique()) if a != "send_email"]
    )
    m2["stage"]      = pd.Categorical(m2["stage"])
    m2["won"]        = m2["won"].astype(int)
    m2["run_id_cat"] = m2["run_id"].astype(str)

    try:
        model = smf.ols(
            "sentiment_delta ~ C(action) + C(stage) + C(won) + C(run_id_cat)",
            data=m2
        ).fit()
    except Exception as e:
        print(f"OLS failed: {e}")
        return pd.DataFrame()

    params, conf, pvals, se = model.params, model.conf_int(), model.pvalues, model.bse

    records = [{
        "action": "send_email (baseline)",
        "coef": round(params["Intercept"], 4), "se": round(se["Intercept"], 4),
        "t": round(model.tvalues["Intercept"], 3), "p_value": round(pvals["Intercept"], 4),
        "ci_lower": round(conf.loc["Intercept", 0], 4),
        "ci_upper": round(conf.loc["Intercept", 1], 4),
        "significant": pvals["Intercept"] < 0.05,
    }]
    for idx in [i for i in params.index if i.startswith("C(action)")]:
        action_name = idx.split("[T.")[-1].rstrip("]")
        records.append({
            "action": action_name,
            "coef": round(params[idx], 4), "se": round(se[idx], 4),
            "t": round(model.tvalues[idx], 3), "p_value": round(pvals[idx], 4),
            "ci_lower": round(conf.loc[idx, 0], 4), "ci_upper": round(conf.loc[idx, 1], 4),
            "significant": pvals[idx] < 0.05,
        })

    result = pd.DataFrame(records).sort_values("coef", ascending=False).reset_index(drop=True)
    result["r_squared"] = round(model.rsquared, 4)
    return result


def _stage_effects(m):
    records = []
    for (action, stage), grp in m.groupby(["action", "stage"]):
        deltas = grp["sentiment_delta"].dropna().values
        n = len(deltas)
        if n == 0:
            continue
        mean = deltas.mean()
        std  = deltas.std(ddof=1) if n > 1 else 0.0
        se   = std / np.sqrt(n)
        tc   = stats.t.ppf(0.975, df=max(n - 1, 1))
        records.append({
            "action": action, "stage": stage, "n": n,
            "mean_delta": round(mean, 4),
            "ci_lower": round(mean - tc * se, 4), "ci_upper": round(mean + tc * se, 4),
            "reliable": n >= 5,
        })
    return (
        pd.DataFrame(records)
        .sort_values(["action", "mean_delta"], ascending=[True, False])
        .reset_index(drop=True)
    )


def _sentiment_timeseries(m, deals):
    cycle = deals[["entity", "cycle_time", "won", "is_lead"]].copy()
    cycle["entity_id"] = cycle["entity"].str.rsplit("_", n=1).str[0]
    cycle["run_id"]    = cycle["entity"].str.rsplit("_", n=1).str[1].astype(int)
    cycle = cycle.drop(columns=["entity"])

    # Drop won/is_lead already on m from _enrich_micro before re-joining
    m2 = m.drop(columns=["won", "is_lead"], errors="ignore")
    m2 = m2.merge(
        cycle[["run_id", "entity_id", "cycle_time", "won", "is_lead"]],
        on=["run_id", "entity_id"], how="left",
    )

    day_agg = (
        m2.groupby(["run_id", "entity_id", "day", "won", "is_lead", "cycle_time"])
        .agg(
            mean_delta      = ("sentiment_delta", "mean"),
            sum_delta       = ("sentiment_delta", "sum"),
            sentiment_level = ("sentiment_total", "last"),
            n_actions       = ("action", "count"),
        )
        .reset_index()
    )

    day_agg["t_norm"] = np.where(
        day_agg["cycle_time"] > 0,
        day_agg["day"] / day_agg["cycle_time"], 0.0
    ).clip(0, 1)

    return day_agg.sort_values(["run_id", "entity_id", "day"]).reset_index(drop=True)


def build_sentiment_effects(micro, macro, deals):
    """
    Parameters
    ----------
    micro  : micro log
    macro  : macro log
    deals  : output of build_deals()

    Returns
    -------
    raw, adjusted, by_stage, timeseries
    """
    print("Enriching micro log...")
    m = _enrich_micro(micro, macro, deals)
    print(f"  {len(m):,} successful actions retained")

    print("Raw effect sizes...")
    raw = _raw_effects(m)

    print("OLS adjusted effects...")
    adjusted = _adjusted_effects(m)
    if not adjusted.empty:
        print(f"  R² = {adjusted['r_squared'].iloc[0]:.4f}")

    print("Per-stage breakdown...")
    by_stage = _stage_effects(m)

    print("Building sentiment time series...")
    timeseries = _sentiment_timeseries(m, deals)

    return raw, adjusted, by_stage, timeseries


# ==================================================================
# RUN
# opps_df = raw sim snapshot (input, untouched)
# deals   = cleaned terminal state (output)
# ==================================================================

deals = build_deals(opps_df, macro, micro, n_runs=15)

raw, adjusted, by_stage, timeseries = build_sentiment_effects(micro, macro, deals)

# Actions with statistically significant effects
print(adjusted[adjusted["significant"] == True][["action", "coef", "se", "t", "p_value"]])

deals.to_pickle('../sim/data/df.pkl')

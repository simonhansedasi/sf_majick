"""
requirement_miner.py
====================
Fits a RequirementConfig from Salesforce activity and stage-history exports.

What it does
------------
1. Maps Salesforce activity types (TaskSubtype, Event Subject) → sim action names
2. Reconstructs per-opportunity action sequences from Task + Event exports
3. Splits sequences by stage using OpportunityFieldHistory
4. Computes action-count distributions across winning deals
5. Sets RequirementConfig thresholds at a chosen percentile of winners
   (default p25: the bottom quartile of winning deals sets the floor —
    achievable without being trivially easy)

Salesforce exports needed
-------------------------
task_df         : Task SOQL export
                  SELECT Id, WhatId, TaskSubtype, Status, ActivityDate, CreatedDate
                  FROM Task WHERE WhatId IN :opp_ids

event_df        : Event SOQL export
                  SELECT Id, WhatId, Subject, ActivityDateTime, CreatedDate
                  FROM Event WHERE WhatId IN :opp_ids

stage_history_df: OpportunityFieldHistory export
                  SELECT OpportunityId, Field, OldValue, NewValue, CreatedDate
                  FROM OpportunityFieldHistory WHERE Field = 'StageName'

opp_df          : Opportunities export (for filtering won/lost)
                  SELECT Id, StageName, CloseDate, CreatedDate, OwnerId, Amount
                  FROM Opportunity

All DataFrames should have lower-cased column names.

Example
-------
    from sf_majick.sim.requirement_miner import RequirementMiner

    miner = RequirementMiner(
        task_df=pd.read_csv("data/tasks.csv"),
        event_df=pd.read_csv("data/events.csv"),
        stage_history_df=pd.read_csv("data/stage_history.csv"),
        opp_df=pd.read_csv("data/opportunities.csv"),
    )

    req_cfg = miner.mine(percentile=25, label="acme_q3")
    print(miner.report())
    req_cfg.save("data/req_config_acme.json")

    # Inspect raw sequences if you want to see what was found
    seq_df = miner.sequences_df()
    stage_df = miner.stage_activity_df()
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

from .requirement_config import RequirementConfig


# ---------------------------------------------------------------------------
# Salesforce → sim action name mapping
# ---------------------------------------------------------------------------

# TaskSubtype values (Salesforce standard)
TASK_SUBTYPE_MAP: dict[str, str] = {
    "Email":          "send_email",
    "Call":           "make_call",
    "List Email":     "send_email",
    "Task":           "follow_up",
    "Assigned":       "internal_prep",
    "Draft":          "internal_prep",
    # Common custom values
    "Follow Up":      "follow_up",
    "Research":       "research_account",
    "Proposal":       "send_proposal",
    "Demo":           "hold_meeting",
}

# Event Subject keywords → sim action names (case-insensitive substring match)
EVENT_SUBJECT_MAP: list[tuple[str, str]] = [
    ("meeting",      "hold_meeting"),
    ("demo",         "hold_meeting"),
    ("discovery",    "hold_meeting"),
    ("call",         "make_call"),
    ("proposal",     "send_proposal"),
    ("follow",       "follow_up"),
    ("stakeholder",  "stakeholder_alignment"),
    ("solution",     "solution_design"),
    ("design",       "solution_design"),
    ("research",     "research_account"),
    ("prep",         "internal_prep"),
    ("internal",     "internal_prep"),
]

# Salesforce standard stage names → sim stage names
SF_STAGE_MAP: dict[str, str] = {
    "prospecting":              "Prospecting",
    "qualification":            "Qualification",
    "needs analysis":           "Qualification",
    "value proposition":        "Proposal",
    "id. decision makers":      "Proposal",
    "perception analysis":      "Proposal",
    "proposal/price quote":     "Proposal",
    "proposal":                 "Proposal",
    "negotiation/review":       "Negotiation",
    "negotiation":              "Negotiation",
    "closed won":               "Closed Won",
    "closed lost":              "Closed Lost",
}

SIM_ACTIONS = [
    "send_email", "make_call", "hold_meeting", "follow_up",
    "send_proposal", "internal_prep", "research_account",
    "solution_design", "stakeholder_alignment",
]

STAGE_ORDER = ["Prospecting", "Qualification", "Proposal", "Negotiation"]


# ---------------------------------------------------------------------------
# RequirementMiner
# ---------------------------------------------------------------------------

class RequirementMiner:

    def __init__(
        self,
        task_df: pd.DataFrame,
        event_df: Optional[pd.DataFrame] = None,
        stage_history_df: Optional[pd.DataFrame] = None,
        opp_df: Optional[pd.DataFrame] = None,
        task_subtype_map: Optional[dict[str, str]] = None,
        event_subject_map: Optional[list[tuple[str, str]]] = None,
        sf_stage_map: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Parameters
        ----------
        task_df          : Salesforce Task export (required)
        event_df         : Salesforce Event export (optional but recommended)
        stage_history_df : OpportunityFieldHistory export (optional)
        opp_df           : Opportunity export for outcome filtering (optional)
        task_subtype_map : Override default TASK_SUBTYPE_MAP
        event_subject_map: Override default EVENT_SUBJECT_MAP
        sf_stage_map     : Override default SF_STAGE_MAP
        """
        self._task_df      = self._norm(task_df)
        self._event_df     = self._norm(event_df)     if event_df is not None     else pd.DataFrame()
        self._history_df   = self._norm(stage_history_df) if stage_history_df is not None else pd.DataFrame()
        self._opp_df       = self._norm(opp_df)       if opp_df is not None       else pd.DataFrame()

        self._task_map   = task_subtype_map  or TASK_SUBTYPE_MAP
        self._event_map  = event_subject_map or EVENT_SUBJECT_MAP
        self._stage_map  = sf_stage_map      or SF_STAGE_MAP

        # Populated by mine()
        self._req_cfg: Optional[RequirementConfig] = None
        self._stats: dict = {}

        # Cache built by _build_activity_df()
        self._activity_df: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mine(self, percentile: int = 25, label: str = "mined") -> RequirementConfig:
        """
        Fit a RequirementConfig from the exports.

        Parameters
        ----------
        percentile : Which percentile of winning-deal action counts to use
                     as the requirement threshold.  25 = bottom quartile of
                     winners (achievable but not trivial).  Use 10 for very
                     permissive gates, 50 for median-winner gates.
        label      : Label stored in the returned config.

        Returns
        -------
        RequirementConfig with fitted count thresholds.
        """
        acts = self._build_activity_df()
        won_ids = self._won_opp_ids()

        # Per-opp total action counts across all stages
        opp_counts = self._opp_action_counts(acts, won_ids)

        # Per-opp action counts split by stage window
        stage_counts = self._stage_action_counts(acts, won_ids)

        p = percentile

        def pct(series: pd.Series, fallback: int) -> int:
            if series.empty:
                return fallback
            return max(1, int(np.percentile(series.dropna(), p)))

        def stage_pct(stage: str, action: str, fallback: int) -> int:
            sub = stage_counts.get(stage, pd.DataFrame())
            if sub.empty or action not in sub.columns:
                return fallback
            return max(1, int(np.percentile(sub[action].dropna(), p)))

        # ------------------------------------------------------------------
        # Micro action gates — from total-opp counts of winning deals
        # ------------------------------------------------------------------
        c = RequirementConfig(label=label)

        if not opp_counts.empty:

            c.micro_research_min_email_or_call = pct(
                opp_counts[["send_email", "make_call"]].min(axis=1), c.micro_research_min_email_or_call
            )
            c.micro_internal_min_touches = pct(
                opp_counts["send_email"] + opp_counts["make_call"], c.micro_internal_min_touches
            )
            c.micro_solution_min_touches = pct(
                opp_counts[["send_email", "make_call", "research_account"]].sum(axis=1),
                c.micro_solution_min_touches,
            )
            c.micro_stakeholder_min_touches = pct(
                opp_counts[["make_call", "send_email", "follow_up"]].sum(axis=1),
                c.micro_stakeholder_min_touches,
            )
            c.micro_meeting_min_touches = pct(
                opp_counts[["send_email", "make_call"]].sum(axis=1),
                c.micro_meeting_min_touches,
            )
            c.micro_meeting_sequence_emails = pct(
                opp_counts["send_email"], c.micro_meeting_sequence_emails
            )
            c.micro_meeting_sequence_calls = pct(
                opp_counts["make_call"], c.micro_meeting_sequence_calls
            )
            c.micro_followup_min_touches = pct(
                opp_counts[["send_email", "make_call"]].sum(axis=1),
                c.micro_followup_min_touches,
            )
            c.micro_followup_chance_emails = pct(
                opp_counts["send_email"], c.micro_followup_chance_emails
            )
            c.micro_followup_chance_calls = pct(
                opp_counts["make_call"], c.micro_followup_chance_calls
            )
            # Proposal lightweight path
            c.micro_proposal_min_touches = pct(
                opp_counts[["send_email", "make_call"]].sum(axis=1),
                c.micro_proposal_min_touches,
            )
            c.micro_proposal_min_meeting_or_followup = pct(
                opp_counts[["hold_meeting", "follow_up"]].sum(axis=1),
                c.micro_proposal_min_meeting_or_followup,
            )
            c.micro_proposal_min_deep_action = pct(
                opp_counts[["solution_design", "stakeholder_alignment", "internal_prep"]].sum(axis=1),
                c.micro_proposal_min_deep_action,
            )
            # Proposal nurture path — use 75th pct (a long path should reflect heavy nurturers)
            hi = 75
            def hi_pct(series, fallback):
                if series.empty:
                    return fallback
                return max(1, int(np.percentile(series.dropna(), hi)))

            c.micro_proposal_nurture_emails   = hi_pct(opp_counts["send_email"],   c.micro_proposal_nurture_emails)
            c.micro_proposal_nurture_calls    = hi_pct(opp_counts["make_call"],    c.micro_proposal_nurture_calls)
            c.micro_proposal_nurture_followups = hi_pct(opp_counts["follow_up"],   c.micro_proposal_nurture_followups)
            c.micro_proposal_nurture_meetings  = hi_pct(opp_counts["hold_meeting"],c.micro_proposal_nurture_meetings)
            c.micro_proposal_nurture_solutions = hi_pct(opp_counts["solution_design"], c.micro_proposal_nurture_solutions)

        # ------------------------------------------------------------------
        # Stage advancement gates — from per-stage activity windows
        # ------------------------------------------------------------------

        def _stage_touches(stage: str, actions: list[str], fallback: int) -> int:
            sub = stage_counts.get(stage, pd.DataFrame())
            if sub.empty:
                return fallback
            avail = [a for a in actions if a in sub.columns]
            if not avail:
                return fallback
            return pct(sub[avail].sum(axis=1), fallback)

        c.stage_lead_min_touches = _stage_touches(
            "Lead", ["research_account", "send_email", "make_call"], c.stage_lead_min_touches
        )
        c.stage_lead_sequence_emails = stage_pct("Lead", "send_email", c.stage_lead_sequence_emails)
        c.stage_lead_sequence_calls  = stage_pct("Lead", "make_call",  c.stage_lead_sequence_calls)

        c.stage_prospecting_min_touches = _stage_touches(
            "Prospecting", ["send_email", "make_call", "research_account"],
            c.stage_prospecting_min_touches,
        )
        c.stage_prospecting_sequence_emails = stage_pct("Prospecting", "send_email", c.stage_prospecting_sequence_emails)
        c.stage_prospecting_sequence_calls  = stage_pct("Prospecting", "make_call",  c.stage_prospecting_sequence_calls)

        c.stage_qualification_min_touches = _stage_touches(
            "Qualification", ["send_email", "make_call", "research_account", "hold_meeting"],
            c.stage_qualification_min_touches,
        )
        c.stage_qualification_sequence_emails   = stage_pct("Qualification", "send_email",    c.stage_qualification_sequence_emails)
        c.stage_qualification_sequence_calls    = stage_pct("Qualification", "make_call",     c.stage_qualification_sequence_calls)
        c.stage_qualification_sequence_meetings = stage_pct("Qualification", "hold_meeting",  c.stage_qualification_sequence_meetings)

        c.stage_proposal_min_deep = _stage_touches(
            "Proposal",
            ["follow_up", "hold_meeting", "internal_prep", "solution_design", "stakeholder_alignment"],
            c.stage_proposal_min_deep,
        )
        c.stage_proposal_sequence_solutions    = stage_pct("Proposal", "solution_design",       c.stage_proposal_sequence_solutions)
        c.stage_proposal_sequence_stakeholders = stage_pct("Proposal", "stakeholder_alignment", c.stage_proposal_sequence_stakeholders)

        c.stage_negotiation_min_deep = _stage_touches(
            "Negotiation",
            ["research_account", "internal_prep", "follow_up",
             "hold_meeting", "solution_design", "stakeholder_alignment"],
            c.stage_negotiation_min_deep,
        )
        c.stage_negotiation_sequence_solutions = stage_pct("Negotiation", "solution_design", c.stage_negotiation_sequence_solutions)
        c.stage_negotiation_sequence_internals = stage_pct("Negotiation", "internal_prep",  c.stage_negotiation_sequence_internals)
        c.stage_negotiation_sequence_followups = stage_pct("Negotiation", "follow_up",      c.stage_negotiation_sequence_followups)

        # ------------------------------------------------------------------
        # Lead conversion gate — from total-opp counts of all won deals
        # ------------------------------------------------------------------
        if not opp_counts.empty:
            c.lead_min_emails            = pct(opp_counts["send_email"], c.lead_min_emails)
            c.lead_min_calls_if_no_meeting = pct(opp_counts["make_call"], c.lead_min_calls_if_no_meeting)

        c.fitted_percentile = percentile
        c.notes = (
            f"Mined from {len(won_ids)} won opps, "
            f"{len(acts):,} activity records. "
            f"Thresholds at p{percentile} of winners."
        )

        self._req_cfg = c
        self._stats = {
            "n_won_opps":      len(won_ids),
            "n_activity_rows": len(acts),
            "percentile":      percentile,
        }
        return c

    def report(self) -> str:
        """Human-readable summary of the mining run. Call after mine()."""
        if self._req_cfg is None:
            return "Call mine() first."
        lines = [
            "=" * 60,
            "RequirementMiner Report",
            "=" * 60,
            f"  Won opps analysed  : {self._stats.get('n_won_opps', 'n/a')}",
            f"  Activity records   : {self._stats.get('n_activity_rows', 'n/a'):,}",
            f"  Threshold percentile: p{self._stats.get('percentile', '?')}",
            "",
            self._req_cfg.describe(),
            "=" * 60,
        ]
        return "\n".join(lines)

    def sequences_df(self) -> pd.DataFrame:
        """
        Return the raw per-opp action count DataFrame used for fitting.
        Useful for sanity-checking: inspect distributions before committing
        to a percentile.
        """
        acts = self._build_activity_df()
        won_ids = self._won_opp_ids()
        return self._opp_action_counts(acts, won_ids)

    def stage_activity_df(self) -> dict[str, pd.DataFrame]:
        """
        Return per-stage action count DataFrames.
        Keys are sim stage names; values are DataFrames (one row per opp).
        """
        acts = self._build_activity_df()
        won_ids = self._won_opp_ids()
        return self._stage_action_counts(acts, won_ids)

    # ------------------------------------------------------------------
    # Internal: normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _norm(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [c.lower().strip() for c in df.columns]
        return df

    # ------------------------------------------------------------------
    # Internal: activity DataFrame assembly
    # ------------------------------------------------------------------

    def _build_activity_df(self) -> pd.DataFrame:
        """
        Combine Task and Event exports into a single activity DataFrame with
        columns: opp_id, date, sim_action.
        """
        if self._activity_df is not None:
            return self._activity_df

        records = []

        # ---- Tasks ----
        t = self._task_df
        if not t.empty:
            opp_col  = next((c for c in ("whatid", "what_id") if c in t.columns), None)
            type_col = next((c for c in ("tasksubtype", "task_subtype", "type") if c in t.columns), None)
            date_col = next((c for c in ("activitydate", "activity_date", "createddate") if c in t.columns), None)

            if opp_col and type_col:
                for _, row in t.iterrows():
                    action = self._task_map.get(str(row.get(type_col, "")), None)
                    if action is None:
                        continue
                    date = pd.to_datetime(row.get(date_col), errors="coerce") if date_col else pd.NaT
                    records.append({
                        "opp_id":     row[opp_col],
                        "date":       date,
                        "sim_action": action,
                        "source":     "task",
                    })
            else:
                warnings.warn(
                    "task_df missing expected columns (whatid/tasksubtype). "
                    "Tasks will not contribute to fitting.",
                    UserWarning,
                )

        # ---- Events ----
        e = self._event_df
        if not e.empty:
            opp_col  = next((c for c in ("whatid", "what_id") if c in e.columns), None)
            subj_col = next((c for c in ("subject",) if c in e.columns), None)
            date_col = next((c for c in ("activitydatetime", "activity_date_time", "createddate") if c in e.columns), None)

            if opp_col and subj_col:
                for _, row in e.iterrows():
                    subj   = str(row.get(subj_col, "")).lower()
                    action = None
                    for keyword, act in self._event_map:
                        if keyword in subj:
                            action = act
                            break
                    if action is None:
                        action = "hold_meeting"   # default: any event = a meeting
                    date = pd.to_datetime(row.get(date_col), errors="coerce") if date_col else pd.NaT
                    records.append({
                        "opp_id":     row[opp_col],
                        "date":       date,
                        "sim_action": action,
                        "source":     "event",
                    })

        if not records:
            warnings.warn("No activity records could be parsed from task_df / event_df.", UserWarning)
            self._activity_df = pd.DataFrame(columns=["opp_id", "date", "sim_action", "source"])
            return self._activity_df

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values(["opp_id", "date"]).reset_index(drop=True)
        self._activity_df = df
        return df

    # ------------------------------------------------------------------
    # Internal: outcome filtering
    # ------------------------------------------------------------------

    def _won_opp_ids(self) -> set:
        """Return a set of opportunity IDs that closed won."""
        if self._opp_df.empty:
            # No opp_df supplied — treat all activity opp_ids as potential winners.
            # This degrades the fit but doesn't break it.
            warnings.warn(
                "No opp_df supplied. Cannot filter to won deals; using all opp IDs in activity log.",
                UserWarning,
            )
            acts = self._build_activity_df()
            return set(acts["opp_id"].unique())

        stage_col = next((c for c in ("stagename", "stage") if c in self._opp_df.columns), None)
        id_col    = next((c for c in ("id",) if c in self._opp_df.columns), None)

        if not stage_col or not id_col:
            warnings.warn(
                "opp_df missing 'id' or 'stagename' column. Using all opp IDs.",
                UserWarning,
            )
            return set(self._opp_df.get("id", pd.Series()).unique())

        won = self._opp_df[
            self._opp_df[stage_col].str.lower().str.strip() == "closed won"
        ]
        return set(won[id_col].unique())

    # ------------------------------------------------------------------
    # Internal: count aggregation
    # ------------------------------------------------------------------

    def _opp_action_counts(self, acts: pd.DataFrame, won_ids: set) -> pd.DataFrame:
        """
        For each won opp, count total occurrences of each sim_action.
        Returns a DataFrame (one row per opp, one column per action).
        """
        if acts.empty:
            return pd.DataFrame()

        won_acts = acts[acts["opp_id"].isin(won_ids)]
        if won_acts.empty:
            warnings.warn("No activity records matched to won opportunities.", UserWarning)
            return pd.DataFrame()

        grouped = (
            won_acts.groupby(["opp_id", "sim_action"])
            .size()
            .unstack(fill_value=0)
            .reindex(columns=SIM_ACTIONS, fill_value=0)
        )
        return grouped

    def _stage_action_counts(self, acts: pd.DataFrame, won_ids: set) -> dict[str, pd.DataFrame]:
        """
        For each sim stage, return a DataFrame of per-opp action counts
        restricted to activities that occurred *within that stage window*.

        Requires stage_history_df.  If not supplied, returns an empty dict
        and fits will fall back to defaults for stage-level counts.
        """
        if self._history_df.empty:
            return {}

        h = self._history_df
        opp_col    = next((c for c in ("opportunityid", "opp_id") if c in h.columns), None)
        old_col    = next((c for c in ("oldvalue", "old_value") if c in h.columns), None)
        new_col    = next((c for c in ("newvalue", "new_value") if c in h.columns), None)
        date_col   = next((c for c in ("createddate", "created_date") if c in h.columns), None)

        if not all([opp_col, new_col, date_col]):
            warnings.warn(
                "stage_history_df missing expected columns. Stage-level fitting will use defaults.",
                UserWarning,
            )
            return {}

        # Normalise stage names
        h = h.copy()
        h["sim_stage"] = h[new_col].str.lower().str.strip().map(self._stage_map)
        h["date"]      = pd.to_datetime(h[date_col], errors="coerce")
        h = h[h["sim_stage"].notna()].sort_values([opp_col, "date"])

        # Build stage windows per opp
        stage_windows = []
        for opp_id, grp in h[h[opp_col].isin(won_ids)].groupby(opp_col):
            rows = grp.sort_values("date").reset_index(drop=True)
            for i, row in rows.iterrows():
                start = row["date"]
                end   = rows.loc[i + 1, "date"] if i + 1 < len(rows) else pd.Timestamp.max
                stage_windows.append({
                    "opp_id":    opp_id,
                    "sim_stage": row["sim_stage"],
                    "start":     start,
                    "end":       end,
                })

        if not stage_windows:
            return {}

        windows_df = pd.DataFrame(stage_windows)
        won_acts   = acts[acts["opp_id"].isin(won_ids)].copy()

        result: dict[str, pd.DataFrame] = {}

        for stage in STAGE_ORDER:
            stage_wins = windows_df[windows_df["sim_stage"] == stage]
            if stage_wins.empty:
                continue

            records = []
            for _, w in stage_wins.iterrows():
                opp_acts = won_acts[
                    (won_acts["opp_id"] == w["opp_id"]) &
                    (won_acts["date"] >= w["start"]) &
                    (won_acts["date"] <  w["end"])
                ]
                counts = opp_acts["sim_action"].value_counts().to_dict()
                counts["opp_id"] = w["opp_id"]
                records.append(counts)

            if not records:
                continue

            df = pd.DataFrame(records).fillna(0)
            df = df.reindex(columns=["opp_id"] + SIM_ACTIONS, fill_value=0)
            result[stage] = df.drop(columns=["opp_id"])

        return result

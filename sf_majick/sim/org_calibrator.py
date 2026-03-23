"""
org_calibrator.py
=================
Two independent, composable tools:

1. OrgCalibrator
   Takes a Salesforce export (as a dict of DataFrames or a single DataFrame)
   and produces an OrgConfig whose probability fields are fitted to match
   the org's observed conversion rates, cycle times, and pipeline shape.

   The calibrator is completely optional.  The sim never imports it.
   You can run the sim with a hand-crafted OrgConfig or with all defaults.

2. ExperimentRunner
   Takes any OrgConfig (fitted or synthetic) and a sim-state factory,
   runs many iterations of the sim with optional parameter perturbations,
   and returns distributions of outcomes for hypothesis comparison.

Separation guarantee
--------------------
- The sim (simulate.py / run_simulation.py) does NOT import anything from
  this file.  It accepts reps/leads/opps/accounts built however you like.
- This file imports from the sim only to call build_state_from_config()
  and run_simulation().  Everything else is pure data plumbing.
"""

from __future__ import annotations

import copy
import random
import warnings
from dataclasses import replace
from typing import Callable, Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

from .org_config import OrgConfig, RepSlot


# ---------------------------------------------------------------------------
# Helpers shared by calibrator and runner
# ---------------------------------------------------------------------------

def _safe_rate(numerator: int, denominator: int, default: float = 0.0) -> float:
    """Avoid ZeroDivisionError; return default when denominator is zero."""
    return numerator / denominator if denominator > 0 else default


# ---------------------------------------------------------------------------
# 1. OrgCalibrator
# ---------------------------------------------------------------------------

class OrgCalibrator:
    """
    Fit an OrgConfig to a Salesforce export.

    Accepts a dict of DataFrames with the following expected keys:
        "opportunities"  – one row per opportunity
        "users"          – one row per active rep / user  (optional)
        "accounts"       – one row per account            (optional)
        "leads"          – one row per lead               (optional)

    Each DataFrame is expected to have been produced by a SOQL export and
    lightly normalised (column names lower-cased).  The calibrator is
    deliberately lenient: missing columns fall back to sim defaults.

    Minimum viable export
    ---------------------
    A single "opportunities" DataFrame with at least:
        stage, amount, close_date, created_date, owner_id

    Everything else enriches the fit but is optional.

    Example
    -------
        export = {
            "opportunities": pd.read_csv("opps.csv"),
            "users":         pd.read_csv("users.csv"),
            "accounts":      pd.read_csv("accounts.csv"),
            "leads":         pd.read_csv("leads.csv"),
        }
        cal = OrgCalibrator(export)
        cfg = cal.calibrate(label="q3_acme")
        print(cal.validation_report())
    """

    # Map from Salesforce stage names → sim stage names.
    # Extend or override this if the org uses custom stages.
    STAGE_MAP: dict[str, str] = {
        # Common SF stage names → sim stages
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

    def __init__(self, export: dict[str, pd.DataFrame] | pd.DataFrame) -> None:
        # Accept a bare DataFrame as shorthand for {"opportunities": df}
        if isinstance(export, pd.DataFrame):
            export = {"opportunities": export}

        self._opps: pd.DataFrame     = self._normalise_opps(export.get("opportunities", pd.DataFrame()))
        self._users: pd.DataFrame    = self._normalise(export.get("users", pd.DataFrame()))
        self._accounts: pd.DataFrame = self._normalise(export.get("accounts", pd.DataFrame()))
        self._leads: pd.DataFrame    = self._normalise(export.get("leads", pd.DataFrame()))

        # Populated by calibrate(); used by validation_report()
        self._fitted_config: Optional[OrgConfig] = None
        self._fit_stats: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calibrate(self, label: str = "fitted") -> OrgConfig:
        """
        Derive an OrgConfig from the export.

        Returns an OrgConfig with only the fields that can be meaningfully
        estimated from the data set as non-None.  All other fields keep
        their sim defaults so the result is always a valid, runnable config.
        """
        kwargs: dict = {"label": label}

        # ---- Team size ----
        n_reps = self._count_reps()
        if n_reps:
            kwargs["n_reps"] = n_reps

        # ---- Pipeline seeding ----
        n_accounts = self._count_accounts()
        if n_accounts:
            kwargs["n_seed_accounts"] = n_accounts

        # ---- Conversion rates → theta overrides ----
        rates = self._compute_conversion_rates()
        self._fit_stats["conversion_rates"] = rates

        if rates.get("lead_to_opp") is not None:
            kwargs["base_prob_lead_conversion"] = rates["lead_to_opp"]

        # Map empirical win rate → base_prob_close via a simple linear
        # adjustment relative to the theta default (0.15).
        if rates.get("opp_win_rate") is not None:
            win_rate = rates["opp_win_rate"]
            # Scale: if org wins 30%, that's 2× the theta default of 15%.
            kwargs["base_prob_close"] = float(np.clip(win_rate, 0.01, 0.60))

        # Lost rate → base_prob_lost
        if rates.get("opp_lost_rate") is not None:
            # Lost rate per opp is much lower than win rate since it's a daily hazard.
            # Empirical lost_rate (fraction of opps that close lost) → daily hazard.
            # Rough approximation: divide by expected cycle length in days.
            cycle = self._fit_stats.get("avg_cycle_days", 60)
            daily_hazard = rates["opp_lost_rate"] / max(cycle, 1)
            kwargs["base_prob_lost"] = float(np.clip(daily_hazard, 0.001, 0.10))

        # ---- Stage advancement rates → prospecting / qualification / etc. ----
        stage_rates = self._compute_stage_advancement_rates()
        self._fit_stats["stage_advancement_rates"] = stage_rates

        for stage_key, config_key in [
            ("Prospecting",   "base_prob_prospecting"),
            ("Qualification", "base_prob_qualification"),
            ("Proposal",      "base_prob_proposal"),
            ("Negotiation",   "base_prob_negotiation"),
        ]:
            rate = stage_rates.get(stage_key)
            if rate is not None:
                # Convert "fraction of opps that advance from this stage" to a
                # daily probability given avg time spent in stage.
                avg_days = self._fit_stats.get(f"avg_days_{stage_key}", 20)
                daily = rate / max(avg_days, 1)
                kwargs[config_key] = float(np.clip(daily, 0.001, 0.30))

        # ---- Cycle time → stagnation / inactivity tuning ----
        avg_cycle = self._compute_avg_cycle_days()
        if avg_cycle:
            self._fit_stats["avg_cycle_days"] = avg_cycle
            # Longer cycles → lower inactivity penalty (deals are meant to be slow)
            # Baseline theta uses 0.010; scale inversely with cycle vs. a 45-day norm.
            kwargs["inactivity_alpha"] = float(np.clip(0.010 * (45 / max(avg_cycle, 10)), 0.002, 0.025))
            kwargs["stagnation_alpha"] = float(np.clip(0.008 * (45 / max(avg_cycle, 10)), 0.001, 0.020))

        # ---- Deal size metadata (stored for reference, not passed to theta yet) ----
        deal_stats = self._compute_deal_stats()
        self._fit_stats["deal_stats"] = deal_stats

        cfg = OrgConfig(**kwargs)
        cfg = replace(cfg, notes=f"Calibrated from export. Fit stats: {self._fit_stats}")
        self._fitted_config = cfg
        return cfg

    def validation_report(self) -> str:
        """
        Human-readable summary of what was fitted and what fell back to defaults.
        Call after calibrate().
        """
        if self._fitted_config is None:
            return "Call calibrate() first."

        cfg = self._fitted_config
        lines = [
            "=" * 60,
            f"Calibration Report — {cfg.label!r}",
            "=" * 60,
            "",
            f"  Reps fitted       : {cfg.n_reps}",
            f"  Seed accounts     : {cfg.n_seed_accounts}",
            "",
            "  Conversion rates (from export)",
        ]

        cr = self._fit_stats.get("conversion_rates", {})
        for k, v in cr.items():
            tag = f"{v:.3f}" if v is not None else "(not available — using sim default)"
            lines.append(f"    {k:<25} {tag}")

        lines += [
            "",
            "  Theta overrides",
            f"    base_prob_lead_conversion : {cfg.base_prob_lead_conversion}",
            f"    base_prob_prospecting     : {cfg.base_prob_prospecting}",
            f"    base_prob_qualification   : {cfg.base_prob_qualification}",
            f"    base_prob_proposal        : {cfg.base_prob_proposal}",
            f"    base_prob_negotiation     : {cfg.base_prob_negotiation}",
            f"    base_prob_close           : {cfg.base_prob_close}",
            f"    base_prob_lost            : {cfg.base_prob_lost}",
            f"    inactivity_alpha          : {cfg.inactivity_alpha}",
            f"    stagnation_alpha          : {cfg.stagnation_alpha}",
            "",
        ]

        deal = self._fit_stats.get("deal_stats", {})
        if deal:
            lines += [
                "  Deal size stats (informational, not yet wired to theta)",
                f"    median ACV     : {deal.get('median_amount', 'n/a')}",
                f"    mean ACV       : {deal.get('mean_amount', 'n/a')}",
                f"    p90 ACV        : {deal.get('p90_amount', 'n/a')}",
                "",
            ]

        avg_cycle = self._fit_stats.get("avg_cycle_days")
        if avg_cycle:
            lines.append(f"  Avg cycle days : {avg_cycle:.1f}")

        lines.append("=" * 60)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal: normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df.columns = [c.lower().strip() for c in df.columns]
        return df

    def _normalise_opps(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self._normalise(df)
        if df.empty:
            return df

        # Normalise stage column
        if "stage" not in df.columns and "stagename" in df.columns:
            df = df.rename(columns={"stagename": "stage"})
        if "stage" in df.columns:
            df["stage_sim"] = df["stage"].str.lower().map(self.STAGE_MAP)

        # Parse dates
        for col in ("close_date", "closedate", "created_date", "createddate"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        # Normalise amount
        for col in ("amount", "amount__c"):
            if col in df.columns:
                df["amount"] = pd.to_numeric(df[col], errors="coerce")
                break

        return df

    # ------------------------------------------------------------------
    # Internal: metrics
    # ------------------------------------------------------------------

    def _count_reps(self) -> Optional[int]:
        if not self._users.empty and "id" in self._users.columns:
            return max(1, len(self._users))
        if not self._opps.empty:
            for col in ("ownerid", "owner_id"):
                if col in self._opps.columns:
                    return max(1, self._opps[col].nunique())
        return None

    def _count_accounts(self) -> Optional[int]:
        if not self._accounts.empty and "id" in self._accounts.columns:
            return len(self._accounts)
        if not self._opps.empty and "accountid" in self._opps.columns:
            return self._opps["accountid"].nunique()
        return None

    def _compute_conversion_rates(self) -> dict:
        rates: dict = {
            "lead_to_opp":   None,
            "opp_win_rate":  None,
            "opp_lost_rate": None,
        }

        # Lead → Opp rate
        if not self._leads.empty:
            total_leads = len(self._leads)
            converted_col = next((c for c in ("isconverted", "is_converted") if c in self._leads.columns), None)
            if converted_col:
                n_converted = self._leads[converted_col].sum()
                rates["lead_to_opp"] = _safe_rate(n_converted, total_leads)

        # Opp win / lost rates
        if not self._opps.empty and "stage_sim" in self._opps.columns:
            closed = self._opps[self._opps["stage_sim"].isin(["Closed Won", "Closed Lost"])]
            total_closed = len(closed)
            if total_closed > 0:
                rates["opp_win_rate"]  = _safe_rate((closed["stage_sim"] == "Closed Won").sum(), total_closed)
                rates["opp_lost_rate"] = _safe_rate((closed["stage_sim"] == "Closed Lost").sum(), total_closed)

        return rates

    def _compute_stage_advancement_rates(self) -> dict:
        """
        For each stage, compute the fraction of opps that advanced to the next.
        Also populates self._fit_stats["avg_days_{Stage}"] as a side effect.
        """
        rates: dict = {}
        if self._opps.empty or "stage_sim" not in self._opps.columns:
            return rates

        STAGE_ORDER = ["Prospecting", "Qualification", "Proposal", "Negotiation"]
        for i, stage in enumerate(STAGE_ORDER[:-1]):
            next_stage = STAGE_ORDER[i + 1]
            at_stage   = self._opps[self._opps["stage_sim"] == stage]
            advanced   = self._opps[self._opps["stage_sim"] == next_stage]
            rates[stage] = _safe_rate(len(advanced), max(len(at_stage), 1))

        return rates

    def _compute_avg_cycle_days(self) -> Optional[float]:
        if self._opps.empty:
            return None

        date_col   = next((c for c in ("close_date", "closedate") if c in self._opps.columns), None)
        create_col = next((c for c in ("created_date", "createddate") if c in self._opps.columns), None)
        if not date_col or not create_col:
            return None

        df = self._opps[[date_col, create_col]].dropna()
        if df.empty:
            return None
        cycle = (df[date_col] - df[create_col]).dt.days
        cycle = cycle[cycle > 0]
        return float(cycle.median()) if len(cycle) > 0 else None

    def _compute_deal_stats(self) -> dict:
        if self._opps.empty or "amount" not in self._opps.columns:
            return {}
        amounts = self._opps["amount"].dropna()
        amounts = amounts[amounts > 0]
        if amounts.empty:
            return {}
        return {
            "median_amount": round(float(amounts.median()), 2),
            "mean_amount":   round(float(amounts.mean()), 2),
            "p90_amount":    round(float(amounts.quantile(0.90)), 2),
            "n_deals":       len(amounts),
        }


# ---------------------------------------------------------------------------
# 2. ExperimentRunner
# ---------------------------------------------------------------------------

class ExperimentRunner:
    """
    Run hypothesis experiments against the sim using any OrgConfig.

    The runner is intentionally decoupled from the calibrator — you can
    pass a hand-crafted OrgConfig, a fitted one, or a mix.

    Parameters
    ----------
    base_config     : OrgConfig used as the control condition.
    state_factory   : Callable[[OrgConfig], dict] that returns a fresh
                      {"reps": ..., "leads": ..., "accounts": ...,
                       "opportunities": ...} dict for each run.
                      Use build_state_from_config() for convenience.
    sim_fn          : The run_simulation function from simulate.py.
    micro_policy    : The micro policy callable (simulate_rep_thinking).
    n_iterations    : Monte Carlo iterations per experiment condition.
    show_progress   : Whether to show tqdm progress bars.

    Example
    -------
        from sf_majick.sim.simulate import run_simulation
        from sf_majick.sim.micro_policy import simulate_rep_thinking
        from sf_majick.sim.org_calibrator import ExperimentRunner, build_state_from_config

        runner = ExperimentRunner(
            base_config   = cfg,
            state_factory = build_state_from_config,
            sim_fn        = run_simulation,
            micro_policy  = simulate_rep_thinking,
            n_iterations  = 200,
        )

        results = runner.compare({
            "baseline":          {},
            "hire_2_closers":    {"n_reps": 10, "rep_slots": [RepSlot("Closer", 2, start_day=0)]},
            "faster_ramp":       {"base_prob_prospecting": 0.12},
            "fix_lost_rate":     {"base_prob_lost": 0.020},
        })

        print(results.groupby("experiment")[["won_rate","revenue_per_run"]].describe())
    """

    def __init__(
        self,
        base_config: OrgConfig,
        state_factory: Callable[[OrgConfig], dict],
        sim_fn: Callable,
        micro_policy: Callable,
        n_iterations: int = 200,
        show_progress: bool = True,
    ) -> None:
        self.base_config    = base_config
        self.state_factory  = state_factory
        self.sim_fn         = sim_fn
        self.micro_policy   = micro_policy
        self.n_iterations   = n_iterations
        self.show_progress  = show_progress

    # ------------------------------------------------------------------
    # Single experiment
    # ------------------------------------------------------------------

    def run(
        self,
        perturbation: dict | None = None,
        label: str = "experiment",
    ) -> pd.DataFrame:
        """
        Run n_iterations of the sim under a single perturbation.

        Parameters
        ----------
        perturbation : dict of OrgConfig field overrides, or None for baseline.
        label        : string tag added to all rows in the output DataFrame.

        Returns
        -------
        DataFrame with one row per simulation run.
        Columns: label, run_id, n_won, n_lost, revenue_per_run, won_rate,
                 avg_rep_earnings, total_micro_actions, total_macro_events.
        """
        from .logger import EventLogger

        cfg = self.base_config.with_changes(**(perturbation or {}), label=label)

        records = []
        iterator = range(self.n_iterations)
        if self.show_progress:
            iterator = tqdm(iterator, desc=label, leave=False)

        for i in iterator:
            seed = cfg.seed_offset + i
            random.seed(seed)
            np.random.seed(seed)

            state  = self.state_factory(cfg)
            logger = EventLogger()

            self.sim_fn(
                reps=state["reps"],
                leads=state.get("leads", []),
                opportunities=state.get("opportunities", []),
                accounts=state.get("accounts", []),
                days=cfg.days,
                logger=logger,
                micro_policy=self.micro_policy,
                apply_decay=cfg.apply_decay,
            )

            opps = state.get("opportunities", [])
            n_won    = sum(1 for o in opps if getattr(o, "stage", "") == "Closed Won")
            n_closed = sum(1 for o in opps if "Closed" in getattr(o, "stage", ""))
            revenue  = sum(getattr(o, "revenue", 0) for o in opps if getattr(o, "stage", "") == "Closed Won")
            rep_earnings = [r.earnings for r in state["reps"]]

            records.append({
                "label":             label,
                "run_id":            i,
                "n_won":             n_won,
                "n_lost":            n_closed - n_won,
                "n_closed":          n_closed,
                "revenue_per_run":   revenue,
                "won_rate":          _safe_rate(n_won, max(n_closed, 1)),
                "avg_rep_earnings":  float(np.mean(rep_earnings)) if rep_earnings else 0.0,
                "total_micro_actions": len(logger.micro_events),
                "total_macro_events":  len(logger.macro_events),
            })

        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # Multi-experiment comparison
    # ------------------------------------------------------------------

    def compare(
        self,
        experiments: dict[str, dict | None],
    ) -> pd.DataFrame:
        """
        Run multiple experiment conditions and stack the results.

        Parameters
        ----------
        experiments : dict mapping {label: perturbation_dict}.
                      Use an empty dict {} or None for the control condition.

        Returns
        -------
        Stacked DataFrame with all runs across all conditions.

        Example
        -------
            results = runner.compare({
                "baseline":       {},
                "hire_2_reps":    {"n_reps": 12},
                "cut_lost_rate":  {"base_prob_lost": 0.018},
            })
            # Aggregate by experiment label
            summary = (
                results
                .groupby("label")[["won_rate", "revenue_per_run", "avg_rep_earnings"]]
                .agg(["mean", "std", "median"])
            )
        """
        frames = []
        for label, perturbation in experiments.items():
            df = self.run(perturbation=perturbation or {}, label=label)
            frames.append(df)

        return pd.concat(frames, ignore_index=True)

    # ------------------------------------------------------------------
    # Convenience: sensitivity scan
    # ------------------------------------------------------------------

    def sensitivity_scan(
        self,
        param: str,
        values: list,
        base_label: str | None = None,
    ) -> pd.DataFrame:
        """
        Sweep a single OrgConfig parameter across a list of values.

        Useful for finding breakpoints: "at what win rate does hiring
        a new rep pay off?"

        Parameters
        ----------
        param  : OrgConfig field name (e.g. "base_prob_close").
        values : list of values to sweep.

        Example
        -------
            df = runner.sensitivity_scan(
                "base_prob_close",
                [0.10, 0.15, 0.20, 0.25, 0.30],
            )
        """
        experiments = {
            f"{base_label or param}={v}": {param: v}
            for v in values
        }
        return self.compare(experiments)


# ---------------------------------------------------------------------------
# 3. State factory
# ---------------------------------------------------------------------------

def build_state_from_config(cfg: OrgConfig) -> dict:
    """
    Build a fresh sim state (reps, leads, accounts, opportunities) from
    an OrgConfig.  This is the default state_factory for ExperimentRunner.

    The function applies cfg.apply_to_theta() so the probability fields
    on the config are live in the sim for this run.

    Returns
    -------
    dict with keys: reps, leads, accounts, opportunities
    """
    # Import here to avoid circular imports at module load time.
    from .reps import SalesRep, ARCHETYPES, random_personality, ARCHETYPE_ROTATION
    from .entities import Account
    from .utils import generate_random_leads
    from .theta import theta as BASE_THETA

    # ----------------------------------------------------------------
    # Apply config overrides to theta (module-level mutation for this run).
    # This is intentionally done per-call so each sim run gets the right
    # theta without global state leaking between experiments.
    # ----------------------------------------------------------------
    live_theta = cfg.apply_to_theta(BASE_THETA)
    # Patch the module's theta dict in-place for the duration of this call.
    # (The sim reads theta directly from the module, not via a parameter.)
    import sf_majick.sim.theta as theta_module
    _saved_theta = dict(theta_module.theta)
    theta_module.theta.update(live_theta)

    try:
        # ------------------------------------------------------------
        # Build reps
        # ------------------------------------------------------------
        reps = []

        if cfg.rep_slots:
            # Detailed slot-based team
            for slot in cfg.rep_slots:
                for _ in range(slot.count):
                    rep = SalesRep(
                        id=f"rep_{len(reps)}",
                        archetype_name=slot.archetype_name,
                        comp_rate=slot.comp_rate,
                    )
                    reps.append(rep)
        else:
            # Simple n_reps with archetype_weights distribution
            archetype_names = list(cfg.archetype_weights.keys())
            weights = list(cfg.archetype_weights.values())
            for i in range(cfg.n_reps):
                chosen = random.choices(archetype_names, weights=weights, k=1)[0]
                rep = SalesRep(
                    id=f"rep_{i}",
                    archetype_name=chosen,
                    comp_rate=cfg.default_comp_rate,
                )
                reps.append(rep)

        # ------------------------------------------------------------
        # Build accounts
        # ------------------------------------------------------------
        personality_names  = list(cfg.account_personality_weights.keys())
        personality_weights = list(cfg.account_personality_weights.values())

        accounts = []
        for i in range(cfg.n_seed_accounts):
            assigned_rep = reps[i % len(reps)]

            if cfg.random_account_revenues or i >= len(cfg.account_revenues):
                revenue = float(np.random.lognormal(mean=15, sigma=1))
            else:
                revenue = cfg.account_revenues[i]

            acc = Account(
                id=f"acc_{i}",
                name=f"Account_{i}",
                rep_id=assigned_rep.id,
                annual_revenue=revenue,
            )
            # Override auto-assigned personality with config weights
            archetype = random.choices(personality_names, weights=personality_weights, k=1)[0]
            acc.assign_archetype(archetype)
            accounts.append(acc)

        # ------------------------------------------------------------
        # Seed opportunities (one per account)
        # ------------------------------------------------------------
        opportunities = [acc.create_opportunity() for acc in accounts]

        # ------------------------------------------------------------
        # Seed leads
        # ------------------------------------------------------------
        leads = generate_random_leads(n=cfg.n_seed_leads)

        return {
            "reps":          reps,
            "leads":         leads,
            "accounts":      accounts,
            "opportunities": opportunities,
        }

    finally:
        # Restore theta so subsequent calls / imports are unaffected.
        theta_module.theta.clear()
        theta_module.theta.update(_saved_theta)

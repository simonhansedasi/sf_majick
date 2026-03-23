"""
org_config.py
=============
Defines OrgConfig — the single kwargs dictionary that drives the sim
when you want to parameterise it against a real org.

This module is intentionally free of any sim dependencies so it can be
imported anywhere (calibration scripts, notebooks, experiment runners)
without pulling in the whole sim graph.

Usage
-----
Standalone sim (no fitting):
    from sf_majick.sim.org_config import OrgConfig
    # Use defaults, or override any field you want to explore
    cfg = OrgConfig(n_reps=8, days=60)

After fitting an org:
    cfg = OrgCalibrator(sf_export).calibrate()

Feeding into the sim:
    reps, leads, accounts, opportunities = build_state_from_config(cfg)
    run_simulation(reps=reps, leads=leads, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace, asdict
from typing import Optional
import json


# ---------------------------------------------------------------------------
# Rep team composition
# ---------------------------------------------------------------------------

@dataclass
class RepSlot:
    """
    Describes one rep (or one cohort of identically-configured reps).

    archetype_name : one of "Closer", "Nurturer", "Grinder", "Scattered",
                     or None for random.
    count          : how many reps of this type.
    start_day      : day they join the sim (0 = present from the start).
    comp_rate      : commission multiplier (1.0 = standard plan).
    """
    archetype_name: Optional[str] = None
    count: int = 1
    start_day: int = 0
    comp_rate: float = 1.0


# ---------------------------------------------------------------------------
# OrgConfig
# ---------------------------------------------------------------------------

@dataclass
class OrgConfig:
    """
    Full parameterisation of one sim run.

    All fields have defaults so the sim works out-of-the-box with zero
    fitting. Override only the fields that matter for a given experiment.

    Sections
    --------
    - Team composition
    - Pipeline seeding
    - Conversion / probability levers  (map onto theta)
    - Economics
    - Simulation control
    """

    # ------------------------------------------------------------------
    # Team composition
    # ------------------------------------------------------------------
    # Simple shorthand: total reps, all random archetypes, present day 0.
    n_reps: int = 8

    # Detailed override: list of RepSlots.  If non-empty, n_reps is ignored.
    rep_slots: list[RepSlot] = field(default_factory=list)

    # Archetype distribution weights when assigning random archetypes.
    # Keys must match ARCHETYPES in reps.py.
    archetype_weights: dict[str, float] = field(default_factory=lambda: {
        "Closer":    0.30,
        "Nurturer":  0.25,
        "Grinder":   0.30,
        "Scattered": 0.15,
    })

    # ------------------------------------------------------------------
    # Pipeline seeding (initial state)
    # ------------------------------------------------------------------
    # Number of synthetic leads injected at day 0.
    n_seed_leads: int = 4

    # Number of synthetic accounts to create (each seeds one opportunity).
    n_seed_accounts: int = 10

    # If True, accounts are created with random revenues drawn from a
    # lognormal.  If False, you must supply account_revenues list.
    random_account_revenues: bool = True
    account_revenues: list[float] = field(default_factory=list)

    # Account personality archetype distribution weights.
    account_personality_weights: dict[str, float] = field(default_factory=lambda: {
        "Analytical Skeptic":           0.30,
        "Urgent Pragmatist":            0.40,
        "Price-Sensitive Opportunist":  0.20,
        "Easy-Going Follower":          0.10,
    })

    # ------------------------------------------------------------------
    # Conversion / probability levers
    # These values are injected into theta at sim startup via apply_to_theta().
    # Set to None to leave the theta default untouched.
    # ------------------------------------------------------------------

    # Lead → Opp conversion base probability
    base_prob_lead_conversion: Optional[float] = None   # theta default: 0.25

    # Stage advancement base probabilities
    base_prob_prospecting:   Optional[float] = None     # theta default: 0.08
    base_prob_qualification: Optional[float] = None     # theta default: 0.04
    base_prob_proposal:      Optional[float] = None     # theta default: 0.02
    base_prob_negotiation:   Optional[float] = None     # theta default: 0.01

    # Close / lost probabilities
    base_prob_close: Optional[float] = None             # theta default: 0.15
    base_prob_lost:  Optional[float] = None             # theta default: 0.035

    # Sentiment sensitivity
    sentiment_beta_opportunity: Optional[float] = None  # theta default: 0.2
    sentiment_beta_lead:        Optional[float] = None  # theta default: 0.1

    # Momentum / friction sensitivity
    momentum_beta_opportunity: Optional[float] = None   # theta default: 0.75
    friction_beta_opportunity: Optional[float] = None   # theta default: 0.5

    # Inactivity / stagnation decay (pipeline death hazard)
    inactivity_alpha: Optional[float] = None            # theta default: 0.010
    stagnation_alpha: Optional[float] = None            # theta default: 0.008

    # ------------------------------------------------------------------
    # Economics
    # ------------------------------------------------------------------
    # Commission tier overrides.  None = use CommissionPlan defaults.
    # Format: list of (threshold, rate) tuples, same as CommissionPlan.tiers.
    commission_tiers: Optional[list[tuple[float, float]]] = None

    # Default comp_rate for reps not individually specified.
    default_comp_rate: float = 1.0

    # ------------------------------------------------------------------
    # Simulation control
    # ------------------------------------------------------------------
    days: int = 90
    n_runs: int = 100
    seed_offset: int = 0

    # Whether to apply passive sentiment decay on untouched days.
    apply_decay: bool = True

    # ------------------------------------------------------------------
    # Metadata (for traceability)
    # ------------------------------------------------------------------
    # Label shown in experiment comparisons.
    label: str = "baseline"

    # Optional free-form notes (e.g. "fitted from Q3 Salesforce export").
    notes: str = ""

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def with_changes(self, **kwargs) -> "OrgConfig":
        """
        Return a new OrgConfig with the given fields overridden.
        Original config is not mutated.

        Example
        -------
        new_cfg = cfg.with_changes(n_reps=12, label="hire_4_reps")
        """
        return replace(self, **kwargs)

    def apply_to_theta(self, theta: dict) -> dict:
        """
        Overlay the OrgConfig's probability fields onto a theta dict.
        Returns a *copy* of theta — the original is not mutated.

        Call this at the start of each sim run when using a fitted config.

        Example
        -------
        from sf_majick.sim.theta import theta as BASE_THETA
        live_theta = cfg.apply_to_theta(BASE_THETA)
        """
        t = dict(theta)  # shallow copy is fine; values are scalars

        _overlay = {
            "base_prob_lead_conversion": self.base_prob_lead_conversion,
            "base_prob_prospecting":     self.base_prob_prospecting,
            "base_prob_qualification":   self.base_prob_qualification,
            "base_prob_proposal":        self.base_prob_proposal,
            "base_prob_negotiation":     self.base_prob_negotiation,
            "base_prob_close":           self.base_prob_close,
            "base_prob_lost":            self.base_prob_lost,
            "sentiment_beta_opportunity":self.sentiment_beta_opportunity,
            "sentiment_beta_lead":       self.sentiment_beta_lead,
            "momentum_beta_opportunity": self.momentum_beta_opportunity,
            "friction_beta_opportunity": self.friction_beta_opportunity,
            "inactivity_alpha":          self.inactivity_alpha,
            "stagnation_alpha":          self.stagnation_alpha,
        }

        for k, v in _overlay.items():
            if v is not None:
                t[k] = v

        return t

    def to_dict(self) -> dict:
        """Serialise to a plain dict (JSON-safe)."""
        d = asdict(self)
        # commission_tiers contains tuples; convert to lists for JSON
        if d.get("commission_tiers"):
            d["commission_tiers"] = [list(t) for t in d["commission_tiers"]]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "OrgConfig":
        """Deserialise from a plain dict (e.g. loaded from JSON)."""
        if d.get("commission_tiers"):
            d["commission_tiers"] = [tuple(t) for t in d["commission_tiers"]]
        if d.get("rep_slots"):
            d["rep_slots"] = [RepSlot(**s) for s in d["rep_slots"]]
        return cls(**d)

    def save(self, path: str) -> None:
        """Persist config to a JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "OrgConfig":
        """Load config from a JSON file."""
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def describe(self) -> str:
        """Human-readable summary for quick inspection."""
        lines = [
            f"OrgConfig: {self.label!r}",
            f"  Team     : {self.n_reps} reps, {self.days} days, {self.n_runs} runs",
            f"  Pipeline : {self.n_seed_leads} seed leads, {self.n_seed_accounts} seed accounts",
        ]
        overrides = {
            k: v for k, v in [
                ("lead_conv",   self.base_prob_lead_conversion),
                ("prospecting", self.base_prob_prospecting),
                ("close",       self.base_prob_close),
                ("lost",        self.base_prob_lost),
                ("inactivity",  self.inactivity_alpha),
            ] if v is not None
        }
        if overrides:
            lines.append(f"  Theta    : {overrides}")
        if self.notes:
            lines.append(f"  Notes    : {self.notes}")
        return "\n".join(lines)

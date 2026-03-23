"""
requirement_config.py
=====================
RequirementConfig holds the action-count thresholds that gate micro actions
and macro stage advancements.  Every integer in your MICRO_ACTIONS requirement
trees and MICRO_REQUIREMENTS_BY_STAGE maps to a named field here.

Design principles
-----------------
- The tree *structure* (AND / OR / sequence / chance nodes) is preserved —
  it encodes good sales theory.
- Only the *counts* are parameterised here.  This is the minimal surface area
  needed to fit to real org data without rebuilding the entire logic graph.
- All fields default to your current hardcoded values, so RequirementConfig()
  with no arguments reproduces the existing sim behaviour exactly.
- build_micro_actions(cfg) and build_stage_requirements(cfg) return freshly
  constructed requirement trees wired to cfg's values.  Call these once at
  sim startup and pass the results wherever MICRO_ACTIONS /
  MICRO_REQUIREMENTS_BY_STAGE are currently imported directly.

Fitting workflow
----------------
    from sf_majick.sim.requirement_miner import RequirementMiner
    miner = RequirementMiner(task_df, event_df, stage_history_df)
    req_cfg = miner.mine(percentile=25)
    print(req_cfg.describe())
    req_cfg.save("data/req_config_acme.json")

Using in the sim
----------------
    from sf_majick.sim.requirement_config import (
        RequirementConfig, build_micro_actions, build_stage_requirements
    )
    req_cfg = RequirementConfig.load("data/req_config_acme.json")
    MICRO_ACTIONS               = build_micro_actions(req_cfg)
    MICRO_REQUIREMENTS_BY_STAGE = build_stage_requirements(req_cfg)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict


# ---------------------------------------------------------------------------
# RequirementConfig
# ---------------------------------------------------------------------------

@dataclass
class RequirementConfig:
    """
    Named count thresholds for every integer in the requirement trees.

    Naming convention
    -----------------
    micro_{action}_{what}   : count threshold gating a micro action
    stage_{from}_{what}     : count threshold for a stage advancement gate
    lead_{what}             : count threshold for lead conversion
    """

    # ------------------------------------------------------------------
    # MICRO ACTION gates
    # ------------------------------------------------------------------

    # research_account: prior email or call count
    micro_research_min_email_or_call: int = 1

    # internal_prep: combined email+call count for the chance path
    micro_internal_min_touches: int = 2

    # solution_design: combined email+call+research for chance path
    micro_solution_min_touches: int = 3

    # stakeholder_alignment: combined call+email+follow_up
    micro_stakeholder_min_touches: int = 4

    # hold_meeting (non-sequence path): combined email+call after research
    micro_meeting_min_touches: int = 3
    # hold_meeting sequence path
    micro_meeting_sequence_emails: int = 2
    micro_meeting_sequence_calls: int = 1
    # hold_meeting cold-call chance path
    micro_meeting_chance_calls: int = 2

    # follow_up (non-sequence path): combined email+call after meeting
    micro_followup_min_touches: int = 3
    # follow_up chance path
    micro_followup_chance_emails: int = 4
    micro_followup_chance_calls: int = 2

    # send_proposal — lightweight path
    micro_proposal_min_meeting_or_followup: int = 1
    micro_proposal_min_deep_action: int = 1         # solution_design / stakeholder / internal_prep
    micro_proposal_min_touches: int = 4             # combined email+call
    # send_proposal — long nurture path
    micro_proposal_nurture_emails: int = 12
    micro_proposal_nurture_calls: int = 10
    micro_proposal_nurture_followups: int = 3
    micro_proposal_nurture_meetings: int = 2
    micro_proposal_nurture_solutions: int = 1

    # ------------------------------------------------------------------
    # MACRO STAGE ADVANCEMENT gates (MICRO_REQUIREMENTS_BY_STAGE)
    # ------------------------------------------------------------------

    # Lead
    stage_lead_min_touches: int = 1
    stage_lead_sequence_emails: int = 1
    stage_lead_sequence_calls: int = 1

    # Lead Qualified
    stage_leadq_min_touches: int = 2
    stage_leadq_sequence_emails: int = 1
    stage_leadq_sequence_calls: int = 1

    # Prospecting → Qualification
    stage_prospecting_min_touches: int = 2
    stage_prospecting_sequence_emails: int = 1
    stage_prospecting_sequence_calls: int = 1

    # Qualification → Proposal
    stage_qualification_min_touches: int = 3
    stage_qualification_sequence_emails: int = 2
    stage_qualification_sequence_calls: int = 1
    stage_qualification_sequence_meetings: int = 1

    # Proposal → Negotiation
    stage_proposal_min_deep: int = 2               # deep actions (follow_up+meeting+internal+solution+stakeholder)
    stage_proposal_sequence_solutions: int = 1
    stage_proposal_sequence_stakeholders: int = 1
    stage_proposal_min_proposal_sent: int = 1

    # Negotiation → Close
    stage_negotiation_min_deep: int = 3
    stage_negotiation_sequence_solutions: int = 1
    stage_negotiation_sequence_internals: int = 1
    stage_negotiation_sequence_followups: int = 1
    stage_negotiation_min_proposal_sent: int = 1

    # ------------------------------------------------------------------
    # LEAD CONVERSION gate (can_convert_lead in macro_actions.py)
    # ------------------------------------------------------------------
    lead_min_emails: int = 1
    lead_min_calls_if_no_meeting: int = 2           # calls needed when no meeting has occurred

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    label: str = "default"
    notes: str = ""
    fitted_percentile: int = 25

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RequirementConfig":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "RequirementConfig":
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def describe(self) -> str:
        c = self
        lines = [
            f"RequirementConfig: {c.label!r}  (fitted at p{c.fitted_percentile})",
            "",
            "  Micro action gates",
            f"    research unlock          email|call >= {c.micro_research_min_email_or_call}",
            f"    internal_prep            touches    >= {c.micro_internal_min_touches}",
            f"    solution_design          touches    >= {c.micro_solution_min_touches}",
            f"    stakeholder_alignment    touches    >= {c.micro_stakeholder_min_touches}",
            f"    hold_meeting             touches    >= {c.micro_meeting_min_touches}",
            f"    hold_meeting  sequence   {c.micro_meeting_sequence_emails}e + {c.micro_meeting_sequence_calls}c",
            f"    follow_up                touches    >= {c.micro_followup_min_touches}",
            f"    send_proposal (light)    touches    >= {c.micro_proposal_min_touches}",
            f"    send_proposal (nurture)  {c.micro_proposal_nurture_emails}e + "
            f"{c.micro_proposal_nurture_calls}c + {c.micro_proposal_nurture_meetings}m",
            "",
            "  Stage advancement gates",
            f"    Lead                     {c.stage_lead_min_touches} touches",
            f"    Lead Qualified           {c.stage_leadq_min_touches} touches",
            f"    Prospecting→Qualification {c.stage_prospecting_min_touches} touches",
            f"    Qualification→Proposal   {c.stage_qualification_min_touches} touches",
            f"    Proposal→Negotiation     {c.stage_proposal_min_deep} deep + proposal sent",
            f"    Negotiation→Close        {c.stage_negotiation_min_deep} deep + proposal sent",
            "",
            "  Lead conversion gate",
            f"    min emails               {c.lead_min_emails}",
            f"    min calls (no meeting)   {c.lead_min_calls_if_no_meeting}",
        ]
        if c.notes:
            lines += ["", f"  Notes: {c.notes}"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tree builders
# These return fresh dicts/objects each call — safe to call per-run.
# ---------------------------------------------------------------------------

def build_micro_actions(cfg: RequirementConfig) -> dict:
    """
    Return a MICRO_ACTIONS dict with requirement trees wired to cfg's counts.
    Drop-in replacement for the static MICRO_ACTIONS in micro_actions.py.

    Usage
    -----
        MICRO_ACTIONS = build_micro_actions(req_cfg)
        # then pass to whatever calls MICRO_ACTIONS directly
    """
    from sf_majick.sim.micro_actions import (
        MicroAction,
        send_email, make_call, hold_meeting, follow_up,
        research_account, internal_prep, send_proposal,
        solution_design, stakeholder_alignment,
    )

    c = cfg

    return {

        "send_email": MicroAction("send_email", 15, send_email, requirements=None),

        "make_call": MicroAction("make_call", 15, make_call, requirements=None),

        "research_account": MicroAction(
            "research_account", 25, research_account,
            requirements={"or": [
                {"chance": 0.60, "req": {}},
                {"send_email": c.micro_research_min_email_or_call},
                {"make_call":  c.micro_research_min_email_or_call},
            ]}
        ),

        "internal_prep": MicroAction(
            "internal_prep", 25, internal_prep,
            requirements={"or": [
                {"hold_meeting": 1},
                {"follow_up": 1},
                {"solution_design": 1},
                {"chance": 0.40, "req": {"min_total": {
                    "actions": ["send_email", "make_call"],
                    "count": c.micro_internal_min_touches,
                }}},
            ]}
        ),

        "solution_design": MicroAction(
            "solution_design", 35, solution_design,
            requirements={"or": [
                {"internal_prep": 1},
                {"hold_meeting": 1},
                {"follow_up": 1},
                {"chance": 0.30, "req": {"min_total": {
                    "actions": ["send_email", "make_call", "research_account"],
                    "count": c.micro_solution_min_touches,
                }}},
            ]}
        ),

        "stakeholder_alignment": MicroAction(
            "stakeholder_alignment", 40, stakeholder_alignment,
            requirements={"or": [
                {"solution_design": 1},
                {"min_total": {
                    "actions": ["make_call", "send_email", "follow_up"],
                    "count": c.micro_stakeholder_min_touches,
                }},
            ]}
        ),

        "hold_meeting": MicroAction(
            "hold_meeting", 40, hold_meeting,
            requirements={"or": [
                {"and": [
                    {"research_account": 1},
                    {"min_total": {
                        "actions": ["send_email", "make_call"],
                        "count": c.micro_meeting_min_touches,
                    }},
                ]},
                {"sequence": [
                    {"send_email": c.micro_meeting_sequence_emails},
                    {"make_call":  c.micro_meeting_sequence_calls},
                ]},
                {"chance": 0.015, "req": {
                    "make_call": c.micro_meeting_chance_calls,
                }},
            ]}
        ),

        "follow_up": MicroAction(
            "follow_up", 30, follow_up,
            requirements={"or": [
                {"and": [
                    {"hold_meeting": 1},
                    {"min_total": {
                        "actions": ["send_email", "make_call"],
                        "count": c.micro_followup_min_touches,
                    }},
                ]},
                {"sequence": [
                    {"hold_meeting":  1},
                    {"internal_prep": 1},
                    {"send_email":    1},
                ]},
                {"chance": 0.012, "req": {"and": [
                    {"send_email": c.micro_followup_chance_emails},
                    {"make_call":  c.micro_followup_chance_calls},
                ]}},
            ]}
        ),

        "send_proposal": MicroAction(
            "send_proposal", 50, send_proposal,
            requirements={"or": [
                # Lightweight path
                {"and": [
                    {"min_total": {
                        "actions": ["hold_meeting", "follow_up"],
                        "count": c.micro_proposal_min_meeting_or_followup,
                    }},
                    {"min_total": {
                        "actions": ["solution_design", "stakeholder_alignment", "internal_prep"],
                        "count": c.micro_proposal_min_deep_action,
                    }},
                    {"min_total": {
                        "actions": ["send_email", "make_call"],
                        "count": c.micro_proposal_min_touches,
                    }},
                ]},
                # Long nurture path
                {"sequence": [
                    {"send_email":       c.micro_proposal_nurture_emails},
                    {"make_call":        c.micro_proposal_nurture_calls},
                    {"follow_up":        c.micro_proposal_nurture_followups},
                    {"hold_meeting":     c.micro_proposal_nurture_meetings},
                    {"solution_design":  c.micro_proposal_nurture_solutions},
                ]},
            ]}
        ),
    }


def build_stage_requirements(cfg: RequirementConfig) -> dict:
    """
    Return a MICRO_REQUIREMENTS_BY_STAGE dict wired to cfg's counts.
    Drop-in replacement for the static dict in utils.py.

    Usage
    -----
        MICRO_REQUIREMENTS_BY_STAGE = build_stage_requirements(req_cfg)
    """
    c = cfg

    return {

        "Lead": {"and": [
            {"min_total": {
                "actions": ["research_account", "send_email", "make_call"],
                "count": c.stage_lead_min_touches,
            }},
            {"or": [
                {"research_account": 1},
                {"sequence": [
                    {"send_email": c.stage_lead_sequence_emails},
                    {"make_call":  c.stage_lead_sequence_calls},
                ]},
                {"sequence": [
                    {"make_call":  c.stage_lead_sequence_calls},
                    {"send_email": c.stage_lead_sequence_emails},
                ]},
                {"chance": 0.40, "req": {"send_email": c.stage_lead_sequence_emails}},
            ]},
        ]},

        "Lead Qualified": {"and": [
            {"min_total": {
                "actions": ["send_email", "make_call", "hold_meeting", "research_account"],
                "count": c.stage_leadq_min_touches,
            }},
            {"or": [
                {"hold_meeting": 1},
                {"sequence": [
                    {"send_email": c.stage_leadq_sequence_emails},
                    {"make_call":  c.stage_leadq_sequence_calls},
                ]},
                {"sequence": [
                    {"make_call":  c.stage_leadq_sequence_calls},
                    {"send_email": c.stage_leadq_sequence_emails},
                ]},
                {"chance": 0.35, "req": {"min_total": {
                    "actions": ["send_email", "make_call"],
                    "count": c.stage_leadq_min_touches,
                }}},
            ]},
        ]},

        "Prospecting": {"and": [
            {"min_total": {
                "actions": ["send_email", "make_call", "research_account"],
                "count": c.stage_prospecting_min_touches,
            }},
            {"or": [
                {"sequence": [
                    {"send_email": c.stage_prospecting_sequence_emails},
                    {"make_call":  c.stage_prospecting_sequence_calls},
                ]},
                {"sequence": [
                    {"research_account": 1},
                    {"send_email": c.stage_prospecting_sequence_emails},
                ]},
                {"chance": 0.35, "req": {
                    "send_email": c.stage_prospecting_sequence_emails + 1,
                }},
            ]},
        ]},

        "Qualification": {"and": [
            {"min_total": {
                "actions": ["send_email", "make_call", "research_account", "hold_meeting"],
                "count": c.stage_qualification_min_touches,
            }},
            {"or": [
                {"sequence": [
                    {"send_email":   c.stage_qualification_sequence_emails},
                    {"make_call":    c.stage_qualification_sequence_calls},
                    {"hold_meeting": c.stage_qualification_sequence_meetings},
                ]},
                {"sequence": [
                    {"research_account": 1},
                    {"hold_meeting":     c.stage_qualification_sequence_meetings},
                ]},
                {"sequence": [
                    {"make_call":  c.stage_qualification_sequence_calls + 1},
                    {"send_email": c.stage_qualification_sequence_emails},
                ]},
                {"chance": 0.25, "req": {
                    "hold_meeting": c.stage_qualification_sequence_meetings,
                }},
            ]},
        ]},

        "Proposal": {"and": [
            {"min_total": {
                "actions": ["follow_up", "hold_meeting", "internal_prep",
                            "solution_design", "stakeholder_alignment"],
                "count": c.stage_proposal_min_deep,
            }},
            {"or": [
                {"sequence": [
                    {"solution_design":       c.stage_proposal_sequence_solutions},
                    {"stakeholder_alignment": c.stage_proposal_sequence_stakeholders},
                ]},
                {"sequence": [
                    {"hold_meeting":    1},
                    {"follow_up":       1},
                    {"solution_design": c.stage_proposal_sequence_solutions},
                ]},
                {"chance": 0.2, "req": {"internal_prep": 1}},
            ]},
            {"send_proposal": c.stage_proposal_min_proposal_sent},
        ]},

        "Negotiation": {"and": [
            {"min_total": {
                "actions": ["research_account", "internal_prep", "follow_up",
                            "hold_meeting", "solution_design", "stakeholder_alignment"],
                "count": c.stage_negotiation_min_deep,
            }},
            {"or": [
                {"sequence": [
                    {"solution_design": c.stage_negotiation_sequence_solutions},
                    {"internal_prep":   c.stage_negotiation_sequence_internals},
                    {"follow_up":       c.stage_negotiation_sequence_followups},
                ]},
                {"sequence": [
                    {"hold_meeting":          1},
                    {"stakeholder_alignment": 1},
                ]},
                {"sequence": [
                    {"internal_prep": c.stage_negotiation_sequence_internals},
                    {"make_call":     1},
                    {"send_email":    1},
                ]},
                {"chance": 0.25, "req": {
                    "follow_up": c.stage_negotiation_sequence_followups,
                }},
            ]},
            {"send_proposal": c.stage_negotiation_min_proposal_sent},
        ]},
    }

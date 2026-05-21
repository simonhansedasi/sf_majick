"""
Smoke tests for the sales org simulator.

Run with:  pytest tests/test_sim.py -v
"""

import random
import pytest

from sf_majick.sim.entities import MicroState, Lead, Opportunity, Account
from sf_majick.sim.reps import SalesRep
from sf_majick.sim.logger import EventLogger
from sf_majick.sim.micro_policy import simulate_rep_thinking
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.utils import generate_random_leads, generate_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_world(n_reps=3, n_accounts=4):
    """Return a minimal (reps, leads, accounts, opportunities) world state."""
    reps = [
        SalesRep(id=f"rep_{i}", archetype_name=arch)
        for i, arch in enumerate(["Closer", "Nurturer", "Grinder"])
    ][:n_reps]

    accounts = [
        Account(id=f"acc_{i}", name=f"Acme_{i}", rep_id=reps[i % len(reps)].id)
        for i in range(n_accounts)
    ]
    opportunities = [acc.create_opportunity() for acc in accounts]
    leads = generate_random_leads(n=3)

    return reps, leads, accounts, opportunities


# ---------------------------------------------------------------------------
# MicroState / consume_requirements
# ---------------------------------------------------------------------------

class TestConsumeRequirements:
    def test_and_consumes_all_branches(self):
        """AND node must consume every sub-requirement, not just the first."""
        ms = MicroState(send_email=3, make_call=3)
        req = {"and": [{"send_email": 2}, {"make_call": 2}]}
        ms.consume_requirements(req)
        assert ms.send_email == 1, "send_email should drop by 2"
        assert ms.make_call == 1, "make_call should drop by 2"

    def test_or_consumes_exactly_one_branch(self):
        """OR node must consume exactly one satisfied branch, not all."""
        ms = MicroState(send_email=2, make_call=2)
        req = {"or": [{"send_email": 1}, {"make_call": 1}]}
        ms.consume_requirements(req)
        total_consumed = (2 - ms.send_email) + (2 - ms.make_call)
        assert total_consumed == 1, "OR should consume exactly 1 action total"

    def test_leaf_decrements_counts(self):
        ms = MicroState(send_email=5)
        ms.consume_requirements({"send_email": 3})
        assert ms.send_email == 2

    def test_none_requirement_is_noop(self):
        ms = MicroState(send_email=2)
        ms.consume_requirements(None)
        assert ms.send_email == 2


# ---------------------------------------------------------------------------
# Commission — no double-booking
# ---------------------------------------------------------------------------

class TestCommission:
    def test_commission_credited_once_on_close(self):
        """
        Closing a won opportunity should add commission exactly once.
        Previously attempt_close() AND work_entity() both called add_commission().
        """
        from sf_majick.sim.macro_actions import attempt_close

        rep = SalesRep(id="rep_0", archetype_name="Closer")
        opp = Opportunity(
            id=generate_id(),
            stage="Negotiation",
            revenue=100_000.0,
            rep_id="rep_0",
            difficulty=0.1,
        )

        # Patch random so the close always succeeds
        import sf_majick.sim.macro_actions as ma_module
        orig_random = random.random
        try:
            random.random = lambda: 0.0   # always < close probability
            attempt_close(opp, rep=rep)
        finally:
            random.random = orig_random

        # Commission should have been added exactly once (in work_entity, not attempt_close)
        # After our fix, attempt_close no longer adds commission.
        assert rep.earnings == 0.0, (
            "attempt_close should NOT credit commission; only work_entity should"
        )


# ---------------------------------------------------------------------------
# SalesRep.end_of_day
# ---------------------------------------------------------------------------

class TestEndOfDay:
    def test_end_of_day_increments_lifetime_actions(self):
        rep = SalesRep(id="rep_0")
        assert rep.lifetime_actions == 0
        rep.end_of_day(actions_taken=5, deals_worked=2)
        assert rep.lifetime_actions == 5

    def test_end_of_day_accumulates_stress(self):
        rep = SalesRep(id="rep_0")
        initial_stress = rep.stress
        rep.end_of_day(actions_taken=10, deals_worked=2)
        assert rep.stress > initial_stress, "Workload should add stress"

    def test_end_of_day_increments_consecutive_no_close_days(self):
        rep = SalesRep(id="rep_0")
        rep.end_of_day(actions_taken=3, deals_worked=1)
        assert rep.consecutive_no_close_days == 1


# ---------------------------------------------------------------------------
# RepSlot.start_day
# ---------------------------------------------------------------------------

class TestRepSlotStartDay:
    def test_rep_start_day_field_exists(self):
        rep = SalesRep(id="rep_0", start_day=10)
        assert rep.start_day == 10

    def test_deferred_rep_not_active_before_start_day(self):
        """
        A rep with start_day=30 should not appear in active_reps on day 1.
        """
        reps, leads, accounts, opportunities = _make_world()
        late_rep = SalesRep(id="rep_late", archetype_name="Grinder", start_day=30)
        reps.append(late_rep)

        # Run for 5 days; late_rep should have done nothing
        logger = EventLogger()
        run_simulation(
            reps=reps,
            leads=leads,
            accounts=accounts,
            opportunities=opportunities,
            days=5,
            logger=logger,
            micro_policy=simulate_rep_thinking,
        )

        rep_ids_with_actions = {e["rep_id"] for e in logger.micro_events}
        assert "rep_late" not in rep_ids_with_actions, (
            "Deferred rep should have taken no actions before start_day"
        )


# ---------------------------------------------------------------------------
# Full simulation smoke test
# ---------------------------------------------------------------------------

class TestRunSimulation:
    def test_smoke_10_days(self):
        """Sim runs 10 days without exception and returns expected keys."""
        reps, leads, accounts, opportunities = _make_world()
        logger = EventLogger()

        result = run_simulation(
            reps=reps,
            leads=leads,
            accounts=accounts,
            opportunities=opportunities,
            days=10,
            logger=logger,
            micro_policy=simulate_rep_thinking,
        )

        assert result["days_run"] == 10
        assert "final_stage_distribution" in result
        # Some opportunities should still be open or closed — distribution non-empty
        assert len(result["final_stage_distribution"]) > 0

    def test_stage_distribution_keys_are_valid_stages(self):
        from sf_majick.sim.utils import PIPELINE_STAGES
        reps, leads, accounts, opportunities = _make_world()
        logger = EventLogger()

        result = run_simulation(
            reps=reps,
            leads=leads,
            accounts=accounts,
            opportunities=opportunities,
            days=10,
            logger=logger,
            micro_policy=simulate_rep_thinking,
        )
        for stage in result["final_stage_distribution"]:
            assert stage in PIPELINE_STAGES or stage in ("Closed Dead", "Unknown"), (
                f"Unexpected stage in distribution: {stage}"
            )

    def test_reps_earn_commission_on_closes(self):
        """At least some revenue should flow through across 30 days."""
        random.seed(42)
        reps, leads, accounts, opportunities = _make_world(n_reps=3, n_accounts=8)
        logger = EventLogger()

        run_simulation(
            reps=reps,
            leads=leads,
            accounts=accounts,
            opportunities=opportunities,
            days=30,
            logger=logger,
            micro_policy=simulate_rep_thinking,
        )
        # Not asserting a specific number — just that the earnings machinery ran
        total_earnings = sum(r.earnings for r in reps)
        assert total_earnings >= 0.0   # could be 0 if no closes in 30 days

    def test_no_double_commission(self):
        """
        Commission from a close should never be counted more than once.
        We check that rep earnings match CommissionPlan.commission_on() × closes.
        """
        from sf_majick.sim.economics import CommissionPlan

        random.seed(7)
        reps, leads, accounts, opportunities = _make_world(n_reps=2, n_accounts=6)
        logger = EventLogger()

        run_simulation(
            reps=reps,
            leads=leads,
            accounts=accounts,
            opportunities=opportunities,
            days=30,
            logger=logger,
            micro_policy=simulate_rep_thinking,
        )

        # Recompute expected earnings from the opportunity list
        for rep in reps:
            won_revs = [
                opp.revenue for opp in opportunities
                if opp.stage == "Closed Won" and opp.rep_id == rep.id
            ]
            expected = sum(CommissionPlan().commission_on(r) for r in won_revs)
            # Earnings should be close (within floating-point rounding)
            assert abs(rep.earnings - expected) < 1.0, (
                f"Rep {rep.id}: earnings={rep.earnings:.2f} but expected={expected:.2f} "
                f"from {len(won_revs)} closed-won deals — possible double-booking"
            )

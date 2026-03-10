from typing import List, Dict, Callable
import random
import numpy as np
import copy

from .entities import Opportunity, Lead, generate_id, Account
from .reps import SalesRep
from .logger import EventLogger
from .micro_actions import MICRO_ACTIONS
from .macro_actions import decrement_cooldowns 
from .utils import generate_random_leads, softmax
from .utility_engine import choose_targets_with_strategy, strategy_weighted_utility, expected_commission
# from .economics import CommissionPlan
# from .theta import theta
from .sentiment import apply_sentiment
from tqdm import tqdm

# ---------------------------------------------------------------------
# Simulation Engine
# ---------------------------------------------------------------------
def run_simulation(
    reps: List[SalesRep],
    leads: List[Lead],
    accounts: List[Account],
    opportunities: List[Opportunity],
    days: int,
    logger: EventLogger,
    micro_policy: Callable[[SalesRep, object], List[str]],
    apply_decay: bool = True,
) -> Dict:
    
    # ---------------------------------------------------------------------
    # Day 0: Initial World State Logging
    # ---------------------------------------------------------------------
    for lead in leads:
        logger.log_macro(
            day=0,
            rep_id=lead.rep_id,
            entity_id=lead.id,
            macro_name="Lead Created",
            advanced=True,
            old_stage=None,
            new_stage=getattr(lead, "stage", "Lead"),
            probability=None,
        )
        

    for opp in opportunities:
        logger.log_macro(
            day=0,
            rep_id=opp.rep_id,
            entity_id=opp.id,
            macro_name="Base Opportunity Created",
            advanced=True,
            old_stage=None,
            new_stage=opp.stage,
            probability=None,
        )
    for day in tqdm(range(1, days + 1)):
        # -----------------------------
        # Daily Reset Phase
        # -----------------------------
        # print(day)
        decrement_cooldowns(opportunities)
        for rep in reps:
            rep.reset_day()
        for entity in leads + opportunities:

            entity.reset_daily_flags()
        # -----------------------------
        # Daily Opportunity Spawn
        # -----------------------------
        for account in accounts:
            account.days_since_last_opportunity += 1
            if random.random() < account.effective_buying_propensity():
                if (
                    account.days_since_last_opportunity > account.opportunity_cooldown
                    and random.random() < account.buying_propensity
                ):
                    new_op = account.create_opportunity()
                    opportunities.append(new_op)

                    account.days_since_last_opportunity = 0
                    account.opportunity_cooldown = random.randint(30, 45)
                    
                    logger.log_macro(
                        day=day,
                        rep_id=account.rep_id,
                        entity_id=new_op.id,
                        macro_name="Random Buy Opportunity",
                        advanced=True,
                        old_stage=None,
                        new_stage='Prospecting',
                        probability=None,
                    )
                    
        # -----------------------------
        # Weekly Lead Generation
        # -----------------------------
        if day % 30 == 1:
            new_leads = generate_random_leads(n=random.randint(1,4))
            leads.extend(new_leads)
            for lead in new_leads:
                logger.log_macro(
                    day=day,
                    rep_id="system",
                    entity_id=lead.id,
                    macro_name="New Lead",
                    advanced=True,
                    old_stage=None,
                    new_stage=None,
                    probability=None,
                )

        # -----------------------------
        # Assign unclaimed entities to reps
        # -----------------------------
        for entity in leads + opportunities:
            if entity.is_closed or getattr(entity, 'rep_id', None) is not None:
                continue

            # Compute strategy utilities for all reps
            utilities = [strategy_weighted_utility(entity, r.strategy) for r in reps]
            total = sum(utilities)
            chosen_rep = random.choice(reps) if total == 0 else random.choices(
                reps, weights=[u / total for u in utilities], k=1
            )[0]

            entity.rep_id = chosen_rep.id
                                    
        # -----------------------------
        # Each rep works their entities
        # -----------------------------
        
        for rep in reps:
            # print()
            # print(rep.id)
            rep.reset_day()
            owned_entities = [e for e in opportunities + leads if e.rep_id == rep.id and not e.is_closed]
                
                
            while rep.attention_remaining > 20:
                # Filter by allowed actions via strategy
                targets_with_actions = choose_targets_with_strategy(
                    entities=owned_entities,
                    rep_id=rep.id,
                    strategy=rep.strategy
                )
                actionable_entities = [e for e, allowed in targets_with_actions if allowed]

                if not actionable_entities:
                    # Option 1: spawn leads
                    new_leads = generate_random_leads(n=random.randint(1, 2))
                    leads.extend(new_leads)
                    owned_entities.extend(new_leads)
                    for lead in new_leads:
                        logger.log_macro(
                            day=day,
                            rep_id=rep.id,
                            entity_id=lead.id,
                            macro_name="New Lead",
                            advanced=True,
                            old_stage=None,
                            new_stage=None,
                            probability=None,
                        )
                    continue

                
                chosen_entity = pick_entity_for_rep(rep, actionable_entities)
                
                if chosen_entity is None:
                    new_leads = generate_random_leads(n=random.randint(1,2))
                    leads.extend(new_leads)
                    for lead in new_leads:
                        actionable_entities.append(lead)
                        logger.log_macro(
                            day=day,
                            rep_id=rep.id,
                            entity_id=lead.id,
                            macro_name="New Lead",
                            advanced=True,
                            old_stage=None,
                            new_stage=None,
                            probability=None,
                        )
                    # print('leads spawned')

                    # Regenerate targets_with_actions using the full, updated list
                    targets_with_actions = choose_targets_with_strategy(
                        entities=actionable_entities,
                        rep_id=rep.id,
                        strategy=rep.strategy
                    )

                    # Now pick a chosen entity from the updated actionable_entities
                    chosen_entity = pick_entity_for_rep(rep, actionable_entities)
                    
                # print(chosen_entity.id)
                allowed_actions = [a for e, a in targets_with_actions if e == chosen_entity][0]
                chosen_actions = [micro_policy(rep, chosen_entity)]
                
                
                
                telemetry = rep.work_entity(chosen_entity, micro_actions=chosen_actions, accounts=accounts, opportunities = opportunities)

                    
                    
                for m in telemetry['micro_results']:
                    logger.log_micro(
                        day=day,
                        rep_id=rep.id,
                        entity_id=chosen_entity.id,
                        action=m['action'],
                        cost=MICRO_ACTIONS[m['action']].cost,
                        success=m['success'],
                        attention_remaining=m.get('remaining_attention', rep.attention_remaining),
                        sentiment_delta=m.get('sentiment_delta'),
                        sentiment_total=m.get('sentiment_total'),
                    )
                    
                    
                for macro in telemetry["macro_result"]:
                    if (
                        macro.get("old_stage")
                        and macro.get("old_stage") != getattr(chosen_entity, "stage", None)
                    ):

                        result = macro.get('result')
                        if isinstance(result, dict):
                            spawned_account = result['account']

                            spawned_oppo = result['opportunity']

                            if spawned_account == None:
                                continue

                            logger.log_macro(
                                rep_id=spawned_account.rep_id,
                                entity_id=None,
                                macro_name='Spawn Account',
                                old_stage='Lead',
                                new_stage=macro.get("new_stage"),
                                probability=macro.get("probability"),
                                day = day,
                                advanced = macro.get('advanced'),
                            )

                            logger.log_macro(
                                rep_id=spawned_oppo.rep_id,
                                entity_id=spawned_oppo.id,
                                macro_name='Spawn Opportunity',
                                old_stage='None',
                                new_stage=macro.get("new_stage"),
                                probability=macro.get("probability"),
                                day = day,
                                advanced = macro.get('advanced'),

                            )


                        logger.log_macro(
                            rep_id=rep.id,
                            entity_id=getattr(chosen_entity, "id", None),
                            macro_name=macro.get("macro_name"),
                            old_stage=macro.get("old_stage"),
                            new_stage=macro.get("new_stage"),
                            probability=macro.get("probability"),
                            day = day,
                            advanced = macro.get('advanced')
                        )

                    
                if telemetry['micro_results'][0]['success'] == False:

                    break
                    
                    
                    
                    
                    
            for entity in owned_entities:
                if entity.is_closed:
                    continue
                    
                entity.increment_day()

                if entity.days_since_touch > 0:
                    entity.sentiment *= 0.92
                    # Apply passive decay via sentiment
                    rep_for_sentiment = getattr(entity, "rep_id", None)
                    delta = apply_sentiment("no_touch", rep_for_sentiment, entity, decay_days = 1)   
                    
                    
                death_prob = compute_pipeline_death(entity)
                death_prob = min(death_prob, 0.35)
                if random.random() < death_prob:
                    logger.log_macro(
                        rep_id = rep.id,
                        entity_id = entity.id,
                        macro_name = 'Decay / Lost',
                        old_stage = entity.stage,
                        new_stage = 'Closed Dead',
                        probability = death_prob,
                        day = day,
                        advanced = True
                        
                    )
                    entity.stage = "Closed Dead"

                    
                    
                # -----------------------------
    # Final Summary
    # -----------------------------
    return {
        'days_run': days,
        'final_stage_distribution': _stage_distribution(opportunities),
        'total_accounts': len(accounts),
        'logger_summary': logger.summary(),
    }

def pick_entity_for_rep(rep, entities):

    open_entities = [e for e in entities if not e.is_closed]

    if not open_entities:
        # print("NO OPEN ENTITIES")
        return None

    scores = np.array([
        strategy_weighted_utility(e, rep.strategy)
        for e in open_entities
    ])
    scores = scores - np.max(scores)
    scores = np.tanh(scores / 1e6)

    # if np.any(np.isnan(scores)):
        # print("NAN SCORES DETECTED")
        # print(scores)

    # if np.any(np.isinf(scores)):
        # print("INF SCORES DETECTED")
        # print(scores)

    if np.std(scores) < 1e-8:
        scores += np.random.normal(0, 1e-4, size=len(scores))

    probs = softmax(scores, temperature=0.5)

    # if np.any(np.isnan(probs)):
        # print("SOFTMAX BROKE")
        # print(scores)

    probs = softmax(scores, temperature=1.5)
    # print('probs', probs)
    return np.random.choice(open_entities, p=probs)

    


def _stage_distribution(opportunities: list) -> dict:
    """
    Count the number of opportunities in each stage.
    Returns a dict: {stage_name: count}
    """
    distribution = {}
    for opp in opportunities:
        stage = getattr(opp, "stage", "Unknown")
        distribution[stage] = distribution.get(stage, 0) + 1
    return distribution


def compute_pipeline_death(entity):
    if entity.is_closed:
        return 0
    base = 0.0001  # lower base

    # inactivity
    inactivity = min(entity.days_since_touch * 0.000025, 0.10)  # half original

    # fatigue (too many touches)
    touches = sum(
        entity.micro_state.get(a, 0)
        for a in ["email","call","meeting","follow_up"]
    )
    fatigue = max(0, touches - 10) * 0.000125  # half original

    # sentiment
    sentiment_penalty = max(0, -entity.sentiment) * 0.00125  # half original

    # stage aging
    age_penalty = min(entity.days_in_stage * 0.002, 0.01250)  # lower slope

    return base + inactivity + fatigue + sentiment_penalty + age_penalty
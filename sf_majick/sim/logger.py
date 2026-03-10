from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from collections import Counter

@dataclass
class EventLogger:
    """
    Central event logger for simulation.

    Logs:
      - Micro actions (emails, calls, meetings, proposals, etc.)
      - Macro actions (lead conversion, opportunity closure, stage advancement)
      - Opportunity-level states
    """

    micro_events: List[Dict[str, Any]] = field(default_factory=list)
    macro_events: List[Dict[str, Any]] = field(default_factory=list)
    opportunity_events: List[Dict[str, Any]] = field(default_factory=list)

    # -------------------------
    # Micro Logging
    # -------------------------
    def log_micro(
        self,
        day: int,
        rep_id: str,
        entity_id: str,
        action: str,
        cost: int = 1,
        success: bool = True,
        attention_remaining: Optional[int] = None,
        sentiment_delta: float = 0.0,
        sentiment_total: float = 0.0
    ):
        """Log a single micro action."""
        self.micro_events.append({
            'day': day,
            'rep_id': rep_id,
            'entity_id': entity_id,
            'action': action,
            'cost': cost,
            'success': success,
            'attention_remaining': attention_remaining,
            'sentiment_delta': sentiment_delta,
            'sentiment_total': sentiment_total
        })

    def log_micro_from_entity(self, day: int, rep, entity, action_name: str, cost: int = 1, success: bool = True):
        """Helper to log micro directly from entity sentiment."""
        self.log_micro(
            day=day,
            rep_id=getattr(rep, "id", None),
            entity_id=entity.id,
            action=action_name,
            cost=cost,
            success=success,
            attention_remaining=getattr(entity, "attention", None),
            sentiment_delta=getattr(entity, "last_sentiment_delta", 0.0),
            sentiment_total=getattr(entity, "sentiment", 0.0)
        )

    # -------------------------
    # Macro Logging
    # -------------------------
    def log_macro(
        self,
        day: int,
        rep_id: str,
        entity_id: str,
        macro_name: str,
        advanced: bool,
        old_stage: Optional[str] = None,
        new_stage: Optional[str] = None,
        probability: Optional[float] = None
    ):
        self.macro_events.append({
            'day': day,
            'rep_id': rep_id,
            'entity_id': entity_id,
            'macro_name': macro_name,
            'advanced': advanced,
            'old_stage': old_stage,
            'new_stage': new_stage,
            'probability': probability
        })

    # -------------------------
    # Opportunity-Level Logging
    # -------------------------
    def log_opportunity_state(self, run_id: str, opportunity: Any, full_sequence: bool = True):
        """
        Log opportunity micro-state at key points.
        Actions must be a list of dicts with keys 'rep_id', 'action', 'day'.
        """
        actions = getattr(opportunity, 'actions', [])
        total_actions = len(actions)
        reps = list({a['rep_id'] for a in actions})
        counter = Counter([a['action'] for a in actions])

        first_proposal_day = next((a['day'] for a in actions if a['action'] in ['send_proposal','proposal']), None)
        created_day = getattr(opportunity, 'created_day', 0)
        time_to_first_proposal = first_proposal_day - created_day if first_proposal_day else None
        cycle_length = actions[-1]['day'] - created_day + 1 if actions else 0

        log_row = {
            'run_id': run_id,
            'opportunity_id': opportunity.id,
            'current_stage': getattr(opportunity, 'stage', None),
            'total_actions': total_actions,
            'rep_interactions': reps,
            'emails_frac': counter.get('send_email', 0) / total_actions if total_actions else 0,
            'calls_frac': counter.get('make_call', 0) / total_actions if total_actions else 0,
            'proposals_frac': counter.get('send_proposal', 0) / total_actions if total_actions else 0,
            'time_to_first_proposal': time_to_first_proposal,
            'cycle_length': cycle_length,
            'revenue': getattr(opportunity, 'revenue', 0)
        }

        if full_sequence:
            log_row['action_sequence'] = actions

        self.opportunity_events.append(log_row)

    # -------------------------
    # Utilities
    # -------------------------
    def clear(self):
        """Reset all logs."""
        self.micro_events.clear()
        self.macro_events.clear()
        self.opportunity_events.clear()

    def summary(self) -> Dict[str, int]:
        """Quick aggregate counts."""
        return {
            'total_micro_events': len(self.micro_events),
            'total_macro_events': len(self.macro_events),
            'total_opportunity_events': len(self.opportunity_events),
            'total_advancements': sum(1 for e in self.macro_events if e['advanced'])
        }
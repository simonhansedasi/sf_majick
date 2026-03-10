from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class CommissionPlan:
    """
    Tiered commission system.
    Commission = tier_rate × revenue × rep_comp_rate
    """
    tiers: List[Tuple[float, float]] = field(default_factory=lambda: [
        (1_000_000, 0.05),       # first 10k at 4%
        (10_000_000, 0.08),       # next 40k at 6%
        (50_000_000, 0.12),      # next 100k at 8%
        (float('inf'), 0.18)  # remainder at 12%
    ])

    @staticmethod
    def commission_on(revenue: float, rep_comp_rate: float = 1) -> float:
        """
        Calculate commission based on tiers and rep's comp rate.
        """
        remaining = revenue
        total_commission = 0.0
        lower_bound = 0.0

        for threshold, rate in CommissionPlan().tiers:
            # Determine the chunk of revenue in this tier
            chunk = min(remaining, threshold - lower_bound)
            total_commission += chunk * rate
            remaining -= chunk
            lower_bound = threshold
            if remaining <= 0:
                break

        # Scale by rep's comp rate
        return total_commission * rep_comp_rate

"""Budget fit used to adjust the recommendation score."""

from app.schemas.recommendations import Budget, Candidate

#: A price this far outside the budget (relative to the limit) gets a fit of 0.
MAX_RELATIVE_DISTANCE = 0.5


def budget_fit(budget: Budget | None, candidate: Candidate) -> float | None:
    """Return 1.0 inside the budget, decreasing linearly to 0.0 outside it.

    Returns ``None`` when it cannot be compared: no budget, no limits, no price or a
    different currency (prices are never converted).
    """
    if budget is None or candidate.price is None or (budget.min is None and budget.max is None):
        return None
    if candidate.currency != budget.currency:
        return None

    price = candidate.price
    if budget.max is not None and price > budget.max:
        distance = (price - budget.max) / budget.max if budget.max > 0 else float("inf")
    elif budget.min is not None and price < budget.min:
        distance = (budget.min - price) / budget.min
    else:
        return 1.0
    return max(0.0, 1.0 - distance / MAX_RELATIVE_DISTANCE)

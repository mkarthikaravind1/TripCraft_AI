"""
Smart Budget Optimiser — deterministic budget arithmetic.

Every amount is handled as an integer number of minor units ("cents") so the
results are exact and the category totals always add up to the grand total.
static/planner/js/budget.js implements the *same* algorithm so the dashboard
can update instantly in the browser; the server result remains authoritative.

Rounding rule (used by both implementations): percentages are integers and
``apply_percent`` rounds half up, which for non-negative integers is
``(amount * percent + 50) // 100``.
"""

from decimal import ROUND_HALF_UP, Decimal

CATEGORY_ORDER = ["transport", "accommodation", "food", "activities", "misc", "contingency"]
CATEGORY_LABELS = {
    "transport": "Transportation",
    "accommodation": "Accommodation",
    "food": "Food",
    "activities": "Activities",
    "misc": "Miscellaneous",
    "contingency": "Contingency buffer",
}


def to_cents(value):
    """Convert a Decimal/number/string amount to integer minor units."""
    if value is None:
        return None
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_cents(cents):
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))


def apply_percent(amount, percent):
    """Integer percentage of an integer amount, rounded half up."""
    return (amount * percent + 50) // 100


def divide_round(amount, divisor):
    """Integer division rounded half up (divisor > 0)."""
    return (amount + divisor // 2) // divisor


def build_inputs(trip, days=None, expenses=None):
    """Serialise a Trip into the plain-data structure the calculator uses.

    The same structure is embedded in the dashboard as JSON for budget.js.
    """
    if days is None:
        days = trip.days.prefetch_related("activities").all()
    if expenses is None:
        expenses = trip.expenses.all()

    day_inputs = []
    for day in days:
        day_inputs.append(
            {
                "id": day.id,
                "day_number": day.day_number,
                "meal_cents_pp": sum(to_cents(m.get("cost_per_person", 0)) for m in day.meals),
                "activities": [
                    {
                        "id": a.id,
                        "cost_cents_pp": to_cents(a.cost_per_person),
                        "removed": a.is_removed,
                    }
                    for a in day.activities.all()
                ],
            }
        )

    expense_inputs = {
        key: {"estimate_cents": 0, "user_cents": None} for key in ("transport", "accommodation", "misc")
    }
    for expense in expenses:
        expense_inputs[expense.category] = {
            "estimate_cents": to_cents(expense.estimated_amount),
            "user_cents": to_cents(expense.user_amount),
        }

    return {
        "budget_cents": to_cents(trip.budget),
        "travellers": trip.travellers,
        "meal_percent": trip.meal_percent,
        "stay_percent": trip.stay_percent,
        "contingency_percent": trip.contingency_percent,
        "days": day_inputs,
        "expenses": expense_inputs,
    }


def compute(inputs):
    """Calculate the full budget breakdown from ``build_inputs`` data."""
    travellers = max(int(inputs["travellers"]), 1)
    days = inputs["days"]
    num_days = max(len(days), 1)
    expenses = inputs["expenses"]

    def expense_amount(key, percent=100):
        item = expenses[key]
        if item["user_cents"] is not None:
            return item["user_cents"]  # the traveller's own figure is used as-is
        return apply_percent(item["estimate_cents"], percent)

    daily = []
    for day in days:
        activity_cents = travellers * sum(
            a["cost_cents_pp"] for a in day["activities"] if not a["removed"]
        )
        food_cents = apply_percent(day["meal_cents_pp"] * travellers, inputs["meal_percent"])
        daily.append(
            {"day_number": day["day_number"], "activities": activity_cents, "food": food_cents}
        )

    categories = {
        "transport": expense_amount("transport"),
        "accommodation": expense_amount("accommodation", inputs["stay_percent"]),
        "food": sum(d["food"] for d in daily),
        "activities": sum(d["activities"] for d in daily),
        "misc": expense_amount("misc"),
    }
    subtotal = sum(categories.values())
    categories["contingency"] = apply_percent(subtotal, inputs["contingency_percent"])
    total = subtotal + categories["contingency"]

    # Trip-wide costs are spread evenly across days; any remainder goes to the
    # last day so that the daily totals add up exactly to the grand total.
    shared = (
        categories["transport"]
        + categories["accommodation"]
        + categories["misc"]
        + categories["contingency"]
    )
    per_day_shared = shared // num_days
    for index, day in enumerate(daily):
        day["shared"] = per_day_shared + (shared - per_day_shared * num_days if index == len(daily) - 1 else 0)
        day["total"] = day["activities"] + day["food"] + day["shared"]

    budget = inputs["budget_cents"]
    utilisation_tenths = divide_round(total * 1000, budget) if budget > 0 else 0
    return {
        "categories": categories,
        "total": total,
        "budget": budget,
        "remaining": budget - total,
        "over_budget": total > budget,
        "utilisation": utilisation_tenths / 10,
        "per_traveller": divide_round(total, travellers),
        "per_day": divide_round(total, num_days),
        "daily": daily,
    }


def baseline_inputs(inputs):
    """The originally generated plan: every activity, standard styles, no overrides."""
    return {
        **inputs,
        "meal_percent": 100,
        "stay_percent": 100,
        "days": [
            {**day, "activities": [{**a, "removed": False} for a in day["activities"]]}
            for day in inputs["days"]
        ],
        "expenses": {
            key: {**value, "user_cents": None} for key, value in inputs["expenses"].items()
        },
    }


def summarise(trip, days=None):
    """Budget result plus savings against the originally generated plan."""
    inputs = build_inputs(trip, days=days)
    result = compute(inputs)
    baseline = compute(baseline_inputs(inputs))
    result["baseline_total"] = baseline["total"]
    result["savings"] = baseline["total"] - result["total"]
    return inputs, result


def recalculate(trip):
    """Recompute and persist the trip total and per-day costs. Returns (inputs, result)."""
    days = list(trip.days.prefetch_related("activities").all())
    inputs, result = summarise(trip, days=days)

    for day, day_result in zip(days, result["daily"]):
        cost = from_cents(day_result["total"])
        if day.estimated_cost != cost:
            day.estimated_cost = cost
            day.save(update_fields=["estimated_cost"])
    trip.estimated_total = from_cents(result["total"])
    trip.save(update_fields=["estimated_total", "updated_at"])
    return inputs, result

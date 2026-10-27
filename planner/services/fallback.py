"""
Transparent local fallback planner.

Used when no Gemini API key is configured or the AI service fails. It builds a
plan from generic templates that follow the traveller's interests, pace and
budget split. It is always labelled as a *sample* — never as AI output — and
it names no specific real-world venues, prices or opening hours.
"""

from decimal import Decimal

# Share of the total budget assigned to each category in a sample plan.
# Together with the default 10% contingency this stays below 100%.
SHARES = {
    "accommodation": Decimal("0.30"),
    "transport": Decimal("0.12"),
    "misc": Decimal("0.05"),
    "food": Decimal("0.22"),
    "activities": Decimal("0.18"),
}
MEAL_SPLIT = [("breakfast", Decimal("0.20")), ("lunch", Decimal("0.35")), ("dinner", Decimal("0.45"))]

# (name, description, category, duration minutes, relative cost weight)
TEMPLATES = {
    "culture": [
        ("Historic centre walking tour", "Wander the oldest streets of {d} and get your bearings among its best-known landmarks.", "culture", 150, 1),
        ("Landmark monument visit", "Spend unhurried time at one of {d}'s signature monuments or places of worship.", "culture", 120, 2),
        ("Local heritage museum", "Learn the story of {d} at a city or regional history museum.", "culture", 120, 2),
    ],
    "food": [
        ("Street-food tasting walk", "Sample local snacks and specialities across a lively food street.", "food", 120, 2),
        ("Cooking class or market tour", "Join a hands-on class or guided market visit to understand regional ingredients.", "food", 180, 3),
        ("Regional speciality dinner", "Seek out a well-reviewed spot serving the dish {d} is known for.", "food", 90, 2),
    ],
    "nature": [
        ("Sunrise viewpoint", "Catch the early light from a popular viewpoint before the crowds arrive.", "nature", 90, 0),
        ("Park or botanical garden stroll", "Slow down with a walk through {d}'s green spaces.", "nature", 120, 1),
        ("Half-day nature excursion", "Head just outside {d} for a lake, coast, forest or hill walk.", "nature", 240, 3),
    ],
    "adventure": [
        ("Guided hike or trek", "A guided outing on a well-used trail near {d}; check difficulty before booking.", "adventure", 240, 3),
        ("Cycling or water-sports session", "Rent a bike or try a water activity, depending on what {d} offers.", "adventure", 150, 2),
    ],
    "art": [
        ("Art museum or gallery", "Browse a major collection or a cluster of independent galleries.", "culture", 150, 2),
        ("Street-art neighbourhood walk", "Explore a creative district known for murals, studios and design shops.", "sightseeing", 120, 0),
        ("Local craft workshop", "Try a short workshop in a traditional craft of the region.", "culture", 120, 3),
    ],
    "shopping": [
        ("Local market browse", "Explore a busy local market for crafts, textiles and everyday goods.", "shopping", 120, 1),
        ("Artisan and souvenir quarter", "Pick up thoughtful souvenirs from small independent makers.", "shopping", 90, 1),
    ],
    "nightlife": [
        ("Evening live-music venue", "Spend the evening at a venue with local live music.", "nightlife", 150, 2),
        ("Night market and city lights", "Stroll a night market or waterfront when {d} lights up.", "nightlife", 120, 1),
    ],
    "relaxation": [
        ("Spa or wellness session", "Book a massage, bathhouse or wellness treatment to recharge.", "relaxation", 120, 3),
        ("Slow café afternoon", "Settle into a neighbourhood café with a book and people-watch.", "relaxation", 90, 1),
        ("Sunset by the water", "Find a riverside, lakeside or seaside spot for sunset.", "relaxation", 90, 0),
    ],
    "photography": [
        ("Golden-hour photo walk", "Photograph {d}'s most characterful streets in soft evening light.", "sightseeing", 120, 0),
        ("Panoramic city viewpoint", "Head up to a tower, hill or rooftop for a panorama of {d}.", "sightseeing", 90, 1),
    ],
    "local": [
        ("Neighbourhood life walk", "Explore a residential district to see everyday life in {d}.", "sightseeing", 120, 0),
        ("Cultural performance", "Watch a traditional music, dance or theatre performance.", "culture", 120, 2),
    ],
}
GENERIC = [
    ("Explore a new neighbourhood", "Pick an area of {d} you have not seen yet and explore on foot.", "sightseeing", 120, 0),
    ("Free time for personal discoveries", "Leave space to revisit a favourite spot or follow a recommendation.", "relaxation", 120, 0),
]

PACE_SLOTS = {
    "relaxed": ["10:00", "15:30"],
    "balanced": ["09:30", "12:00", "16:30"],
    "packed": ["08:30", "11:00", "14:00", "17:30"],
}
PACE_LABEL = {"relaxed": "relaxed", "balanced": "balanced", "packed": "packed"}


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"))


def build_sample_plan(request, reason=""):
    """Return a plan dict in the same shape as ``itinerary.normalise_plan``."""
    budget = Decimal(request.budget)
    travellers = max(request.travellers, 1)
    num_days = request.num_days
    per_person_day = budget / (travellers * num_days)
    activity_pool = per_person_day * SHARES["activities"]
    food_pool = per_person_day * SHARES["food"]
    d = request.destination

    interests = [i for i in request.interests if i in TEMPLATES] or ["culture", "food", "nature"]
    queues = {key: list(TEMPLATES[key]) for key in interests}
    slots = PACE_SLOTS.get(request.pace, PACE_SLOTS["balanced"])

    def next_template(turn):
        for offset in range(len(interests)):
            queue = queues[interests[(turn + offset) % len(interests)]]
            if queue:
                return queue.pop(0)
        return None

    turn = 0
    generic_count = 0
    days = []
    for index in range(num_days):
        picks = []
        for _slot in slots:
            template = next_template(turn)
            turn += 1
            if template is None:
                name, desc, cat, dur, weight = GENERIC[generic_count % len(GENERIC)]
                generic_count += 1
                template = (f"{name} ({generic_count})", desc, cat, dur, weight)
            picks.append(template)

        total_weight = sum(t[4] for t in picks) or 1
        activities = []
        if index == 0:
            activities.append(_travel("08:00" if slots[0] > "09:00" else "07:30", f"Arrive and settle in {d}",
                                      "Check in, drop your bags and pick up a local transport card or SIM if needed."))
        for slot, (name, desc, cat, dur, weight) in zip(slots, picks):
            activities.append(
                {
                    "time_slot": slot,
                    "name": name,
                    "description": desc.format(d=d),
                    "duration_minutes": dur,
                    "location": f"{d} (choose a specific spot locally)",
                    "category": cat,
                    "cost_per_person": _money(activity_pool * weight / total_weight),
                }
            )
        if request.pace != "packed":
            activities.append(_rest("14:30" if request.pace == "relaxed" else "15:00"))
        if index == num_days - 1 and num_days > 1:
            activities.append(_travel("19:30", "Pack and prepare for departure",
                                      "Leave buffer time for check-out and the journey home."))
        activities.sort(key=lambda a: a["time_slot"])

        meals = [
            {
                "meal": meal,
                "suggestion": _meal_text(meal, request.dietary),
                "cost_per_person": _money(food_pool * share),
            }
            for meal, share in MEAL_SPLIT
        ]
        days.append(
            {
                "title": "Arrival and first impressions" if index == 0 else f"Exploring {d}",
                "summary": f"A {PACE_LABEL.get(request.pace, 'balanced')} day built around "
                + ", ".join(p[0].lower() for p in picks) + ".",
                "notes": "Group nearby stops together and use "
                + _transport_text(request.transport) + " between areas.",
                "meals": meals,
                "activities": activities,
            }
        )

    return {
        "overview": (
            f"This sample plan was built by TripCraft's local templates, not by a live AI model"
            f"{' (' + reason + ')' if reason else ''}. It follows your interests, a "
            f"{PACE_LABEL.get(request.pace, 'balanced')} pace and a proportional split of your budget, "
            f"but activities are generic placeholders rather than researched recommendations for {d}."
        ),
        "tips": [
            "Regenerate with live AI when it becomes available for destination-specific suggestions.",
            "All amounts are rough proportional estimates — check real prices before booking.",
        ],
        "days": days,
        "missing_days": 0,
        "estimates": {
            "transport": {"amount": _money(budget * SHARES["transport"]),
                          "note": "Sample allowance for getting there and around (12% of budget)."},
            "accommodation": {"amount": _money(budget * SHARES["accommodation"]),
                              "note": f"Sample allowance for {request.num_nights} night(s) (30% of budget)."},
            "misc": {"amount": _money(budget * SHARES["misc"]),
                     "note": "Sample allowance for SIM cards, tips and small extras (5% of budget)."},
        },
    }


def sample_day(request, index, used_names):
    """A single template day, used to fill days an AI response left out."""
    plan = build_sample_plan(request)
    day = plan["days"][min(index, len(plan["days"]) - 1)]
    day["activities"] = [a for a in day["activities"] if a["name"].casefold() not in used_names]
    if not any(a["category"] not in {"travel", "rest"} for a in day["activities"]):
        day["activities"].append(
            {
                "time_slot": "10:00",
                "name": f"Open day to explore {request.destination}",
                "description": "Unplanned time to follow your own discoveries.",
                "duration_minutes": 240,
                "location": request.destination,
                "category": "sightseeing",
                "cost_per_person": Decimal("0.00"),
            }
        )
    day["title"] = day["title"] + " (sample)"
    return day


def _travel(time_slot, name, description):
    return {"time_slot": time_slot, "name": name, "description": description, "duration_minutes": 60,
            "location": "", "category": "travel", "cost_per_person": Decimal("0.00")}


def _rest(time_slot):
    return {"time_slot": time_slot, "name": "Rest and recharge", "duration_minutes": 60, "location": "",
            "description": "Unscheduled downtime — head back to your stay or linger somewhere comfortable.",
            "category": "rest", "cost_per_person": Decimal("0.00")}


def _meal_text(meal, dietary):
    diet = f" ({dietary.replace('_', ' ')} options)" if dietary else ""
    return {
        "breakfast": f"Simple local breakfast near your stay{diet}",
        "lunch": f"Casual lunch at a busy local eatery{diet}",
        "dinner": f"Sit-down dinner trying a regional dish{diet}",
    }[meal]


def _transport_text(transport):
    return {
        "public": "public transport",
        "walking": "walking or cycling",
        "taxi": "taxis or ride-hailing",
        "car": "your rental car",
    }.get(transport, "whichever transport is most convenient")

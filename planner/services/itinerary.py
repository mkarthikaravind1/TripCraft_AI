"""
Validation and normalisation of itinerary data.

Model output is never trusted directly: ``parse_ai_response`` turns raw text
into a clean, bounded "plan" dictionary, coercing or discarding bad values.
The local fallback produces the same plan structure, so the rest of the app
does not care where a plan came from.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from planner.models import Activity

MAX_RESPONSE_CHARS = 200_000
MAX_ACTIVITIES_PER_DAY = 8
MAX_MEALS_PER_DAY = 4
MAX_TIPS = 5
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
VALID_CATEGORIES = {choice.value for choice in Activity.Category}
VALID_MEALS = {"breakfast", "lunch", "dinner", "snack"}


class ItineraryParseError(ValueError):
    """Raised when model output cannot be turned into a usable itinerary."""


@dataclass
class TripRequest:
    """Validated trip preferences (built from TripForm.cleaned_data)."""

    destination: str
    start_date: date
    end_date: date
    budget: Decimal
    currency: str
    travellers: int
    interests: list = field(default_factory=list)
    pace: str = "balanced"
    transport: str = "mixed"
    origin: str = ""
    dietary: str = ""
    accessibility: str = ""
    notes: str = ""

    @property
    def num_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def num_nights(self):
        return max(self.num_days - 1, 1)

    def day_date(self, index):
        return self.start_date + timedelta(days=index)

    @classmethod
    def from_trip(cls, trip):
        return cls(
            destination=trip.destination,
            start_date=trip.start_date,
            end_date=trip.end_date,
            budget=trip.budget,
            currency=trip.currency,
            travellers=trip.travellers,
            interests=list(trip.interests),
            pace=trip.pace,
            transport=trip.transport,
            origin=trip.origin,
            dietary=trip.dietary,
            accessibility=trip.accessibility,
            notes=trip.notes,
        )


def clean_text(value, max_length):
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    value = " ".join(value.split())  # collapse whitespace / newlines
    if len(value) > max_length:
        value = value[: max_length - 1].rstrip() + "…"
    return value


def clean_money(value, cap):
    """Non-negative Decimal with 2 dp, capped to a sane maximum."""
    if isinstance(value, bool):
        return Decimal("0.00")
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0.00")
    if not amount.is_finite() or amount < 0:
        return Decimal("0.00")
    return min(amount, cap).quantize(Decimal("0.01"))


def clean_int(value, default, low, high):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def clean_time(value):
    match = TIME_RE.match(str(value or "").strip())
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def extract_json(text):
    """Parse JSON, tolerating Markdown code fences around it."""
    if not isinstance(text, str) or not text.strip():
        raise ItineraryParseError("The AI response was empty.")
    if len(text) > MAX_RESPONSE_CHARS:
        raise ItineraryParseError("The AI response was too long.")
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ItineraryParseError("The AI response was not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ItineraryParseError("The AI response had an unexpected shape.")
    return data


def normalise_activity(raw, money_cap):
    if not isinstance(raw, dict):
        return None
    name = clean_text(raw.get("name"), 120)
    if not name:
        return None
    category = str(raw.get("category", "")).strip().lower()
    if category not in VALID_CATEGORIES:
        category = Activity.Category.SIGHTSEEING
    return {
        "time_slot": clean_time(raw.get("time_slot")),
        "name": name,
        "description": clean_text(raw.get("description"), 600),
        "duration_minutes": clean_int(raw.get("duration_minutes"), 60, 5, 720),
        "location": clean_text(raw.get("location"), 120),
        "category": category,
        "cost_per_person": clean_money(raw.get("cost_per_person"), money_cap),
    }


def normalise_meal(raw, money_cap):
    if not isinstance(raw, dict):
        return None
    suggestion = clean_text(raw.get("suggestion"), 200)
    if not suggestion:
        return None
    meal = str(raw.get("meal", "")).strip().lower()
    return {
        "meal": meal if meal in VALID_MEALS else "snack",
        "suggestion": suggestion,
        "cost_per_person": clean_money(raw.get("cost_per_person"), money_cap),
    }


def normalise_plan(data, request):
    """Validate a plan dictionary against the trip request.

    Returns a cleaned plan with exactly ``request.num_days`` days, or raises
    ItineraryParseError if nothing usable is present. Missing days are
    reported in ``plan["missing_days"]`` so the caller can fill them in.
    """
    budget = Decimal(request.budget)
    per_person_cap = (budget / max(request.travellers, 1)).quantize(Decimal("0.01"))

    raw_days = data.get("days")
    if not isinstance(raw_days, list) or not raw_days:
        raise ItineraryParseError("The AI response contained no itinerary days.")

    seen_names = set()
    days = []
    for raw_day in raw_days[: request.num_days]:
        if not isinstance(raw_day, dict):
            continue
        activities = []
        raw_activities = raw_day.get("activities")
        for raw_activity in raw_activities if isinstance(raw_activities, list) else []:
            activity = normalise_activity(raw_activity, per_person_cap)
            if activity is None:
                continue
            key = activity["name"].casefold()
            # Avoid repeating the same named activity across the trip
            # (travel and rest breaks such as "Hotel check-in" may recur).
            if activity["category"] not in {"travel", "rest"}:
                if key in seen_names:
                    continue
                seen_names.add(key)
            activities.append(activity)
            if len(activities) >= MAX_ACTIVITIES_PER_DAY:
                break
        activities.sort(key=lambda a: a["time_slot"] or "99:99")

        # A day consisting only of travel/rest is still "empty" for a visitor.
        if not any(a["category"] not in {"travel", "rest"} for a in activities):
            continue

        meals = []
        raw_meals = raw_day.get("meals")
        for raw_meal in raw_meals if isinstance(raw_meals, list) else []:
            meal = normalise_meal(raw_meal, per_person_cap)
            if meal:
                meals.append(meal)
            if len(meals) >= MAX_MEALS_PER_DAY:
                break

        days.append(
            {
                "title": clean_text(raw_day.get("title"), 120),
                "summary": clean_text(raw_day.get("summary"), 600),
                "notes": clean_text(raw_day.get("notes"), 400),
                "meals": meals,
                "activities": activities,
            }
        )

    if not days:
        raise ItineraryParseError("The AI response contained no usable itinerary days.")

    raw_estimates = data.get("estimates")
    raw_estimates = raw_estimates if isinstance(raw_estimates, dict) else {}

    def estimate(amount_key, note_key, multiplier=1):
        amount = clean_money(raw_estimates.get(amount_key), budget)
        return {
            "amount": min((amount * multiplier).quantize(Decimal("0.01")), budget),
            "note": clean_text(raw_estimates.get(note_key), 200),
        }

    tips_raw = data.get("tips")
    tips = [clean_text(t, 200) for t in tips_raw if clean_text(t, 200)] if isinstance(tips_raw, list) else []

    return {
        "overview": clean_text(data.get("overview"), 800),
        "tips": tips[:MAX_TIPS],
        "days": days,
        "missing_days": request.num_days - len(days),
        "estimates": {
            "transport": estimate("transport_total", "transport_note"),
            "accommodation": estimate(
                "accommodation_per_night", "accommodation_note", multiplier=request.num_nights
            ),
            "misc": estimate("misc_total", "misc_note"),
        },
    }


def parse_ai_response(text, request):
    """Parse raw model text into a validated plan dictionary."""
    return normalise_plan(extract_json(text), request)

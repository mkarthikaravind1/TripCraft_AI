"""
Trip persistence and ownership rules.

Anonymous visitors own the trips whose ids are stored in their session;
signed-in users own trips linked to their account. Nobody else can see them.
"""

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404

from planner.models import Activity, Expense, ItineraryDay, Trip

from . import budget
from .ai import generate_plan
from .fallback import sample_day
from .itinerary import TripRequest

SESSION_KEY = "trip_ids"
MAX_SESSION_TRIPS = 20


def request_from_form(cleaned):
    return TripRequest(
        destination=cleaned["destination"],
        origin=cleaned.get("origin", ""),
        start_date=cleaned["start_date"],
        end_date=cleaned["end_date"],
        budget=cleaned["budget"],
        currency=cleaned["currency"],
        travellers=cleaned["travellers"],
        interests=cleaned["interests"],
        pace=cleaned["pace"],
        transport=cleaned["transport"],
        dietary=cleaned.get("dietary", ""),
        accessibility=cleaned.get("accessibility", ""),
        notes=cleaned.get("notes", ""),
    )


@transaction.atomic
def save_plan(trip, request, result):
    """Replace the trip's itinerary and estimates with a generated plan."""
    plan = result.plan
    trip.days.all().delete()
    trip.expenses.all().delete()

    days = list(plan["days"])
    used = {a["name"].casefold() for day in days for a in day["activities"]}
    while len(days) < request.num_days:  # fill any days the AI left out
        days.append(sample_day(request, len(days), used))

    for index, day in enumerate(days[: request.num_days]):
        day_obj = ItineraryDay.objects.create(
            trip=trip,
            day_number=index + 1,
            date=request.day_date(index),
            title=day["title"] or f"Day {index + 1}",
            summary=day["summary"],
            notes=day["notes"],
            meals=[{**m, "cost_per_person": str(m["cost_per_person"])} for m in day["meals"]],
        )
        Activity.objects.bulk_create(
            Activity(day=day_obj, order=order, **activity)
            for order, activity in enumerate(day["activities"])
        )

    expense_source = Expense.Source.AI if result.source == "ai" else Expense.Source.SAMPLE
    for category, estimate in plan["estimates"].items():
        Expense.objects.create(
            trip=trip,
            category=category,
            description=estimate["note"],
            estimated_amount=estimate["amount"],
            source=expense_source,
        )

    trip.source = result.source
    trip.ai_model = result.model
    trip.fallback_reason = result.fallback_reason
    overview = plan["overview"]
    if plan.get("missing_days"):
        overview += f" ({plan['missing_days']} day(s) were filled in with sample suggestions.)"
    trip.overview = overview
    trip.tips = plan["tips"]
    trip.meal_style = "standard"
    trip.stay_style = "standard"
    trip.save()
    budget.recalculate(trip)
    return trip


def create_trip(cleaned, user=None, provider=None):
    request = request_from_form(cleaned)
    result = generate_plan(request, provider=provider)
    trip = Trip(
        user=user if user and user.is_authenticated else None,
        destination=request.destination,
        origin=request.origin,
        start_date=request.start_date,
        end_date=request.end_date,
        budget=request.budget,
        currency=request.currency,
        travellers=request.travellers,
        interests=request.interests,
        pace=request.pace,
        transport=request.transport,
        dietary=request.dietary,
        accessibility=request.accessibility,
        notes=request.notes,
        source=result.source,
    )
    with transaction.atomic():
        trip.save()
        save_plan(trip, request, result)
    return trip


def regenerate(trip, provider=None):
    request = TripRequest.from_trip(trip)
    result = generate_plan(request, provider=provider)
    return save_plan(trip, request, result)


# --- Ownership --------------------------------------------------------------
def remember_trip(http_request, trip):
    """Let an anonymous visitor reopen trips created in this browser session."""
    ids = [i for i in http_request.session.get(SESSION_KEY, []) if i != str(trip.id)]
    ids.insert(0, str(trip.id))
    http_request.session[SESSION_KEY] = ids[:MAX_SESSION_TRIPS]


def forget_trip(http_request, trip):
    ids = http_request.session.get(SESSION_KEY, [])
    http_request.session[SESSION_KEY] = [i for i in ids if i != str(trip.id)]


def can_access(http_request, trip):
    if trip.user_id is not None:
        return http_request.user.is_authenticated and trip.user_id == http_request.user.id
    return str(trip.id) in http_request.session.get(SESSION_KEY, [])


def get_trip_for(http_request, trip_id):
    """Fetch a trip the current visitor owns, or 404 (never reveal others' trips)."""
    trip = get_object_or_404(Trip, pk=trip_id)
    if not can_access(http_request, trip):
        raise Http404("Trip not found")
    return trip


def session_trips(http_request):
    ids = http_request.session.get(SESSION_KEY, [])
    return Trip.objects.filter(pk__in=ids, user__isnull=True)


def claim_session_trips(http_request, user):
    """After sign-in/registration, attach this browser's anonymous trips to the account."""
    ids = http_request.session.get(SESSION_KEY, [])
    if ids:
        Trip.objects.filter(pk__in=ids, user__isnull=True).update(user=user)

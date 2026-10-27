"""HTML page views: homepage, planning form, dashboard and trip list."""

from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from planner.forms import CURRENCY_SYMBOLS, INTERESTS, TripForm
from planner.services import budget, trips
from planner.services.ai import get_provider
from support.services import ratelimit
from support.views.errors import error_response

INTEREST_LABELS = dict(INTERESTS)


def home(request):
    return render(request, "planner/home.html")


@require_http_methods(["GET", "POST"])
def plan_trip(request):
    if request.method == "POST":
        form = TripForm(request.POST)
        if form.is_valid():
            allowed, _ = ratelimit.hit(request, "generate")
            if not allowed:
                return error_response(request, "429", message="You've generated several itineraries in a short time. "
                                                              "Please wait a few minutes before trying again.")
            trip = trips.create_trip(form.cleaned_data, user=request.user)
            trips.remember_trip(request, trip)
            if trip.is_ai:
                messages.success(request, "Your itinerary is ready.")
            return redirect("planner:trip_detail", trip_id=trip.id)
    else:
        start = timezone.localdate() + timedelta(days=14)
        form = TripForm(initial={"start_date": start, "end_date": start + timedelta(days=3)})
    return render(
        request,
        "planner/plan.html",
        {"form": form, "ai_configured": get_provider().configured, "today": timezone.localdate()},
    )


def trip_detail(request, trip_id):
    trip = trips.get_trip_for(request, trip_id)
    days = list(trip.days.prefetch_related("activities").all())
    expenses = {e.category: e for e in trip.expenses.all()}
    inputs, result = budget.summarise(trip, days=days)

    category_rows = []
    for key in budget.CATEGORY_ORDER:
        if key in expenses:
            source = expenses[key].source_label
        elif key == "contingency":
            source = "Your setting"
        else:
            source = "Sum of itinerary items"
        category_rows.append(
            {"key": key, "label": budget.CATEGORY_LABELS[key], "cents": result["categories"][key], "source": source}
        )

    removed = [a for day in days for a in day.activities.all() if a.is_removed]
    return render(
        request,
        "planner/dashboard.html",
        {
            "trip": trip,
            "days": days,
            "daily": dict(zip([d.id for d in days], result["daily"])),
            "expenses": expenses,
            "result": result,
            "category_rows": category_rows,
            "removed": removed,
            "interest_labels": [INTEREST_LABELS.get(i, i) for i in trip.interests],
            "currency_symbol": CURRENCY_SYMBOLS.get(trip.currency, trip.currency),
            "budget_state": {
                "inputs": inputs,
                "result": result,
                "currency": trip.currency,
                "symbol": CURRENCY_SYMBOLS.get(trip.currency, trip.currency + " "),
                "labels": budget.CATEGORY_LABELS,
                "order": budget.CATEGORY_ORDER,
                "meal_styles": trip.MEAL_STYLES,
                "stay_styles": trip.STAY_STYLES,
                "meal_style": trip.meal_style,
                "stay_style": trip.stay_style,
            },
            "ai_configured": get_provider().configured,
        },
    )


@require_POST
def regenerate_trip(request, trip_id):
    trip = trips.get_trip_for(request, trip_id)
    allowed, _ = ratelimit.hit(request, "generate")
    if not allowed:
        return error_response(request, "429", message="Please wait a few minutes before regenerating again.")
    trips.regenerate(trip)
    if trip.is_ai:
        messages.success(request, "A fresh AI itinerary has been generated.")
    else:
        messages.warning(request, "Live AI is still unavailable, so a new sample itinerary was created.")
    return redirect("planner:trip_detail", trip_id=trip.id)


@require_POST
def delete_trip(request, trip_id):
    trip = trips.get_trip_for(request, trip_id)
    trips.forget_trip(request, trip)
    trip.delete()
    messages.info(request, f"Your trip to {trip.destination} was deleted.")
    return redirect("planner:my_trips")


def my_trips(request):
    if request.user.is_authenticated:
        trip_list = request.user.trips.all()
    else:
        trip_list = trips.session_trips(request)
    return render(request, "planner/my_trips.html", {"trips": trip_list})

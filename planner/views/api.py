"""
JSON endpoints used by the dashboard (via fetch with the CSRF token).

Each change is saved to the database, the budget is recalculated on the
server and the authoritative result is returned to the browser.
"""

import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from planner.forms import BudgetSettingsForm
from planner.models import Activity
from planner.services import budget, trips
from support.services import weather


def _payload(request):
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _budget_response(trip):
    inputs, result = budget.recalculate(trip)
    return JsonResponse({"ok": True, "inputs": inputs, "result": result})


def _bad_request(message):
    return JsonResponse({"ok": False, "error": message}, status=400)


@require_POST
def update_activity(request, trip_id, activity_id):
    trip = trips.get_trip_for(request, trip_id)
    activity = get_object_or_404(Activity, pk=activity_id, day__trip=trip)
    data = _payload(request)
    if data is None:
        return _bad_request("Invalid request.")

    fields = []
    for key, field in (("completed", "is_completed"), ("removed", "is_removed")):
        if key in data:
            if not isinstance(data[key], bool):
                return _bad_request(f"'{key}' must be true or false.")
            setattr(activity, field, data[key])
            fields.append(field)
    if not fields:
        return _bad_request("Nothing to update.")
    activity.save(update_fields=fields)
    return _budget_response(trip)


@require_POST
def remove_activities(request, trip_id):
    """Remove several activities at once (used by the 'trim paid activities' tool)."""
    trip = trips.get_trip_for(request, trip_id)
    data = _payload(request)
    ids = data.get("ids") if data else None
    if not isinstance(ids, list) or not ids or len(ids) > 200 or not all(isinstance(i, int) for i in ids):
        return _bad_request("Provide a list of activity ids.")
    with transaction.atomic():
        Activity.objects.filter(pk__in=ids, day__trip=trip).update(is_removed=True)
    return _budget_response(trip)


@require_POST
def update_budget(request, trip_id):
    trip = trips.get_trip_for(request, trip_id)
    data = _payload(request)
    if data is None:
        return _bad_request("Invalid request.")
    form = BudgetSettingsForm(data)
    if not form.is_valid():
        first_error = next(iter(form.errors.values()))[0]
        return _bad_request(first_error)
    cleaned = form.cleaned_data

    with transaction.atomic():
        trip_fields = []
        if cleaned.get("contingency_percent") is not None:
            trip.contingency_percent = cleaned["contingency_percent"]
            trip_fields.append("contingency_percent")
        for key in ("meal_style", "stay_style"):
            if cleaned.get(key):
                setattr(trip, key, cleaned[key])
                trip_fields.append(key)
        if trip_fields:
            trip.save(update_fields=trip_fields + ["updated_at"])

        for category in ("transport", "misc"):
            expense = trip.expenses.filter(category=category).first()
            if expense is None:
                continue
            if cleaned.get(f"reset_{category}"):
                expense.user_amount = None
                expense.save(update_fields=["user_amount"])
            elif cleaned.get(f"{category}_amount") is not None:
                expense.user_amount = cleaned[f"{category}_amount"]
                expense.save(update_fields=["user_amount"])
    return _budget_response(trip)


@require_GET
def trip_weather(request, trip_id):
    """Forecast for the trip from the Open-Meteo API (loaded asynchronously by the dashboard)."""
    trip = trips.get_trip_for(request, trip_id)
    result = weather.get_forecast(trip.destination, trip.start_date, trip.end_date)
    return JsonResponse({"ok": result.status in {"ok", "partial"}, **result.as_dict()})

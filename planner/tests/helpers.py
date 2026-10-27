import json
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from planner.services.ai import AIUnavailable


def future(days):
    return timezone.localdate() + timedelta(days=days)


def trip_form_data(**overrides):
    start = future(20)
    data = {
        "destination": "Lisbon, Portugal",
        "origin": "",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=2)).isoformat(),
        "budget": "1500",
        "currency": "EUR",
        "travellers": "2",
        "interests": ["culture", "food"],
        "pace": "balanced",
        "transport": "public",
        "dietary": "",
        "accessibility": "",
        "notes": "",
    }
    data.update(overrides)
    return data


def ai_plan_json(num_days=3, day_offset=0):
    """A valid structured response, as Gemini would return it."""
    days = []
    for i in range(num_days):
        n = i + 1 + day_offset
        days.append({
            "day_number": n,
            "title": f"Day {n} highlights",
            "summary": "A balanced day.",
            "notes": "Use the metro between areas.",
            "activities": [
                {"time_slot": "09:30", "name": f"Museum visit {n}", "description": "Art and history.",
                 "duration_minutes": 120, "location": "Belém", "category": "culture", "cost_per_person": 15},
                {"time_slot": "13:00", "name": f"Tram ride {n}", "description": "Scenic route.",
                 "duration_minutes": 60, "location": "Alfama", "category": "sightseeing", "cost_per_person": 3.5},
                {"time_slot": "15:00", "name": "Rest at the hotel", "description": "", "duration_minutes": 60,
                 "location": "", "category": "rest", "cost_per_person": 0},
            ],
            "meals": [
                {"meal": "breakfast", "suggestion": "Pastel de nata", "cost_per_person": 5},
                {"meal": "lunch", "suggestion": "Bifana sandwich", "cost_per_person": 10},
                {"meal": "dinner", "suggestion": "Seafood rice", "cost_per_person": 25},
            ],
        })
    return json.dumps({
        "overview": "Culture and food at a comfortable pace.",
        "tips": ["Buy a Viva Viagem card."],
        "days": days,
        "estimates": {
            "transport_total": 200, "transport_note": "Flights and metro.",
            "accommodation_per_night": 120, "accommodation_note": "Mid-range hotel.",
            "misc_total": 60, "misc_note": "SIM and tips.",
        },
    })


class FakeProvider:
    """Stands in for GeminiProvider so tests never call the real API."""

    model = "fake-model"

    def __init__(self, response=None, error=None, configured=True):
        self.response = response
        self.error = error
        self.configured = configured
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        if self.error:
            raise self.error
        return self.response


def unavailable_provider(reason="the AI service timed out"):
    return FakeProvider(error=AIUnavailable(reason))


D = Decimal

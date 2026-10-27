import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from planner.forms import TripForm
from planner.models import Activity, Trip

from .helpers import FakeProvider, ai_plan_json, future, trip_form_data, unavailable_provider


class FormValidationTests(TestCase):
    def test_valid_form(self):
        self.assertTrue(TripForm(trip_form_data()).is_valid())

    def test_end_before_start_rejected(self):
        form = TripForm(trip_form_data(end_date=future(5).isoformat(), start_date=future(10).isoformat()))
        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)

    def test_past_start_and_too_long_trips_rejected(self):
        self.assertIn("start_date", TripForm(trip_form_data(start_date=future(-3).isoformat())).errors)
        start = future(10)
        form = TripForm(trip_form_data(start_date=start.isoformat(), end_date=(start + timedelta(days=20)).isoformat()))
        self.assertIn("end_date", form.errors)

    def test_invalid_budgets_rejected(self):
        for value in ["0", "-100", "abc", "999999999999"]:
            self.assertIn("budget", TripForm(trip_form_data(budget=value)).errors, value)
        # Valid number but unrealistically low for 2 people x 3 days (min EUR 15 pp/day).
        self.assertIn("budget", TripForm(trip_form_data(budget="40")).errors)

    def test_destination_and_travellers_validated(self):
        self.assertIn("destination", TripForm(trip_form_data(destination="12345")).errors)
        self.assertIn("travellers", TripForm(trip_form_data(travellers="0")).errors)
        self.assertIn("interests", TripForm(trip_form_data(interests=[])).errors)


class PageTests(TestCase):
    def test_home_plan_and_faq_pages_load_with_widget(self):
        for name in ["planner:home", "planner:plan", "support:faq"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, "data-chat")
            self.assertContains(response, 'data-endpoint="/support/chat/"')

    def test_home_explains_product(self):
        response = self.client.get("/")
        self.assertContains(response, "Plan your trip")
        self.assertContains(response, "TripCraft")


class TripFlowTests(TestCase):
    def setUp(self):
        cache.clear()

    def create_trip(self, provider):
        with mock.patch("planner.services.ai.get_provider", return_value=provider):
            response = self.client.post(reverse("planner:plan"), trip_form_data())
        self.assertEqual(response.status_code, 302)
        return Trip.objects.latest("created_at"), response

    def test_ai_trip_is_saved_and_retrieved(self):
        trip, response = self.create_trip(FakeProvider(response=ai_plan_json(3)))
        self.assertEqual(trip.source, "ai")
        self.assertEqual(trip.days.count(), 3)
        self.assertEqual(trip.expenses.count(), 3)
        page = self.client.get(response["Location"])
        self.assertContains(page, "Lisbon, Portugal")
        self.assertContains(page, "AI-generated")
        self.assertGreater(trip.estimated_total, 0)

    def test_ai_failure_shows_tripcraft_001_sample(self):
        trip, response = self.create_trip(unavailable_provider())
        self.assertEqual(trip.source, "sample")
        page = self.client.get(response["Location"])
        self.assertContains(page, "Sample itinerary · not AI-generated")
        self.assertContains(page, "TRIPCRAFT_001")

    def test_activity_changes_persist_and_update_budget(self):
        trip, _ = self.create_trip(FakeProvider(response=ai_plan_json(3)))
        before = trip.estimated_total
        activity = Activity.objects.filter(day__trip=trip, cost_per_person__gt=0).first()
        url = reverse("planner:update_activity", args=[trip.id, activity.id])
        response = self.client.post(url, json.dumps({"removed": True, "completed": True}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        activity.refresh_from_db()
        trip.refresh_from_db()
        self.assertTrue(activity.is_removed and activity.is_completed)
        self.assertLess(trip.estimated_total, before)
        self.assertEqual(response.json()["result"]["total"], int(trip.estimated_total * 100))

    def test_budget_settings_persist(self):
        trip, _ = self.create_trip(FakeProvider(response=ai_plan_json(3)))
        url = reverse("planner:update_budget", args=[trip.id])
        response = self.client.post(url, json.dumps({"meal_style": "street", "transport_amount": "50", "contingency_percent": 0}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        trip.refresh_from_db()
        self.assertEqual(trip.meal_style, "street")
        self.assertEqual(trip.contingency_percent, 0)
        self.assertEqual(response.json()["result"]["categories"]["transport"], 5000)
        self.assertEqual(response.json()["result"]["categories"]["contingency"], 0)

    def test_invalid_json_returns_400(self):
        trip, _ = self.create_trip(FakeProvider(response=ai_plan_json(3)))
        response = self.client.post(reverse("planner:update_budget", args=[trip.id]), "not json",
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_other_visitors_cannot_see_or_modify_trip(self):
        trip, response = self.create_trip(FakeProvider(response=ai_plan_json(3)))
        stranger = self.client_class()
        self.assertEqual(stranger.get(response["Location"]).status_code, 404)
        activity = Activity.objects.filter(day__trip=trip).first()
        resp = stranger.post(reverse("planner:update_activity", args=[trip.id, activity.id]),
                             json.dumps({"removed": True}), content_type="application/json")
        self.assertEqual(resp.status_code, 404)
        activity.refresh_from_db()
        self.assertFalse(activity.is_removed)

    def test_users_cannot_access_each_others_trips(self):
        alice = User.objects.create_user("alice", password="pw-Strong-123")
        User.objects.create_user("bob", password="pw-Strong-123")
        self.client.login(username="alice", password="pw-Strong-123")
        trip, response = self.create_trip(FakeProvider(response=ai_plan_json(3)))
        self.assertEqual(trip.user, alice)
        self.assertContains(self.client.get(reverse("planner:my_trips")), "Lisbon")
        bob = self.client_class()
        bob.login(username="bob", password="pw-Strong-123")
        self.assertEqual(bob.get(response["Location"]).status_code, 404)
        self.assertNotContains(bob.get(reverse("planner:my_trips")), "Lisbon")

    def test_anonymous_trips_attach_on_signup(self):
        trip, _ = self.create_trip(FakeProvider(response=ai_plan_json(3)))
        self.client.post(reverse("signup"), {"username": "carol", "password1": "pw-Strong-123", "password2": "pw-Strong-123"})
        trip.refresh_from_db()
        self.assertEqual(trip.user.username, "carol")

    @override_settings(RATE_LIMITS={"generate": (1, 600), "chat": (20, 60)})
    def test_generation_rate_limited_with_429(self):
        self.create_trip(FakeProvider(response=ai_plan_json(3)))
        with mock.patch("planner.services.ai.get_provider", return_value=FakeProvider(response=ai_plan_json(3))):
            response = self.client.post(reverse("planner:plan"), trip_form_data())
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too Many Requests", status_code=429)


class WeatherEndpointTests(TestCase):
    def test_weather_endpoint_returns_fallback_on_timeout(self):
        import requests

        with mock.patch("planner.services.ai.get_provider", return_value=unavailable_provider()):
            self.client.post(reverse("planner:plan"), trip_form_data(start_date=future(2).isoformat(),
                                                                     end_date=future(4).isoformat()))
        trip = Trip.objects.latest("created_at")
        with mock.patch("support.services.weather.requests.get", side_effect=requests.Timeout):
            response = self.client.get(reverse("planner:trip_weather", args=[trip.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertEqual(response.json()["days"], [])

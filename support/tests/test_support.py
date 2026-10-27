import json
from datetime import date, timedelta
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from planner.services.ai import AIUnavailable
from planner.tests.helpers import FakeProvider
from support.faq_data import FAQS
from support.models import FAQ, SupportTicket
from support.services import assistant, errors, mongo, retrieval, weather


def post_json(client, url, data):
    return client.post(url, json.dumps(data), content_type="application/json")


# ----------------------------------------------------------------- fakes
class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCollection:
    def __init__(self, fail=False):
        self.documents = []
        self.fail = fail

    def insert_one(self, document):
        if self.fail:
            raise ConnectionError("cluster unreachable")
        self.documents.append(document)
        return FakeInsertResult(f"id{len(self.documents)}")


class FakeMongoDB:
    def __init__(self, fail=False):
        self.collections = {}
        self.fail = fail

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection(self.fail))


class MongoTestMixin:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.db = FakeMongoDB()
        mongo.use_database(self.db)

    def tearDown(self):
        mongo.use_database(None)
        super().tearDown()


def no_ai():
    return FakeProvider(configured=False)


# ------------------------------------------------------------------ FAQs
class FAQTests(TestCase):
    def test_at_least_ten_faqs_seeded_by_migration(self):
        self.assertGreaterEqual(FAQ.objects.filter(is_active=True).count(), 10)

    def test_seed_command_is_idempotent(self):
        call_command("seed_faqs", verbosity=0)
        call_command("seed_faqs", verbosity=0)
        self.assertEqual(FAQ.objects.count(), len(FAQS))

    def test_faq_page_reads_from_database(self):
        FAQ.objects.create(question="Can I plan a trip to the Moon?", answer="Not yet — Earth only.", category="planning")
        response = self.client.get(reverse("support:faq"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Can I plan a trip to the Moon?")
        self.assertEqual(len(response.context["faqs"]), FAQ.objects.filter(is_active=True).count())
        FAQ.objects.filter(question__startswith="Can I plan a trip to the Moon").update(is_active=False)
        self.assertNotContains(self.client.get(reverse("support:faq")), "Moon")

    def test_faq_page_lists_all_error_codes(self):
        response = self.client.get(reverse("support:faq"))
        for code in errors.REQUIRED_CODES:
            self.assertContains(response, f'id="error-{code}"')

    def test_retrieval_finds_relevant_faq(self):
        top = retrieval.search("How do I print my itinerary as a PDF?")[0].faq
        self.assertEqual(top.question, "How can I save or print my itinerary?")
        self.assertEqual(retrieval.search("best beaches in goa"), [])


# ------------------------------------------------------------ error codes
class ErrorRegistryTests(SimpleTestCase):
    def test_all_required_codes_exist_and_are_documented(self):
        self.assertEqual(len(errors.REQUIRED_CODES), 8)
        for code in ["400", "401", "403", "404", "429", "500", "503", "TRIPCRAFT_001"]:
            entry = errors.get(code)
            self.assertIsNotNone(entry, code)
            self.assertTrue(entry.meaning and entry.causes and entry.user_action and entry.troubleshooting)

    def test_detection(self):
        self.assertEqual(errors.detect("What does error 404 mean?"), ["404"])
        self.assertIn("503", errors.detect("Why am I getting a 503 error?"))
        self.assertIn("TRIPCRAFT_001", errors.detect("Explain TRIPCRAFT_001."))
        self.assertIn("TRIPCRAFT_001", errors.detect("What should I do if AI itinerary generation fails?"))
        self.assertEqual(errors.detect("My budget is 500 euros"), [])
        self.assertEqual(errors.detect("Show the budget breakdown"), [])


# -------------------------------------------------------------- assistant
class AssistantTests(TestCase):
    def test_faq_answer_without_ai_uses_retrieved_faq(self):
        reply = assistant.respond("Can I customise my travel budget?", provider=no_ai())
        self.assertEqual(reply.kind, "faq")
        self.assertFalse(reply.ai_used)
        self.assertIn("Adjust your budget", reply.text)
        self.assertTrue(any(s["type"] == "faq" for s in reply.sources))

    def test_ai_answer_receives_faq_context(self):
        provider = FakeProvider(response=json.dumps({"answer": "Use Print / save PDF.", "answerable": True, "topic": "support"}))
        reply = assistant.respond("How do I print my itinerary?", provider=provider)
        self.assertTrue(reply.ai_used)
        self.assertEqual(reply.text, "Use Print / save PDF.")
        prompt = provider.calls[0]["prompt"]
        self.assertIn("How can I save or print my itinerary?", prompt)  # retrieved FAQ passed as context
        self.assertIn("browser's print dialog", prompt)

    def test_404_explained_from_registry(self):
        reply = assistant.respond("What does error 404 mean?", provider=no_ai())
        self.assertEqual(reply.kind, "error_code")
        self.assertIn("Not Found", reply.text)
        self.assertIn(errors.get("404").meaning, reply.text)

    def test_500_explained_safely(self):
        reply = assistant.respond("I got a 500 error", provider=no_ai())
        self.assertIn("Internal Server Error", reply.text)
        for leak in ["Traceback", "SECRET_KEY", "settings.py", "DATABASE_URL", "File \""]:
            self.assertNotIn(leak, reply.text)

    def test_unanswerable_offers_ticket(self):
        reply = assistant.respond("Why is the sky purple on Tuesdays?", provider=no_ai())
        self.assertEqual(reply.kind, "no_answer")
        self.assertTrue(reply.offer_ticket)
        self.assertIn("support ticket", reply.text)

    def test_ai_says_unanswerable_offers_ticket(self):
        provider = FakeProvider(response=json.dumps({"answer": "", "answerable": False, "topic": "support"}))
        reply = assistant.respond("Does TripCraft have a loyalty programme?", provider=provider)
        self.assertTrue(reply.offer_ticket)
        self.assertEqual(reply.kind, "no_answer")

    def test_ai_failure_falls_back_to_help_centre(self):
        reply = assistant.respond("Does TripCraft book flights?", provider=FakeProvider(error=AIUnavailable("rate limited")))
        self.assertFalse(reply.ai_used)
        self.assertIn("help centre", reply.note)
        self.assertIn("does not book", reply.text)

    def test_invalid_ai_json_falls_back(self):
        reply = assistant.respond("Does TripCraft book flights?", provider=FakeProvider(response="not json"))
        self.assertFalse(reply.ai_used)

    def test_explicit_ticket_request(self):
        reply = assistant.respond("I want to create a support ticket", provider=no_ai())
        self.assertEqual(reply.kind, "ticket_prompt")
        self.assertTrue(reply.offer_ticket)


@mock.patch("support.services.assistant.get_provider", no_ai)
class ChatEndpointTests(MongoTestMixin, TestCase):
    url = "/support/chat/"

    def test_chat_responds_and_logs_to_mongodb(self):
        response = post_json(self.client, self.url, {"message": "What does error 404 mean?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reply"]["kind"], "error_code")
        self.assertTrue(data["logged"])
        docs = self.db[mongo.CHAT_COLLECTION].documents
        self.assertEqual([d["role"] for d in docs], ["user", "assistant"])
        self.assertEqual(docs[0]["error_codes"], ["404"])
        self.assertEqual(docs[1]["conversation_id"], data["conversation_id"])

    def test_conversation_continuity(self):
        first = post_json(self.client, self.url, {"message": "hello"}).json()
        second = post_json(self.client, self.url, {"message": "How do I contact support?"}).json()
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        state = self.client.get("/support/chat/state/").json()
        self.assertEqual(len(state["history"]), 4)

    def test_bad_requests_return_400(self):
        self.assertEqual(self.client.post(self.url, "nope", content_type="application/json").status_code, 400)
        self.assertEqual(post_json(self.client, self.url, {"message": "   "}).status_code, 400)
        self.assertEqual(post_json(self.client, self.url, {"message": "x" * 1001}).status_code, 400)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    @override_settings(RATE_LIMITS={"generate": (6, 600), "chat": (2, 60)})
    def test_rate_limit_returns_429(self):
        for _ in range(2):
            post_json(self.client, self.url, {"message": "hello"})
        response = post_json(self.client, self.url, {"message": "hello"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "429")
        self.assertIn("Retry-After", response)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        response = post_json(client, self.url, {"message": "hello"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "403")

    def test_mongodb_failure_is_graceful(self):
        mongo.use_database(FakeMongoDB(fail=True))
        with self.assertLogs("support.services.mongo", level="ERROR") as logs:
            response = post_json(self.client, self.url, {"message": "How do I contact support?"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["logged"])  # the user is not told it was saved
        self.assertNotIn("cluster unreachable", " ".join(logs.output))  # driver message not logged

    def test_mongodb_not_configured_is_graceful(self):
        mongo.use_database(None)
        with override_settings(MONGODB_URI=""):
            response = post_json(self.client, self.url, {"message": "hello"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["logged"])

    def test_feedback_stored_in_mongodb(self):
        chat = post_json(self.client, self.url, {"message": "How do I contact support?"}).json()
        response = post_json(self.client, "/support/chat/feedback/",
                             {"rating": "up", "message_id": chat["message_id"], "comment": "Great"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        doc = self.db[mongo.FEEDBACK_COLLECTION].documents[0]
        self.assertEqual((doc["rating"], doc["message_id"], doc["conversation_id"]), ("up", chat["message_id"], chat["conversation_id"]))

    def test_feedback_failure_is_reported_honestly(self):
        mongo.use_database(FakeMongoDB(fail=True))
        response = post_json(self.client, "/support/chat/feedback/", {"rating": "down"})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["saved"])
        self.assertEqual(post_json(self.client, "/support/chat/feedback/", {"rating": "meh"}).status_code, 400)


class RealDriverFailureTests(TestCase):
    """Uses the real PyMongo client against an address where nothing is listening."""

    @override_settings(MONGODB_URI="mongodb://127.0.0.1:1/?directConnection=true", MONGODB_TIMEOUT_MS=300)
    def test_unreachable_server_does_not_raise(self):
        mongo.use_database(None)
        mongo._client = None
        try:
            with self.assertLogs("support.services.mongo", level="ERROR"):
                self.assertIsNone(mongo.log_message("c1", "user", "hello"))
            self.assertFalse(mongo.save_feedback("c1", "up"))  # skipped quickly during the retry window
        finally:
            mongo._client = None
            mongo.use_database(None)


# ---------------------------------------------------------------- tickets
@mock.patch("support.services.assistant.get_provider", no_ai)
class TicketTests(MongoTestMixin, TestCase):
    def ticket_payload(self, **overrides):
        data = {"confirm": True, "subject": "Generator failing", "description": "The itinerary generator keeps failing.",
                "error_code": "TRIPCRAFT_001", "contact_email": ""}
        data.update(overrides)
        return data

    def test_unresolved_question_then_confirmed_ticket_stored(self):
        chat = post_json(self.client, "/support/chat/", {"message": "Why is the sky purple on Tuesdays?"}).json()
        self.assertTrue(chat["reply"]["offer_ticket"])
        self.assertEqual(SupportTicket.objects.count(), 0)  # never created silently
        response = post_json(self.client, "/support/chat/ticket/", self.ticket_payload())
        self.assertEqual(response.status_code, 201)
        ticket = SupportTicket.objects.get()
        self.assertEqual(response.json()["reference"], ticket.reference)
        self.assertRegex(ticket.reference, r"^TC-[A-Z2-9]{8}$")
        self.assertEqual((ticket.status, ticket.channel, ticket.conversation_id), ("OPEN", "assistant", chat["conversation_id"]))
        self.assertNotIn("email has been sent", response.json()["message"].lower())
        logged = self.db[mongo.CHAT_COLLECTION].documents[-1]
        self.assertEqual(logged["ticket_reference"], ticket.reference)
        self.assertTrue(logged["resulted_in_ticket"])

    def test_ticket_requires_confirmation_and_valid_data(self):
        self.assertEqual(post_json(self.client, "/support/chat/ticket/", self.ticket_payload(confirm=False)).status_code, 400)
        bad = post_json(self.client, "/support/chat/ticket/", self.ticket_payload(description="short", contact_email="nope"))
        self.assertEqual(bad.status_code, 400)
        self.assertIn("description", bad.json()["fields"])
        self.assertIn("contact_email", bad.json()["fields"])
        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_no_reference_when_database_write_fails(self):
        with mock.patch("support.models.SupportTicket.objects.create", side_effect=DatabaseError("db down")):
            response = post_json(self.client, "/support/chat/ticket/", self.ticket_payload())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("reference", response.json())
        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_help_form_creates_ticket(self):
        response = self.client.post(reverse("support:create_ticket"), {
            "subject": "Print layout", "description": "The PDF cuts off the last day.", "error_code": "", "contact_email": ""})
        ticket = SupportTicket.objects.get()
        self.assertRedirects(response, reverse("support:ticket_detail", args=[ticket.reference]))
        self.assertContains(self.client.get(response["Location"]), ticket.reference)

    def test_ticket_access_control(self):
        post_json(self.client, "/support/chat/ticket/", self.ticket_payload())
        ticket = SupportTicket.objects.get()
        url = reverse("support:ticket_detail", args=[ticket.reference])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Client().get(url).status_code, 404)  # another anonymous visitor

        owner = User.objects.create_user("dana", password="pw-Strong-123")
        ticket.user = owner
        ticket.save()
        self.assertEqual(Client().get(url).status_code, 401)  # logged out
        other = Client()
        User.objects.create_user("eve", password="pw-Strong-123")
        other.login(username="eve", password="pw-Strong-123")
        self.assertEqual(other.get(url).status_code, 403)
        mine = Client()
        mine.login(username="dana", password="pw-Strong-123")
        self.assertEqual(mine.get(url).status_code, 200)


# ---------------------------------------------------------------- weather
class WeatherTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.today = date(2026, 10, 27)

    def test_timeout_triggers_fallback(self):
        with mock.patch("support.services.weather.requests.get", side_effect=requests.Timeout) as get:
            result = weather.get_forecast("Lisbon", self.today + timedelta(days=2), self.today + timedelta(days=4), today=self.today)
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.days, [])
        self.assertIn("temporarily unavailable", result.message)
        self.assertIn("timeout", get.call_args.kwargs)

    def test_http_error_triggers_fallback(self):
        response = mock.Mock()
        response.raise_for_status.side_effect = requests.HTTPError("502")
        with mock.patch("support.services.weather.requests.get", return_value=response):
            result = weather.get_forecast("Lisbon", self.today, self.today, today=self.today)
        self.assertEqual(result.status, "unavailable")

    def test_dates_beyond_forecast_window(self):
        with mock.patch("support.services.weather.requests.get") as get:
            result = weather.get_forecast("Lisbon", self.today + timedelta(days=40), self.today + timedelta(days=42), today=self.today)
        self.assertEqual(result.status, "out_of_range")
        get.assert_not_called()

    def test_valid_forecast_parsed(self):
        geo = mock.Mock(**{"json.return_value": {"results": [{"latitude": 38.7, "longitude": -9.1, "name": "Lisbon", "country": "Portugal"}]}})
        start = self.today + timedelta(days=1)
        forecast = mock.Mock(**{"json.return_value": {"daily": {
            "time": [start.isoformat(), (start + timedelta(days=1)).isoformat()],
            "weather_code": [0, 61], "temperature_2m_max": [24.4, 20.0], "temperature_2m_min": [15.1, 14.0],
            "precipitation_probability_max": [5, 80]}}})
        with mock.patch("support.services.weather.requests.get", side_effect=[geo, forecast]):
            result = weather.get_forecast("Lisbon, Portugal", start, start + timedelta(days=1), today=self.today)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.location, "Lisbon, Portugal")
        self.assertEqual(result.days[1]["summary"], "Light rain")
        self.assertEqual(result.days[0]["temp_max"], 24)
        self.assertTrue(result.fetched_at)

    def test_malformed_forecast_triggers_fallback(self):
        geo = mock.Mock(**{"json.return_value": {"results": [{"latitude": 38.7, "longitude": -9.1, "name": "Lisbon"}]}})
        bad = mock.Mock(**{"json.return_value": {"unexpected": True}})
        with mock.patch("support.services.weather.requests.get", side_effect=[geo, bad]):
            result = weather.get_forecast("Lisbon", self.today, self.today, today=self.today)
        self.assertEqual(result.status, "unavailable")


# ------------------------------------------------- health, logging, errors
class HealthAndLoggingTests(TestCase):
    def test_health(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_reports_database_and_optional_services(self):
        data = self.client.get("/health/ready/").json()
        self.assertEqual(data["checks"]["database"], "ok")
        self.assertIn(data["optional"]["mongodb"], {"ok", "unavailable", "not_configured"})
        self.assertNotIn("mongodb://", json.dumps(data))

    def test_readiness_503_when_database_down(self):
        with mock.patch("support.views.health.connection.cursor", side_effect=DatabaseError("down")):
            response = self.client.get("/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["database"], "unavailable")

    def test_request_logging(self):
        with self.assertLogs("tripcraft.requests", level="INFO") as logs:
            response = self.client.get("/health/?secret=abc")
        line = logs.output[0]
        self.assertIn("GET /health/ 200", line)
        self.assertIn(f"id={response['X-Request-ID']}", line)
        self.assertNotIn("secret=abc", line)


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
class ProductionErrorPageTests(TestCase):
    def test_invalid_url_returns_custom_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "This page took a detour.", status_code=404)
        self.assertContains(response, "Ask the assistant", status_code=404)
        self.assertContains(response, "data-chat", status_code=404)

    def test_custom_500_is_safe(self):
        from support.views.errors import server_error

        request = self.client.get("/").wsgi_request
        response = server_error(request)
        self.assertEqual(response.status_code, 500)
        body = response.content.decode()
        self.assertIn("Something went wrong on our side", body)
        self.assertIn("Ask the assistant", body)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("SECRET_KEY", body)

    def test_unhandled_exception_renders_500_page(self):
        client = Client(raise_request_exception=False)
        with mock.patch("planner.views.pages.render", side_effect=RuntimeError("boom secret detail")):
            response = client.get("/")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("boom secret detail", response.content.decode())
        self.assertIn("Something went wrong", response.content.decode())

    def test_500_falls_back_to_plain_html_if_template_fails(self):
        from support.views.errors import server_error

        request = self.client.get("/").wsgi_request
        with mock.patch("support.views.errors.render", side_effect=Exception("template broken")), \
                self.assertLogs("support.views.errors", level="ERROR"):
            response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Something went wrong", response.content.decode())

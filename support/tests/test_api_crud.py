import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from support.models import FAQ, ErrorCode, SupportTicket
from support.services import errors


def send(client, method, url, data=None):
    return getattr(client, method)(url, json.dumps(data or {}), content_type="application/json")


class ErrorCodesInSQLTests(TestCase):
    def test_eight_required_codes_seeded_into_sql(self):
        stored = set(ErrorCode.objects.filter(is_active=True).values_list("code", flat=True))
        self.assertTrue(set(errors.REQUIRED_CODES) <= stored)
        self.assertGreaterEqual(len(stored), 8)

    def test_registry_reads_from_database(self):
        ErrorCode.objects.filter(code="404").update(title="Lost in transit")
        self.assertEqual(errors.get("404").title, "Lost in transit")
        self.assertContains(self.client.get(reverse("support:faq")), "Lost in transit")
        self.assertIn("Lost in transit", errors.as_text(errors.get("404")))

    def test_new_code_added_in_sql_is_recognised(self):
        ErrorCode.objects.create(code="TRIPCRAFT_002", http_status=200, title="Weather unavailable",
                                 meaning="Weather could not be loaded.", causes=["timeout"], user_action="Retry later.",
                                 troubleshooting=["Reload"], where_seen="Dashboard", keywords=["weather unavailable"])
        self.assertIn("TRIPCRAFT_002", errors.detect("why is the weather unavailable?"))
        codes = self.client.get(reverse("support:api_error_codes")).json()["error_codes"]
        self.assertIn("TRIPCRAFT_002", [c["code"] for c in codes])

    def test_falls_back_to_built_in_codes_if_database_fails(self):
        with mock.patch("support.models.ErrorCode.objects.filter", side_effect=DatabaseError("down")):
            entry = errors.get("500")
        self.assertEqual(entry.title, "Internal Server Error")

    def test_error_codes_api(self):
        data = self.client.get(reverse("support:api_error_codes")).json()
        self.assertGreaterEqual(data["count"], 8)
        first = data["error_codes"][0]
        self.assertEqual(set(first), {"code", "http_status", "title", "meaning", "causes", "user_action",
                                      "troubleshooting", "where_seen"})


class FAQApiTests(TestCase):
    def test_faq_api_returns_sql_records(self):
        response = self.client.get(reverse("support:api_faqs"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], FAQ.objects.filter(is_active=True).count())
        self.assertGreaterEqual(data["count"], 10)
        self.assertEqual(set(data["faqs"][0]), {"id", "question", "answer", "category", "category_label"})
        self.assertTrue(data["categories"])

    def test_faq_api_search_and_filter(self):
        data = self.client.get(reverse("support:api_faqs"), {"q": "print"}).json()
        self.assertIn("How can I save or print my itinerary?", [f["question"] for f in data["faqs"]])
        budget = self.client.get(reverse("support:api_faqs"), {"category": "budget"}).json()
        self.assertTrue(budget["faqs"] and all(f["category"] == "budget" for f in budget["faqs"]))

    def test_inactive_faq_hidden_from_api(self):
        FAQ.objects.filter(question="What is TripCraft AI?").update(is_active=False)
        questions = [f["question"] for f in self.client.get(reverse("support:api_faqs")).json()["faqs"]]
        self.assertNotIn("What is TripCraft AI?", questions)

    def test_faq_page_loads_list_from_api(self):
        response = self.client.get(reverse("support:faq"))
        self.assertContains(response, 'data-faq-api="/api/faqs/"')
        self.assertContains(response, "support/js/faq.js")


class TicketCRUDTests(TestCase):
    def setUp(self):
        cache.clear()

    def create(self, client=None, **overrides):
        data = {"subject": "Weather card empty", "description": "The weather card shows nothing for Goa.",
                "error_code": "", "contact_email": "Traveller@Example.com"}
        data.update(overrides)
        response = send(client or self.client, "post", reverse("support:api_tickets"), data)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["ticket"]

    def test_full_crud_via_api(self):
        ticket = self.create()  # Create
        url = reverse("support:api_ticket", args=[ticket["reference"]])
        self.assertEqual(ticket["contact_email"], "traveller@example.com")

        read = self.client.get(url)  # Read
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["ticket"]["subject"], "Weather card empty")

        updated = send(self.client, "patch", url, {"description": "Still empty after a reload on mobile.", "status": "RESOLVED"})
        self.assertEqual(updated.status_code, 200)  # Update
        db = SupportTicket.objects.get(reference=ticket["reference"])
        self.assertEqual(db.description, "Still empty after a reload on mobile.")
        self.assertEqual(db.subject, "Weather card empty")  # untouched fields kept
        self.assertEqual(db.status, "RESOLVED")  # explicit status wins when sent with an edit
        self.assertEqual(updated.json()["ticket"]["status"], "RESOLVED")

        deleted = send(self.client, "delete", url)  # Delete
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(SupportTicket.objects.filter(reference=ticket["reference"]).exists())
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_validation_and_status_rules(self):
        url = reverse("support:api_ticket", args=[self.create()["reference"]])
        self.assertEqual(send(self.client, "patch", url, {"description": "short"}).status_code, 400)
        self.assertEqual(send(self.client, "patch", url, {"status": "IN_PROGRESS"}).status_code, 400)
        self.assertEqual(self.client.patch(url, "nope", content_type="application/json").status_code, 400)

    def test_strangers_cannot_read_update_or_delete(self):
        ticket = self.create()
        url = reverse("support:api_ticket", args=[ticket["reference"]])
        stranger = Client()
        self.assertEqual(stranger.get(url).status_code, 404)
        self.assertEqual(send(stranger, "patch", url, {"subject": "Hacked subject"}).status_code, 404)
        self.assertEqual(send(stranger, "delete", url).status_code, 404)
        self.assertEqual(SupportTicket.objects.get(reference=ticket["reference"]).subject, "Weather card empty")

    def test_lookup_status_codes(self):
        ref = self.create()["reference"]
        other = Client()
        lookup = reverse("support:api_ticket_lookup")
        self.assertEqual(send(other, "post", lookup, {"reference": ref}).status_code, 401)
        self.assertEqual(send(other, "post", lookup, {"reference": ref, "email": "wrong@example.com"}).status_code, 403)
        self.assertEqual(send(other, "post", lookup, {"reference": "TC-ZZZZZZZZ", "email": "a@b.co"}).status_code, 404)
        ok = send(other, "post", lookup, {"reference": ref.lower(), "email": "traveller@example.com"})
        self.assertEqual(ok.status_code, 200)
        # After an email-verified lookup, the ticket opens in that browser.
        self.assertEqual(other.get(reverse("support:ticket_detail", args=[ref])).status_code, 200)

    @override_settings(RATE_LIMITS={"generate": (6, 600), "chat": (20, 60), "lookup": (2, 60)})
    def test_lookup_is_rate_limited(self):
        lookup = reverse("support:api_ticket_lookup")
        for _ in range(2):
            send(self.client, "post", lookup, {"reference": "TC-ZZZZZZZZ", "email": "a@b.co"})
        self.assertEqual(send(self.client, "post", lookup, {"reference": "TC-ZZZZZZZZ", "email": "a@b.co"}).status_code, 429)

    def test_user_owned_ticket_api_access(self):
        owner = User.objects.create_user("fay", password="pw-Strong-123")
        self.client.login(username="fay", password="pw-Strong-123")
        ref = self.create(contact_email="")["reference"]
        self.assertEqual(SupportTicket.objects.get(reference=ref).user, owner)
        url = reverse("support:api_ticket", args=[ref])
        self.assertEqual(Client().get(url).status_code, 401)
        User.objects.create_user("gus", password="pw-Strong-123")
        gus = Client()
        gus.login(username="gus", password="pw-Strong-123")
        self.assertEqual(gus.get(url).status_code, 403)

    def test_html_crud_pages(self):
        response = self.client.post(reverse("support:create_ticket"), {
            "subject": "Print layout", "description": "The PDF cuts off the last day.", "error_code": "", "contact_email": ""})
        ticket = SupportTicket.objects.get()
        detail = reverse("support:ticket_detail", args=[ticket.reference])
        self.assertRedirects(response, detail)

        page = self.client.get(reverse("support:support"))
        self.assertContains(page, ticket.reference)  # listed under "Your tickets"

        edit = self.client.post(detail, {"subject": "Print layout broken", "description": "The PDF cuts off the last two days.",
                                         "error_code": "", "contact_email": ""})
        self.assertRedirects(edit, detail)
        ticket.refresh_from_db()
        self.assertEqual(ticket.subject, "Print layout broken")

        self.client.post(reverse("support:ticket_status", args=[ticket.reference]), {"status": "RESOLVED"})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "RESOLVED")

        bad = self.client.post(detail, {"subject": "x", "description": "short", "error_code": "", "contact_email": ""})
        self.assertEqual(bad.status_code, 400)

        delete = self.client.post(reverse("support:ticket_delete", args=[ticket.reference]))
        self.assertRedirects(delete, reverse("support:support"))
        self.assertFalse(SupportTicket.objects.exists())

    def test_html_lookup_errors(self):
        ref = self.create()["reference"]
        other = Client()
        url = reverse("support:lookup_ticket")
        self.assertEqual(other.post(url, {"reference": ref, "email": ""}).status_code, 401)
        self.assertEqual(other.post(url, {"reference": ref, "email": "wrong@example.com"}).status_code, 403)
        self.assertEqual(other.post(url, {"reference": "TC-ZZZZZZZZ", "email": "a@b.co"}).status_code, 404)
        self.assertRedirects(other.post(url, {"reference": ref, "email": "traveller@example.com"}),
                             reverse("support:ticket_detail", args=[ref]))

    def test_api_write_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = send(csrf_client, "post", reverse("support:api_tickets"),
                        {"subject": "Hello there", "description": "A sufficiently long description."})
        self.assertEqual(response.status_code, 403)

    def test_support_page_has_widget(self):
        response = self.client.get(reverse("support:support"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-chat")

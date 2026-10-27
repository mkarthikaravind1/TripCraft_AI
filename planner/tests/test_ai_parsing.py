import json
from decimal import Decimal

from django.test import SimpleTestCase

from planner.services.ai import AIUnavailable, GeminiProvider, generate_plan
from planner.services.itinerary import ItineraryParseError, TripRequest, parse_ai_response

from .helpers import FakeProvider, ai_plan_json, future


def make_request(days=3, budget="1500"):
    start = future(10)
    from datetime import timedelta

    return TripRequest(destination="Lisbon", start_date=start, end_date=start + timedelta(days=days - 1),
                       budget=Decimal(budget), currency="EUR", travellers=2, interests=["culture"])


class ParseAIResponseTests(SimpleTestCase):
    def test_valid_output(self):
        plan = parse_ai_response(ai_plan_json(3), make_request())
        self.assertEqual(len(plan["days"]), 3)
        self.assertEqual(plan["missing_days"], 0)
        first = plan["days"][0]["activities"][0]
        self.assertEqual(first["cost_per_person"], Decimal("15.00"))
        self.assertEqual(plan["estimates"]["accommodation"]["amount"], Decimal("240.00"))  # 120 x 2 nights

    def test_code_fences_are_tolerated(self):
        plan = parse_ai_response("```json\n" + ai_plan_json(3) + "\n```", make_request())
        self.assertEqual(len(plan["days"]), 3)

    def test_malformed_json_raises(self):
        with self.assertRaises(ItineraryParseError):
            parse_ai_response('{"days": [ {"title": ', make_request())

    def test_wrong_shape_raises(self):
        with self.assertRaises(ItineraryParseError):
            parse_ai_response(json.dumps(["not", "an", "object"]), make_request())
        with self.assertRaises(ItineraryParseError):
            parse_ai_response(json.dumps({"days": []}), make_request())

    def test_oversized_response_raises(self):
        with self.assertRaises(ItineraryParseError):
            parse_ai_response(" " * 300_000, make_request())

    def test_invalid_values_are_cleaned(self):
        data = json.loads(ai_plan_json(3))
        act = data["days"][0]["activities"][0]
        act.update({"cost_per_person": -50, "duration_minutes": "lots", "time_slot": "25:99",
                    "category": "teleportation", "name": "x" * 500})
        data["days"][1]["activities"][1]["cost_per_person"] = 10_000_000  # absurd: capped
        plan = parse_ai_response(json.dumps(data), make_request())
        acts = plan["days"][0]["activities"]
        cleaned = next(a for a in acts if a["name"].startswith("x"))
        self.assertEqual(cleaned["cost_per_person"], Decimal("0.00"))
        self.assertEqual(cleaned["duration_minutes"], 60)
        self.assertEqual(cleaned["time_slot"], "")
        self.assertEqual(cleaned["category"], "sightseeing")
        self.assertLessEqual(len(cleaned["name"]), 120)
        capped = plan["days"][1]["activities"]
        self.assertTrue(all(a["cost_per_person"] <= Decimal("750.00") for a in capped))

    def test_extra_days_truncated_and_missing_days_reported(self):
        self.assertEqual(len(parse_ai_response(ai_plan_json(5), make_request(days=3))["days"]), 3)
        self.assertEqual(parse_ai_response(ai_plan_json(2), make_request(days=3))["missing_days"], 1)

    def test_duplicate_activities_removed(self):
        data = json.loads(ai_plan_json(2))
        data["days"][1]["activities"][0]["name"] = data["days"][0]["activities"][0]["name"]
        plan = parse_ai_response(json.dumps(data), make_request(days=2))
        names = [a["name"] for d in plan["days"] for a in d["activities"] if a["category"] != "rest"]
        self.assertEqual(len(names), len(set(names)))


class GeneratePlanTests(SimpleTestCase):
    def test_live_ai_result(self):
        result = generate_plan(make_request(), provider=FakeProvider(response=ai_plan_json(3)))
        self.assertEqual(result.source, "ai")
        self.assertEqual(result.model, "fake-model")

    def test_api_failure_falls_back_to_labelled_sample(self):
        result = generate_plan(make_request(), provider=FakeProvider(error=AIUnavailable("the AI service timed out")))
        self.assertEqual(result.source, "sample")
        self.assertIn("timed out", result.fallback_reason)
        self.assertIn("not by a live AI model", result.plan["overview"])
        self.assertEqual(len(result.plan["days"]), 3)

    def test_malformed_ai_output_falls_back(self):
        result = generate_plan(make_request(), provider=FakeProvider(response="Sorry, I can't do JSON today"))
        self.assertEqual(result.source, "sample")
        self.assertEqual(result.fallback_reason, "the AI response could not be validated")

    def test_missing_key_is_unavailable(self):
        with self.assertRaises(AIUnavailable):
            GeminiProvider(api_key="").generate("hello")

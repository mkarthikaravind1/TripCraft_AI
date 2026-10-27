import json
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from unittest import skipUnless

from django.test import SimpleTestCase, TestCase

from planner.services import budget

BUDGET_JS = Path(settings.BASE_DIR) / "planner" / "static" / "planner" / "js" / "budget.js"


def sample_inputs(**overrides):
    inputs = {
        "budget_cents": 150000,
        "travellers": 2,
        "meal_percent": 100,
        "stay_percent": 100,
        "contingency_percent": 10,
        "days": [
            {"id": 1, "day_number": 1, "meal_cents_pp": 4000,
             "activities": [{"id": 11, "cost_cents_pp": 1500, "removed": False},
                            {"id": 12, "cost_cents_pp": 350, "removed": False}]},
            {"id": 2, "day_number": 2, "meal_cents_pp": 3333,
             "activities": [{"id": 21, "cost_cents_pp": 2999, "removed": False}]},
            {"id": 3, "day_number": 3, "meal_cents_pp": 4001, "activities": []},
        ],
        "expenses": {
            "transport": {"estimate_cents": 20000, "user_cents": None},
            "accommodation": {"estimate_cents": 24000, "user_cents": None},
            "misc": {"estimate_cents": 6000, "user_cents": None},
        },
    }
    inputs.update(overrides)
    return inputs


class BudgetCalculationTests(SimpleTestCase):
    def test_categories_add_up_to_total(self):
        result = budget.compute(sample_inputs())
        self.assertEqual(sum(result["categories"].values()), result["total"])
        self.assertEqual(sum(d["total"] for d in result["daily"]), result["total"])

    def test_known_values(self):
        result = budget.compute(sample_inputs())
        c = result["categories"]
        self.assertEqual(c["activities"], 2 * (1500 + 350 + 2999))
        self.assertEqual(c["food"], 2 * (4000 + 3333 + 4001))
        self.assertEqual(c["transport"], 20000)
        subtotal = c["transport"] + c["accommodation"] + c["food"] + c["activities"] + c["misc"]
        self.assertEqual(c["contingency"], (subtotal * 10 + 50) // 100)
        self.assertEqual(result["remaining"], 150000 - result["total"])
        self.assertEqual(result["per_traveller"], (result["total"] + 1) // 2)
        self.assertAlmostEqual(result["utilisation"], round(result["total"] / 150000 * 100, 1), places=1)

    def test_removing_an_activity_lowers_total_by_its_group_cost_plus_buffer(self):
        before = budget.compute(sample_inputs())
        inputs = sample_inputs()
        inputs["days"][1]["activities"][0]["removed"] = True
        after = budget.compute(inputs)
        self.assertEqual(before["categories"]["activities"] - after["categories"]["activities"], 2 * 2999)
        self.assertLess(after["total"], before["total"])

    def test_meal_and_stay_styles_and_user_override(self):
        inputs = sample_inputs(meal_percent=55, stay_percent=50)
        inputs["expenses"]["transport"]["user_cents"] = 5000
        result = budget.compute(inputs)
        self.assertEqual(result["categories"]["accommodation"], 12000)
        self.assertEqual(result["categories"]["transport"], 5000)
        base_food = budget.compute(sample_inputs())["categories"]["food"]
        self.assertLess(result["categories"]["food"], base_food)

    def test_over_budget_flag(self):
        result = budget.compute(sample_inputs(budget_cents=1000))
        self.assertTrue(result["over_budget"])
        self.assertLess(result["remaining"], 0)

    def test_baseline_ignores_adjustments(self):
        inputs = sample_inputs(meal_percent=55)
        inputs["days"][0]["activities"][0]["removed"] = True
        baseline = budget.compute(budget.baseline_inputs(inputs))
        self.assertEqual(baseline["total"], budget.compute(sample_inputs())["total"])


@skipUnless(shutil.which("node"), "Node.js not installed")
class BudgetJavaScriptParityTests(SimpleTestCase):
    """budget.js must give exactly the same numbers as budget.py."""

    def test_js_matches_python(self):
        cases = [sample_inputs(), sample_inputs(meal_percent=75, stay_percent=140, contingency_percent=17)]
        cases[1]["expenses"]["misc"]["user_cents"] = 12345
        script = (
            f"const b = require({json.dumps(str(BUDGET_JS))});"
            "const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            "process.stdout.write(JSON.stringify(cases.map(b.compute)));"
        )
        output = subprocess.run(["node", "-e", script], input=json.dumps(cases), capture_output=True, text=True,
                                timeout=20, check=True).stdout
        for js_result, inputs in zip(json.loads(output), cases):
            py_result = budget.compute(inputs)
            self.assertEqual(js_result["categories"], py_result["categories"])
            self.assertEqual(js_result["total"], py_result["total"])
            self.assertEqual(js_result["daily"], py_result["daily"])
            self.assertEqual(js_result["utilisation"], py_result["utilisation"])


class MoneyFormatTests(TestCase):
    def test_indian_grouping(self):
        from planner.templatetags.tripcraft import money

        self.assertEqual(money(1234567800, "INR"), "₹1,23,45,678")
        self.assertEqual(money(123456700, "USD"), "$1,234,567")
        self.assertEqual(money(-50000, "EUR"), "−€500")

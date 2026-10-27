import re
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Trip

MAX_TRIP_DAYS = 14
MAX_BUDGET = Decimal("50000000")

CURRENCIES = [
    ("INR", "₹ INR"),
    ("USD", "$ USD"),
    ("EUR", "€ EUR"),
    ("GBP", "£ GBP"),
    ("JPY", "¥ JPY"),
    ("AUD", "A$ AUD"),
    ("CAD", "C$ CAD"),
    ("SGD", "S$ SGD"),
    ("AED", "AED"),
    ("THB", "฿ THB"),
]
CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
                    "AUD": "A$", "CAD": "C$", "SGD": "S$", "AED": "AED ", "THB": "฿"}
# Below this per-person, per-day amount a trip is not realistically plannable.
MIN_DAILY_PER_PERSON = {"INR": 500, "USD": 15, "EUR": 15, "GBP": 12, "JPY": 2000,
                        "AUD": 20, "CAD": 20, "SGD": 20, "AED": 50, "THB": 400}

INTERESTS = [
    ("culture", "Culture & history"),
    ("food", "Food & cuisine"),
    ("nature", "Nature & outdoors"),
    ("adventure", "Adventure"),
    ("art", "Art & museums"),
    ("shopping", "Shopping"),
    ("nightlife", "Nightlife"),
    ("relaxation", "Relaxation & wellness"),
    ("photography", "Photography"),
    ("local", "Local experiences"),
]
DIETARY = [
    ("", "No dietary needs"),
    ("vegetarian", "Vegetarian"),
    ("vegan", "Vegan"),
    ("halal", "Halal"),
    ("kosher", "Kosher"),
    ("jain", "Jain"),
    ("gluten_free", "Gluten-free"),
]
PLACE_RE = re.compile(r"^[^\W\d_][\w\s,.'()\-–&/]*$", re.UNICODE)


class TripForm(forms.Form):
    destination = forms.CharField(
        max_length=100,
        min_length=2,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Kyoto, Japan", "autocomplete": "off"}),
    )
    origin = forms.CharField(
        label="Starting from",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Chennai (optional)"}),
    )
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    budget = forms.DecimalField(
        label="Total budget",
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"placeholder": "60000", "min": "1", "step": "any", "inputmode": "decimal"}),
    )
    currency = forms.ChoiceField(choices=CURRENCIES, initial="INR")
    travellers = forms.IntegerField(
        min_value=1, max_value=20, initial=2, widget=forms.NumberInput(attrs={"min": "1", "max": "20"})
    )
    interests = forms.MultipleChoiceField(
        choices=INTERESTS,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Pick at least one interest so we can personalise your plan."},
    )
    pace = forms.ChoiceField(choices=Trip.Pace.choices, initial=Trip.Pace.BALANCED, widget=forms.RadioSelect)
    transport = forms.ChoiceField(label="Getting around", choices=Trip.Transport.choices, initial=Trip.Transport.MIXED)
    dietary = forms.ChoiceField(label="Dietary preference", choices=DIETARY, required=False)
    accessibility = forms.CharField(
        label="Accessibility needs",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. step-free access, limited walking (optional)"}),
    )
    notes = forms.CharField(
        label="Anything else?",
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. celebrating an anniversary, love sunrise views…"}),
    )

    def _clean_place(self, field):
        value = " ".join(self.cleaned_data.get(field, "").split())
        if value and not PLACE_RE.match(value):
            raise forms.ValidationError("Please enter a place name using letters, e.g. “Goa, India”.")
        return value

    def clean_destination(self):
        return self._clean_place("destination")

    def clean_origin(self):
        return self._clean_place("origin")

    def clean_interests(self):
        interests = self.cleaned_data["interests"]
        if len(interests) > 6:
            raise forms.ValidationError("Choose up to 6 interests for a focused plan.")
        return interests

    def clean_budget(self):
        budget = self.cleaned_data["budget"]
        if budget <= 0:
            raise forms.ValidationError("Your budget must be greater than zero.")
        if budget > MAX_BUDGET:
            raise forms.ValidationError("That budget is unrealistically large — please enter a smaller amount.")
        return budget

    def clean_notes(self):
        return self.cleaned_data.get("notes", "").strip()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        today = timezone.localdate()

        if start and start < today:
            self.add_error("start_date", "The trip can't start in the past.")
        elif start and start > today + timedelta(days=730):
            self.add_error("start_date", "Please choose a start date within the next two years.")
        if start and end:
            if end < start:
                self.add_error("end_date", "The return date must be on or after the start date.")
            elif (end - start).days + 1 > MAX_TRIP_DAYS:
                self.add_error("end_date", f"Trips can be at most {MAX_TRIP_DAYS} days long.")

        budget, travellers, currency = cleaned.get("budget"), cleaned.get("travellers"), cleaned.get("currency")
        if budget and travellers and currency and start and end and end >= start and not self.errors.get("budget"):
            days = (end - start).days + 1
            minimum = MIN_DAILY_PER_PERSON.get(currency, 10)
            if budget / (travellers * days) < minimum:
                needed = minimum * travellers * days
                self.add_error(
                    "budget",
                    f"That works out to under {CURRENCY_SYMBOLS.get(currency, '')}{minimum:,} per person per day. "
                    f"Plan with at least {CURRENCY_SYMBOLS.get(currency, '')}{needed:,} for this group and trip length.",
                )
        return cleaned


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username",)


class BudgetSettingsForm(forms.Form):
    """Validates JSON posted by the budget-adjustment panel."""

    contingency_percent = forms.IntegerField(min_value=0, max_value=30, required=False)
    meal_style = forms.ChoiceField(choices=[(k, k) for k in Trip.MEAL_STYLES], required=False)
    stay_style = forms.ChoiceField(choices=[(k, k) for k in Trip.STAY_STYLES], required=False)
    transport_amount = forms.DecimalField(min_value=0, max_value=MAX_BUDGET, decimal_places=2, required=False)
    misc_amount = forms.DecimalField(min_value=0, max_value=MAX_BUDGET, decimal_places=2, required=False)
    reset_transport = forms.BooleanField(required=False)
    reset_misc = forms.BooleanField(required=False)

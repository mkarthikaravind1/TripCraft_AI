import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Trip(models.Model):
    """A planned trip and the preferences it was generated from."""

    class Pace(models.TextChoices):
        RELAXED = "relaxed", "Relaxed"
        BALANCED = "balanced", "Balanced"
        PACKED = "packed", "Packed"

    class Transport(models.TextChoices):
        PUBLIC = "public", "Public transport"
        WALKING = "walking", "Walking & cycling"
        TAXI = "taxi", "Taxis & ride-hailing"
        CAR = "car", "Rental car / self-drive"
        MIXED = "mixed", "A sensible mix"

    class Source(models.TextChoices):
        AI = "ai", "AI-generated"
        SAMPLE = "sample", "Sample (local template)"

    # Adjustment-panel presets: a percentage applied to the base estimate.
    MEAL_STYLES = {"standard": 100, "budget": 75, "street": 55}
    STAY_STYLES = {"premium": 140, "standard": 100, "budget": 70, "hostel": 50}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="trips",
    )

    destination = models.CharField(max_length=100)
    origin = models.CharField("starting location", max_length=100, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    travellers = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(20)]
    )
    interests = models.JSONField(default=list)
    pace = models.CharField(max_length=10, choices=Pace.choices, default=Pace.BALANCED)
    transport = models.CharField(max_length=10, choices=Transport.choices, default=Transport.MIXED)
    dietary = models.CharField(max_length=20, blank=True)
    accessibility = models.CharField(max_length=200, blank=True)
    notes = models.TextField(max_length=500, blank=True)

    # Generation metadata.
    source = models.CharField(max_length=10, choices=Source.choices)
    ai_model = models.CharField(max_length=80, blank=True)
    fallback_reason = models.CharField(max_length=200, blank=True)
    overview = models.TextField(blank=True, help_text="Why this plan fits the traveller.")
    tips = models.JSONField(default=list, blank=True)

    # Budget-adjustment settings (deterministic, applied by services.budget).
    contingency_percent = models.PositiveSmallIntegerField(
        default=10, validators=[MaxValueValidator(30)]
    )
    meal_style = models.CharField(max_length=10, default="standard")
    stay_style = models.CharField(max_length=10, default="standard")
    estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="trip_end_after_start",
            ),
            models.CheckConstraint(condition=models.Q(budget__gt=0), name="trip_budget_positive"),
        ]

    def __str__(self):
        return f"{self.destination} ({self.start_date:%d %b %Y})"

    @property
    def num_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def num_nights(self):
        return max(self.num_days - 1, 1)

    @property
    def meal_percent(self):
        return self.MEAL_STYLES.get(self.meal_style, 100)

    @property
    def stay_percent(self):
        return self.STAY_STYLES.get(self.stay_style, 100)

    @property
    def is_ai(self):
        return self.source == self.Source.AI


class ItineraryDay(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="days")
    day_number = models.PositiveSmallIntegerField()
    date = models.DateField()
    title = models.CharField(max_length=120, blank=True)
    summary = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text="Travel / rest guidance for the day.")
    # List of {"meal": str, "suggestion": str, "cost_per_person": "12.50"}
    meals = models.JSONField(default=list, blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["day_number"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "day_number"], name="unique_day_per_trip"),
        ]

    def __str__(self):
        return f"Day {self.day_number} of {self.trip}"


class Activity(models.Model):
    class Category(models.TextChoices):
        SIGHTSEEING = "sightseeing", "Sightseeing"
        CULTURE = "culture", "Culture & history"
        FOOD = "food", "Food experience"
        NATURE = "nature", "Nature & outdoors"
        ADVENTURE = "adventure", "Adventure"
        SHOPPING = "shopping", "Shopping"
        NIGHTLIFE = "nightlife", "Nightlife"
        RELAXATION = "relaxation", "Relaxation"
        TRAVEL = "travel", "Travel"
        REST = "rest", "Rest break"

    day = models.ForeignKey(ItineraryDay, on_delete=models.CASCADE, related_name="activities")
    order = models.PositiveSmallIntegerField(default=0)
    time_slot = models.CharField(max_length=5, blank=True, help_text="HH:MM, 24-hour")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(5), MaxValueValidator(720)]
    )
    location = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.SIGHTSEEING)
    cost_per_person = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_completed = models.BooleanField(default=False)
    is_removed = models.BooleanField(default=False)

    class Meta:
        ordering = ["order", "time_slot"]
        verbose_name_plural = "activities"

    def __str__(self):
        return self.name

    @property
    def is_break(self):
        return self.category in {self.Category.TRAVEL, self.Category.REST}

    @property
    def duration_label(self):
        hours, minutes = divmod(self.duration_minutes, 60)
        if hours and minutes:
            return f"{hours} h {minutes} min"
        if hours:
            return f"{hours} h"
        return f"{minutes} min"


class Expense(models.Model):
    """Trip-level cost estimates that are not itemised per activity or meal."""

    class Category(models.TextChoices):
        TRANSPORT = "transport", "Transportation"
        ACCOMMODATION = "accommodation", "Accommodation"
        MISC = "misc", "Miscellaneous"

    class Source(models.TextChoices):
        AI = "ai", "AI estimate"
        SAMPLE = "sample", "Sample estimate"

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="expenses")
    category = models.CharField(max_length=15, choices=Category.choices)
    description = models.CharField(max_length=200, blank=True)
    estimated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source = models.CharField(max_length=10, choices=Source.choices)
    # When the traveller types their own figure, it replaces the estimate.
    user_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["category"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "category"], name="unique_expense_category"),
        ]

    def __str__(self):
        return f"{self.get_category_display()} for {self.trip}"

    @property
    def amount(self):
        return self.user_amount if self.user_amount is not None else self.estimated_amount

    @property
    def source_label(self):
        return "Your figure" if self.user_amount is not None else self.get_source_display()

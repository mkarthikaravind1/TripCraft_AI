import secrets

from django.conf import settings
from django.db import models

TICKET_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid confusion


def generate_ticket_reference():
    return "TC-" + "".join(secrets.choice(TICKET_ALPHABET) for _ in range(8))


class FAQ(models.Model):
    """A help-centre question. Shown on /faq/ and used by the assistant as factual context."""

    class Category(models.TextChoices):
        GETTING_STARTED = "getting_started", "Getting started"
        PLANNING = "planning", "Planning & itineraries"
        BUDGET = "budget", "Budget"
        ACCOUNT = "account", "Saving & accounts"
        TROUBLESHOOTING = "troubleshooting", "Troubleshooting"
        SUPPORT = "support", "Support"

    question = models.CharField(max_length=200, unique=True)
    answer = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices)
    keywords = models.CharField(max_length=200, blank=True, help_text="Extra search terms for retrieval.")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        RESOLVED = "RESOLVED", "Resolved"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"

    class Channel(models.TextChoices):
        ASSISTANT = "assistant", "AI assistant"
        HELP_FORM = "help_form", "Help-centre form"

    reference = models.CharField(max_length=11, unique=True, default=generate_ticket_reference, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets"
    )
    session_key = models.CharField(max_length=40, blank=True, help_text="Anonymous browser session reference.")
    contact_email = models.EmailField(blank=True, help_text="Optional — only if the traveller wants a reply.")
    subject = models.CharField(max_length=120)
    description = models.TextField(max_length=2000)
    error_code = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=6, choices=Priority.choices, default=Priority.NORMAL)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.HELP_FORM)
    conversation_id = models.CharField(max_length=36, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference}: {self.subject}"

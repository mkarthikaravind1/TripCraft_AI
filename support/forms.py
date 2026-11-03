from django import forms

from .models import SupportTicket
from .services import errors


def error_code_choices():
    """Evaluated when a form is built, so the database isn't queried at import time."""
    return [("", "No error code")] + [(e.code, f"{e.code} — {e.title}") for e in errors.all_codes()]


class SupportTicketForm(forms.ModelForm):
    error_code = forms.ChoiceField(label="Error code (if you saw one)", required=False, choices=error_code_choices)

    class Meta:
        model = SupportTicket
        fields = ["subject", "description", "error_code", "contact_email"]
        labels = {"contact_email": "Email for a reply"}
        widgets = {
            "subject": forms.TextInput(attrs={"placeholder": "e.g. Itinerary won't generate", "maxlength": 120}),
            "description": forms.Textarea(attrs={"rows": 4, "maxlength": 2000,
                                                 "placeholder": "What were you doing, and what happened?"}),
            "contact_email": forms.EmailInput(attrs={"placeholder": "you@example.com (optional)"}),
        }

    def clean_subject(self):
        subject = " ".join(self.cleaned_data["subject"].split())
        if len(subject) < 4:
            raise forms.ValidationError("Please add a short subject (at least 4 characters).")
        return subject

    def clean_contact_email(self):
        return self.cleaned_data.get("contact_email", "").strip().lower()

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if len(description) < 10:
            raise forms.ValidationError("Please describe the problem in a little more detail (at least 10 characters).")
        if len(description) > 2000:
            raise forms.ValidationError("Please keep the description under 2,000 characters.")
        return description


class TicketLookupForm(forms.Form):
    reference = forms.CharField(
        label="Ticket reference", max_length=11,
        widget=forms.TextInput(attrs={"placeholder": "TC-ABCD2345", "autocomplete": "off", "spellcheck": "false"}),
    )
    email = forms.EmailField(
        label="Email used on the ticket", required=False,
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email"}),
    )

    def clean_reference(self):
        return self.cleaned_data["reference"].strip().upper()

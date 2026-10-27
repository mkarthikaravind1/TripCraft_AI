from django import forms

from .models import SupportTicket
from .services import errors


class SupportTicketForm(forms.ModelForm):
    error_code = forms.ChoiceField(
        label="Error code (if you saw one)",
        required=False,
        choices=[("", "No error code")] + [(e.code, f"{e.code} — {e.title}") for e in errors.all_codes()],
    )

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

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if len(description) < 10:
            raise forms.ValidationError("Please describe the problem in a little more detail (at least 10 characters).")
        if len(description) > 2000:
            raise forms.ValidationError("Please keep the description under 2,000 characters.")
        return description

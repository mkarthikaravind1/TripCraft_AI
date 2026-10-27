"""Help centre: FAQ page, support-ticket form and ticket status page."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from support.forms import SupportTicketForm
from support.models import FAQ, SupportTicket
from support.services import errors, tickets

from .errors import error_response


def _faq_context(form=None):
    faqs = list(FAQ.objects.filter(is_active=True))
    categories = []
    for value, label in FAQ.Category.choices:
        if any(f.category == value for f in faqs):
            categories.append((value, label))
    return {
        "faqs": faqs,
        "categories": categories,
        "error_codes": errors.all_codes(),
        "ticket_form": form or SupportTicketForm(),
    }


def faq_page(request):
    return render(request, "support/faq.html", _faq_context())


@require_http_methods(["POST"])
def create_ticket(request):
    form = SupportTicketForm(request.POST)
    if not form.is_valid():
        return render(request, "support/faq.html", _faq_context(form), status=400)
    try:
        ticket = tickets.create_ticket(request, form.cleaned_data, SupportTicket.Channel.HELP_FORM)
    except tickets.TicketCreationError:
        return error_response(request, "503", message="We couldn't save your ticket right now. Please try again in a few minutes.")
    messages.success(request, f"Ticket {ticket.reference} created. Keep this reference to check its status.")
    return redirect("support:ticket_detail", reference=ticket.reference)


def ticket_detail(request, reference):
    ticket = get_object_or_404(SupportTicket, reference=reference.upper())
    status = tickets.access_status(request, ticket)
    if status == 401:
        return error_response(request, "401")
    if status == 403:
        return error_response(request, "403")
    if status == 404:
        return error_response(request, "404")
    return render(request, "support/ticket_detail.html", {"ticket": ticket, "error": errors.get(ticket.error_code)})

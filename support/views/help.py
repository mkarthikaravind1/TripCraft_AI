"""Help centre (FAQ page) and support pages: create, look up, view, edit, resolve and delete tickets."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from support.forms import SupportTicketForm, TicketLookupForm
from support.models import FAQ, SupportTicket
from support.services import errors, ratelimit, tickets

from .errors import error_response


def faq_page(request):
    # The FAQ list itself is loaded in the browser from /api/faqs/; this copy is the no-JavaScript fallback.
    return render(request, "support/faq.html", {
        "faqs": list(FAQ.objects.filter(is_active=True)),
        "error_codes": errors.all_codes(),
    })


def _support_context(request, form=None, lookup_form=None):
    return {
        "ticket_form": form or SupportTicketForm(),
        "lookup_form": lookup_form or TicketLookupForm(),
        "my_tickets": tickets.visible_tickets(request),
    }


def support_page(request):
    return render(request, "support/support.html", _support_context(request))


@require_POST
def create_ticket(request):
    form = SupportTicketForm(request.POST)
    if not form.is_valid():
        return render(request, "support/support.html", _support_context(request, form=form), status=400)
    try:
        ticket = tickets.create_ticket(request, form.cleaned_data, SupportTicket.Channel.HELP_FORM)
    except tickets.TicketCreationError:
        return error_response(request, "503", message="We couldn't save your ticket right now. Please try again in a few minutes.")
    messages.success(request, f"Ticket {ticket.reference} created. Keep this reference to check its status.")
    return redirect("support:ticket_detail", reference=ticket.reference)


@require_POST
def lookup_ticket(request):
    allowed, _ = ratelimit.hit(request, "lookup")
    if not allowed:
        return error_response(request, "429", message="Too many lookups. Please wait a minute and try again.")
    form = TicketLookupForm(request.POST)
    if not form.is_valid():
        return render(request, "support/support.html", _support_context(request, lookup_form=form), status=400)
    status, ticket = tickets.lookup(request, form.cleaned_data["reference"], form.cleaned_data["email"])
    if status == 200:
        return redirect("support:ticket_detail", reference=ticket.reference)
    message = {
        401: "Enter the email address you used on the ticket.",
        403: "That email doesn't match this ticket. Tickets created without an email can only be opened from the browser that created them.",
        404: "No ticket has that reference. Check it and try again.",
    }[status]
    return error_response(request, str(status), message=message)


def _owned_ticket(request, reference):
    """Return (ticket, None) if the visitor may access it, else (None, error response)."""
    ticket = get_object_or_404(SupportTicket, reference=reference.upper())
    status = tickets.access_status(request, ticket)
    if status != 200:
        return None, error_response(request, str(status))
    return ticket, None


@require_http_methods(["GET", "POST"])
def ticket_detail(request, reference):
    ticket, denied = _owned_ticket(request, reference)
    if denied:
        return denied
    if request.method == "POST":  # Update
        form = SupportTicketForm(request.POST)
        if form.is_valid():
            tickets.update_ticket(ticket, form.cleaned_data)
            messages.success(request, f"Ticket {ticket.reference} updated.")
            return redirect("support:ticket_detail", reference=ticket.reference)
        status = 400
    else:
        form = SupportTicketForm(initial={name: getattr(ticket, name) for name in tickets.EDITABLE_FIELDS})
        status = 200
    return render(request, "support/ticket_detail.html",
                  {"ticket": ticket, "error": errors.get(ticket.error_code) if ticket.error_code else None,
                   "edit_form": form, "editing": status == 400}, status=status)


@require_POST
def ticket_status(request, reference):
    ticket, denied = _owned_ticket(request, reference)
    if denied:
        return denied
    new_status = request.POST.get("status", "")
    try:
        tickets.set_status(ticket, new_status)
    except ValueError:
        return error_response(request, "400", message="Status can only be set to Open or Resolved.")
    messages.success(request, f"Ticket {ticket.reference} marked as {ticket.get_status_display().lower()}.")
    return redirect("support:ticket_detail", reference=ticket.reference)


@require_POST
def ticket_delete(request, reference):
    ticket, denied = _owned_ticket(request, reference)
    if denied:
        return denied
    ref = ticket.reference
    tickets.delete_ticket(request, ticket)
    messages.info(request, f"Ticket {ref} was deleted.")
    return redirect("support:support")

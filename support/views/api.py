"""
JSON API.

GET    /api/faqs/                   FAQs from SQL (used by the FAQ page); ?q= and ?category= filter
GET    /api/error-codes/            supported error codes from SQL
POST   /api/tickets/                create a ticket                       (Create)
POST   /api/tickets/lookup/         find a ticket by reference + email    (Read, 401/403/404)
GET    /api/tickets/<ref>/          read a ticket you own                 (Read)
PATCH  /api/tickets/<ref>/          update subject/description/... or status   (Update)
DELETE /api/tickets/<ref>/          delete a ticket you own               (Delete)

Unsafe methods require Django's CSRF token (X-CSRFToken header).
"""

import json

from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from support.forms import SupportTicketForm
from support.models import FAQ, SupportTicket
from support.services import errors, ratelimit, tickets

from .errors import error_response


def _payload(request):
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def serialize_faq(faq):
    return {"id": faq.id, "question": faq.question, "answer": faq.answer, "category": faq.category,
            "category_label": faq.get_category_display()}


def serialize_error(entry):
    return {"code": entry.code, "http_status": entry.http_status, "title": entry.title, "meaning": entry.meaning,
            "causes": list(entry.causes), "user_action": entry.user_action,
            "troubleshooting": list(entry.troubleshooting), "where_seen": entry.where_seen}


def serialize_ticket(ticket):
    return {
        "reference": ticket.reference,
        "subject": ticket.subject,
        "description": ticket.description,
        "error_code": ticket.error_code,
        "contact_email": ticket.contact_email,
        "status": ticket.status,
        "status_label": ticket.get_status_display(),
        "priority": ticket.priority,
        "channel": ticket.channel,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "url": reverse("support:ticket_detail", args=[ticket.reference]),
    }


@require_GET
def faqs_api(request):
    faqs = FAQ.objects.filter(is_active=True)
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "").strip()
    if query:
        faqs = faqs.filter(Q(question__icontains=query) | Q(answer__icontains=query) | Q(keywords__icontains=query))
    if category:
        faqs = faqs.filter(category=category)
    faqs = list(faqs)
    used = {f.category for f in FAQ.objects.filter(is_active=True).only("category")}
    return JsonResponse({
        "count": len(faqs),
        "categories": [{"value": v, "label": label} for v, label in FAQ.Category.choices if v in used],
        "faqs": [serialize_faq(f) for f in faqs],
    })


@require_GET
def error_codes_api(request):
    codes = errors.all_codes()
    return JsonResponse({"count": len(codes), "error_codes": [serialize_error(e) for e in codes]})


def _validated(data, ticket=None):
    """Validate ticket fields; for updates, unspecified fields keep their current values."""
    base = {name: getattr(ticket, name) for name in tickets.EDITABLE_FIELDS} if ticket else {}
    merged = {**base, **{k: data[k] for k in tickets.EDITABLE_FIELDS if k in data and isinstance(data[k], str)}}
    form = SupportTicketForm(merged)
    return form


def _form_errors(form):
    return JsonResponse({"ok": False, "code": "400", "error": "Please check the ticket details.",
                         "fields": {k: [str(e) for e in v] for k, v in form.errors.items()}}, status=400)


@require_POST
def tickets_api(request):
    data = _payload(request)
    if data is None:
        return error_response(request, "400", message="Invalid JSON.")
    form = _validated(data)
    if not form.is_valid():
        return _form_errors(form)
    try:
        ticket = tickets.create_ticket(request, form.cleaned_data, SupportTicket.Channel.HELP_FORM)
    except tickets.TicketCreationError:
        return error_response(request, "503", message="The ticket could not be saved right now. Please try again.")
    return JsonResponse({"ok": True, "ticket": serialize_ticket(ticket)}, status=201)


@require_POST
def ticket_lookup_api(request):
    allowed, retry_after = ratelimit.hit(request, "lookup")
    if not allowed:
        return error_response(request, "429", message="Too many lookups. Please wait a minute.", extra={"retry_after": retry_after})
    data = _payload(request)
    if data is None:
        return error_response(request, "400", message="Invalid JSON.")
    status, ticket = tickets.lookup(request, data.get("reference"), data.get("email"))
    if status == 401:
        return error_response(request, "401", message="Enter the email address you used on the ticket.")
    if status == 403:
        return error_response(request, "403", message="That email doesn't match this ticket.")
    if status == 404:
        return error_response(request, "404", message="No ticket has that reference.")
    return JsonResponse({"ok": True, "ticket": serialize_ticket(ticket)})


@require_http_methods(["GET", "PATCH", "DELETE"])
def ticket_api(request, reference):
    ticket = SupportTicket.objects.filter(reference=reference.upper()).first()
    if ticket is None:
        return error_response(request, "404", message="No ticket has that reference.")
    status = tickets.access_status(request, ticket)
    if status != 200:
        return error_response(request, str(status))

    if request.method == "GET":
        return JsonResponse({"ok": True, "ticket": serialize_ticket(ticket)})

    if request.method == "DELETE":
        tickets.delete_ticket(request, ticket)
        return JsonResponse({"ok": True, "deleted": reference.upper()})

    data = _payload(request)
    if data is None:
        return error_response(request, "400", message="Invalid JSON.")
    if "status" in data:
        try:
            tickets.set_status(ticket, data["status"])
        except ValueError:
            return error_response(request, "400", message="Status can only be set to OPEN or RESOLVED.")
    if any(k in data for k in tickets.EDITABLE_FIELDS):
        form = _validated(data, ticket)
        if not form.is_valid():
            return _form_errors(form)
        tickets.update_ticket(ticket, form.cleaned_data)
    return JsonResponse({"ok": True, "ticket": serialize_ticket(ticket)})

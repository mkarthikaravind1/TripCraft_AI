"""Support-ticket creation and access rules."""

import logging

from django.db import DatabaseError, IntegrityError, transaction

from support.models import SupportTicket

logger = logging.getLogger(__name__)
SESSION_KEY = "ticket_refs"


class TicketCreationError(Exception):
    pass


def _session_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def create_ticket(request, cleaned, channel, conversation_id=""):
    """Create a ticket from validated form data. Raises TicketCreationError on database failure."""
    for _attempt in range(3):  # retry on the (very unlikely) reference collision
        try:
            with transaction.atomic():
                ticket = SupportTicket.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    session_key=_session_key(request),
                    subject=cleaned["subject"],
                    description=cleaned["description"],
                    error_code=cleaned.get("error_code", "") or "",
                    contact_email=cleaned.get("contact_email", "") or "",
                    priority=SupportTicket.Priority.HIGH if cleaned.get("error_code") in {"500", "503"} else SupportTicket.Priority.NORMAL,
                    channel=channel,
                    conversation_id=conversation_id[:36],
                )
            break
        except IntegrityError:
            continue
        except DatabaseError as exc:
            logger.error("Support ticket could not be saved (%s)", type(exc).__name__)
            raise TicketCreationError from exc
    else:
        raise TicketCreationError("could not allocate a ticket reference")

    remember(request, ticket)
    return ticket


def remember(request, ticket):
    """Grant this browser session access to a ticket (its creator, or after an email-verified lookup)."""
    refs = [r for r in request.session.get(SESSION_KEY, []) if r != ticket.reference]
    request.session[SESSION_KEY] = ([ticket.reference] + refs)[:20]


def forget(request, ticket):
    request.session[SESSION_KEY] = [r for r in request.session.get(SESSION_KEY, []) if r != ticket.reference]


def access_status(request, ticket):
    """HTTP-style status for a ticket: 200 allowed, 401 log in needed, 403 other account, 404 hidden."""
    if ticket.reference in request.session.get(SESSION_KEY, []):
        return 200
    if ticket.user_id is not None:
        if not request.user.is_authenticated:
            return 401
        return 200 if request.user.id == ticket.user_id else 403
    return 404


def visible_tickets(request):
    """Tickets this visitor may see: their account's tickets plus those remembered in this session."""
    from django.db.models import Q

    refs = request.session.get(SESSION_KEY, [])
    query = Q(reference__in=refs)
    if request.user.is_authenticated:
        query |= Q(user=request.user)
    return SupportTicket.objects.filter(query).order_by("-created_at")[:20]


def lookup(request, reference, email):
    """Find a ticket by reference + the email used on it.

    Returns (status, ticket): 401 no email given, 404 unknown reference,
    403 email doesn't match (or the ticket has no email), 200 found.
    """
    reference = (reference or "").strip().upper()
    email = (email or "").strip().lower()
    if not email:
        return 401, None
    ticket = SupportTicket.objects.filter(reference=reference).first()
    if ticket is None:
        return 404, None
    if not ticket.contact_email or ticket.contact_email.lower() != email:
        return 403, None
    remember(request, ticket)
    return 200, ticket


EDITABLE_FIELDS = ("subject", "description", "error_code", "contact_email")


def update_ticket(ticket, cleaned):
    """Update the traveller-editable fields. Resolved tickets are re-opened when edited."""
    for name in EDITABLE_FIELDS:
        if name in cleaned:
            setattr(ticket, name, cleaned[name] or "")
    if ticket.status == SupportTicket.Status.RESOLVED:
        ticket.status = SupportTicket.Status.OPEN
    ticket.save()
    return ticket


def set_status(ticket, status):
    """Travellers may close (resolve) or re-open their own ticket; other statuses are for staff."""
    if status not in {SupportTicket.Status.OPEN, SupportTicket.Status.RESOLVED}:
        raise ValueError("status must be OPEN or RESOLVED")
    ticket.status = status
    ticket.save(update_fields=["status", "updated_at"])
    return ticket


def delete_ticket(request, ticket):
    forget(request, ticket)
    ticket.delete()

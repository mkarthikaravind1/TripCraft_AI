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

    refs = [r for r in request.session.get(SESSION_KEY, []) if r != ticket.reference]
    request.session[SESSION_KEY] = ([ticket.reference] + refs)[:20]
    return ticket


def access_status(request, ticket):
    """HTTP-style status for viewing a ticket: 200 allowed, 401 log in needed, 403 other account, 404 hidden."""
    if ticket.user_id is not None:
        if not request.user.is_authenticated:
            return 401
        return 200 if request.user.id == ticket.user_id else 403
    return 200 if ticket.reference in request.session.get(SESSION_KEY, []) else 404

"""
JSON endpoints for the floating assistant widget.

POST /support/chat/          – ask a question
POST /support/chat/ticket/   – create a ticket after the user confirms
POST /support/chat/feedback/ – thumbs up/down on an assistant reply
"""

import json
import uuid

from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from support.forms import SupportTicketForm
from support.models import SupportTicket
from support.services import assistant, mongo, ratelimit, tickets

from .errors import error_response

SESSION_CHAT = "assistant_chat"
MAX_HISTORY = 8


def _payload(request):
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _conversation(request):
    chat = request.session.get(SESSION_CHAT)
    if not chat or not isinstance(chat.get("history"), list):
        chat = {"id": str(uuid.uuid4()), "history": []}
    return chat


def _refs(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key, (request.user.id if request.user.is_authenticated else None)


@require_POST
def chat_message(request):
    allowed, retry_after = ratelimit.hit(request, "chat")
    if not allowed:
        response = error_response(request, "429", message="You're sending messages very quickly. Please wait a moment.",
                                  extra={"retry_after": retry_after})
        response["Retry-After"] = str(retry_after)
        return response

    data = _payload(request)
    if data is None or not isinstance(data.get("message"), str):
        return error_response(request, "400", message="Please send a message.")
    message = assistant.clean_message(data["message"])
    if not message:
        return error_response(request, "400", message="Please type a question first.")
    if len(message) > assistant.MAX_MESSAGE_CHARS:
        return error_response(request, "400", message=f"Please keep messages under {assistant.MAX_MESSAGE_CHARS} characters.")

    chat = _conversation(request)
    session_ref, user_id = _refs(request)
    reply = assistant.respond(message, chat["history"])

    mongo.log_message(chat["id"], "user", message, session_ref=session_ref, user_id=user_id,
                      error_codes=reply.error_codes)
    message_id = mongo.log_message(
        chat["id"], "assistant", reply.text, session_ref=session_ref, user_id=user_id, kind=reply.kind,
        error_codes=reply.error_codes, faq_ids=[s["id"] for s in reply.sources if s["type"] == "faq"],
        ai_used=reply.ai_used,
    )

    chat["history"] = (chat["history"] + [{"role": "user", "text": message}, {"role": "assistant", "text": reply.text}])[-MAX_HISTORY:]
    if reply.offer_ticket:
        chat["last_problem"] = message
    request.session[SESSION_CHAT] = chat

    return JsonResponse({
        "ok": True,
        "conversation_id": chat["id"],
        "message_id": message_id or "",
        "logged": message_id is not None,
        "reply": reply.as_dict(),
    })


@require_POST
def chat_ticket(request):
    data = _payload(request)
    if data is None:
        return error_response(request, "400", message="Invalid request.")
    if data.get("confirm") is not True:
        return error_response(request, "400", message="Please confirm that you want to create a ticket.")

    form = SupportTicketForm({
        "subject": data.get("subject", ""),
        "description": data.get("description", ""),
        "error_code": data.get("error_code", ""),
        "contact_email": data.get("contact_email", ""),
    })
    if not form.is_valid():
        return JsonResponse({"ok": False, "code": "400", "error": "Please check the ticket details.",
                             "fields": {k: [str(e) for e in v] for k, v in form.errors.items()}}, status=400)

    chat = _conversation(request)
    try:
        ticket = tickets.create_ticket(request, form.cleaned_data, SupportTicket.Channel.ASSISTANT, conversation_id=chat["id"])
    except tickets.TicketCreationError:
        return error_response(request, "503", message="We couldn't create your ticket right now. Please try again in a "
                                                      "few minutes, or use the form in the help centre.")
    request.session[SESSION_CHAT] = chat
    session_ref, user_id = _refs(request)
    mongo.log_message(chat["id"], "system", f"Support ticket {ticket.reference} created.", session_ref=session_ref,
                      user_id=user_id, kind="ticket_created", error_codes=[ticket.error_code] if ticket.error_code else [],
                      ticket_reference=ticket.reference)
    return JsonResponse({
        "ok": True,
        "reference": ticket.reference,
        "url": reverse("support:ticket_detail", args=[ticket.reference]),
        "message": f"Ticket {ticket.reference} has been created. The support team will review it"
                   + (" and reply to the email you gave." if ticket.contact_email else ".")
                   + " TripCraft doesn't send automatic emails, so keep this reference.",
    }, status=201)


@require_POST
def chat_feedback(request):
    data = _payload(request)
    if data is None or data.get("rating") not in {"up", "down"}:
        return error_response(request, "400", message="Feedback must be thumbs up or down.")
    comment = str(data.get("comment", ""))[:500]
    message_id = str(data.get("message_id", ""))[:40]
    chat = _conversation(request)
    session_ref, _ = _refs(request)
    saved = mongo.save_feedback(chat["id"], data["rating"], message_id=message_id, comment=comment, session_ref=session_ref)
    if not saved:
        return JsonResponse({"ok": False, "saved": False,
                             "message": "Thanks — but feedback can't be recorded right now."}, status=503)
    return JsonResponse({"ok": True, "saved": True, "message": "Thanks for your feedback!"})


def chat_state(request):
    """Return the current conversation so the widget can restore it after navigation."""
    chat = request.session.get(SESSION_CHAT) or {}
    return JsonResponse({"ok": True, "conversation_id": chat.get("id", ""), "history": chat.get("history", []),
                         "last_problem": chat.get("last_problem", "")})

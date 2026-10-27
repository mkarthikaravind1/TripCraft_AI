"""
MongoDB storage for assistant chat logs and feedback (PyMongo).

SQL (Django ORM) holds FAQs, tickets and trips; MongoDB holds only the
conversation log and feedback documents. MongoDB is optional at runtime: when
it is not configured or unreachable, writes return None/False, the failure is
logged, and the rest of TripCraft keeps working. Callers must never tell the
user something was saved unless these functions report success.
"""

import logging
import threading
import time
from datetime import UTC, datetime

from django.conf import settings

logger = logging.getLogger(__name__)

CHAT_COLLECTION = "chat_messages"
FEEDBACK_COLLECTION = "feedback"
MAX_TEXT = 2000
RETRY_AFTER_SECONDS = 30  # after a failure, skip MongoDB briefly instead of slowing every request

_lock = threading.Lock()
_client = None
_down_until = 0.0
_override_db = None  # tests can inject a database-like object
failure_count = 0


def use_database(db):
    """Inject a database object (e.g. a fake in tests). Pass None to reset."""
    global _override_db, _down_until
    _override_db = db
    _down_until = 0.0


def is_configured():
    return _override_db is not None or bool(settings.MONGODB_URI)


def get_db():
    """Return the database handle, or None when MongoDB is not configured."""
    global _client
    if _override_db is not None:
        return _override_db
    if not settings.MONGODB_URI:
        return None
    with _lock:
        if _client is None:
            from pymongo import MongoClient

            timeout = settings.MONGODB_TIMEOUT_MS
            _client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=timeout,
                connectTimeoutMS=timeout,
                socketTimeoutMS=timeout * 2,
                appname="tripcraft-ai",
                tz_aware=True,
            )
    return _client[settings.MONGODB_DB_NAME]


def _record_failure(operation, exc):
    global _down_until, failure_count
    failure_count += 1
    _down_until = time.monotonic() + RETRY_AFTER_SECONDS
    # Log the error type only: messages from drivers can include hostnames.
    logger.error("MongoDB %s failed (%s); chat/feedback storage is degraded.", operation, type(exc).__name__)


def _available_db():
    if time.monotonic() < _down_until:
        return None
    return get_db()


def _clip(text, limit=MAX_TEXT):
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


def log_message(conversation_id, role, text, *, session_ref="", user_id=None, kind="", error_codes=None,
                faq_ids=None, ai_used=False, ticket_reference="", response_status="ok"):
    """Store one chat message. Returns the new document id as a string, or None if not stored."""
    db = _available_db()
    if db is None:
        return None
    document = {
        "conversation_id": conversation_id,
        "session_ref": session_ref,
        "user_id": user_id,
        "role": role,
        "text": _clip(text),
        "kind": kind,
        "error_codes": list(error_codes or []),
        "faq_ids": list(faq_ids or []),
        "ai_used": bool(ai_used),
        "resulted_in_ticket": bool(ticket_reference),
        "ticket_reference": ticket_reference,
        "response_status": response_status,
        "created_at": datetime.now(UTC),
    }
    try:
        result = db[CHAT_COLLECTION].insert_one(document)
        return str(result.inserted_id)
    except Exception as exc:  # pymongo errors, network failures, auth errors
        _record_failure("chat log write", exc)
        return None


def save_feedback(conversation_id, rating, *, message_id="", comment="", session_ref=""):
    """Store feedback on an assistant reply. Returns True only if the write succeeded."""
    db = _available_db()
    if db is None:
        return False
    document = {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "rating": rating,
        "comment": _clip(comment, 500),
        "session_ref": session_ref,
        "created_at": datetime.now(UTC),
    }
    try:
        db[FEEDBACK_COLLECTION].insert_one(document)
        return True
    except Exception as exc:
        _record_failure("feedback write", exc)
        return False


def status():
    """'ok', 'unavailable' or 'not_configured' — used by the readiness endpoint."""
    if not is_configured():
        return "not_configured"
    db = get_db()
    try:
        if _override_db is None:
            db.client.admin.command("ping")
        return "ok"
    except Exception as exc:
        _record_failure("ping", exc)
        return "unavailable"


def ensure_indexes():
    db = get_db()
    if db is None:
        return False
    try:
        db[CHAT_COLLECTION].create_index([("conversation_id", 1), ("created_at", 1)])
        db[FEEDBACK_COLLECTION].create_index([("conversation_id", 1)])
        return True
    except Exception as exc:
        _record_failure("index creation", exc)
        return False

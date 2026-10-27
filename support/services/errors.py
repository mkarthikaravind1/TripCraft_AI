"""
Central error-code registry.

The single source of truth for every error code TripCraft AI can show. Used by
the custom error pages, the FAQ/help centre and the support assistant.
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ErrorCode:
    code: str
    http_status: int
    title: str
    meaning: str
    causes: tuple
    user_action: str
    troubleshooting: tuple
    where: str  # where this code is produced in TripCraft AI
    keywords: tuple = field(default_factory=tuple)


TRIPCRAFT_AI_UNAVAILABLE = "TRIPCRAFT_001"

REGISTRY = {
    "400": ErrorCode(
        code="400", http_status=400, title="Bad Request",
        meaning="The server could not process the request because something in it was invalid or malformed.",
        causes=("A form or chat message was sent with missing or invalid data.",
                "A request body was not valid JSON.",
                "The request was larger than the allowed size."),
        user_action="Check the information you entered and try again.",
        troubleshooting=("Reload the page and resubmit.", "Make sure dates, budget and traveller numbers are valid.",
                         "Keep chat messages under 1,000 characters."),
        where="Returned by the dashboard, chat and ticket endpoints when they receive invalid data.",
        keywords=("bad request", "invalid request", "malformed"),
    ),
    "401": ErrorCode(
        code="401", http_status=401, title="Unauthorized",
        meaning="You need to be logged in to view this page.",
        causes=("You opened a support ticket that belongs to an account while logged out.",
                "Your session expired."),
        user_action="Log in to the account that owns the resource, then try again.",
        troubleshooting=("Use the Log in link in the navigation bar.", "If you have no account, plan trips without one — sign-up is optional."),
        where="Returned when a signed-in user's support ticket is opened without logging in.",
        keywords=("unauthorized", "unauthorised", "not logged in", "login required", "authentication"),
    ),
    "403": ErrorCode(
        code="403", http_status=403, title="Forbidden",
        meaning="The request was understood, but you are not allowed to perform it.",
        causes=("You tried to open a support ticket that belongs to a different account.",
                "The security (CSRF) check failed, often because the page was open for a long time or cookies are blocked."),
        user_action="Reload the page and try again. Make sure cookies are enabled for this site.",
        troubleshooting=("Refresh the page to get a new security token.", "Log in with the account that owns the resource."),
        where="Returned for another account's ticket and for failed CSRF checks.",
        keywords=("forbidden", "permission", "csrf", "not allowed", "access denied"),
    ),
    "404": ErrorCode(
        code="404", http_status=404, title="Not Found",
        meaning="The page or resource you asked for does not exist, or you do not have access to it.",
        causes=("The web address was typed incorrectly or the link is out of date.",
                "The trip was deleted, or it was created in a different browser or account.",
                "The trip or ticket belongs to someone else (TripCraft hides other people's data)."),
        user_action="Check the address, or go to My trips or the homepage.",
        troubleshooting=("Open My trips to see trips saved in this browser or account.",
                         "Log in if you saved the trip to an account."),
        where="Returned for unknown URLs and for trips or tickets you do not own.",
        keywords=("not found", "page not found", "missing page", "broken link"),
    ),
    "429": ErrorCode(
        code="429", http_status=429, title="Too Many Requests",
        meaning="You sent too many requests in a short time, so TripCraft is pausing them briefly.",
        causes=("Generating many itineraries in a row.", "Sending many chat messages very quickly."),
        user_action="Wait about a minute, then try again.",
        troubleshooting=("AI itinerary generation is limited to a few requests every 10 minutes per visitor.",
                         "The assistant accepts around 20 messages per minute."),
        where="Returned by itinerary generation, regeneration and the assistant when rate limits are exceeded.",
        keywords=("too many requests", "rate limit", "rate limited", "slow down"),
    ),
    "500": ErrorCode(
        code="500", http_status=500, title="Internal Server Error",
        meaning="Something unexpected went wrong on TripCraft's side. It is not caused by anything you did.",
        causes=("An unexpected problem in the application.",),
        user_action="Try again in a moment. If it keeps happening, create a support ticket describing what you were doing.",
        troubleshooting=("Reload the page.", "Go back to the homepage and retry the action.",
                         "Create a support ticket so the team can investigate."),
        where="Shown by the custom error page for any unexpected server error. Technical details are never shown.",
        keywords=("internal server error", "server error", "something went wrong"),
    ),
    "503": ErrorCode(
        code="503", http_status=503, title="Service Unavailable",
        meaning="A service TripCraft depends on is temporarily unavailable.",
        causes=("The database is temporarily unreachable.",
                "The site is restarting or under maintenance (on free hosting it may be waking up)."),
        user_action="Wait a minute and try again.",
        troubleshooting=("Reload after 30–60 seconds.", "Check /health/ready/ — it reports whether the database is reachable."),
        where="Returned by the readiness check and by support features when the database cannot be reached.",
        keywords=("service unavailable", "maintenance", "site is down", "website is down"),
    ),
    TRIPCRAFT_AI_UNAVAILABLE: ErrorCode(
        code=TRIPCRAFT_AI_UNAVAILABLE, http_status=200, title="Live AI itinerary generation unavailable",
        meaning="TripCraft could not get a usable itinerary from the AI service, so it created a clearly labelled "
                "sample itinerary from local templates instead.",
        causes=("No Gemini API key is configured on the server.",
                "The AI service timed out, was rate-limited or returned an error.",
                "The AI response could not be validated (for example, malformed JSON)."),
        user_action="Your sample plan and budget tools still work. Use “Try live AI again” on the trip dashboard to retry.",
        troubleshooting=("Wait a minute and retry — temporary AI rate limits usually clear quickly.",
                         "If it keeps happening, create a support ticket and include the code TRIPCRAFT_001."),
        where="Shown on the trip dashboard whenever a sample itinerary is used instead of live AI.",
        keywords=("itinerary generation fails", "itinerary generation failed", "ai unavailable", "sample itinerary",
                  "generation fails", "generation failed", "ai failed", "not ai generated", "fallback"),
    ),
}

REQUIRED_CODES = ("400", "401", "403", "404", "429", "500", "503", TRIPCRAFT_AI_UNAVAILABLE)

_CODE_RE = re.compile(r"\b(?:error\s*|code\s*|status\s*)?(400|401|403|404|429|500|503)\b", re.IGNORECASE)
_TC_RE = re.compile(r"\bTRIP\s*CRAFT[\s_-]*0*1\b|\bTC[_-]?001\b", re.IGNORECASE)
_TICKET_RE = re.compile(r"\bTC-[A-Z0-9]{8}\b")


def get(code):
    return REGISTRY.get(str(code).upper())


def all_codes():
    return [REGISTRY[c] for c in REQUIRED_CODES]


def detect(text):
    """Return the error codes mentioned in a message (explicitly or by well-known phrase)."""
    if not text:
        return []
    cleaned = _TICKET_RE.sub(" ", text)  # don't mistake ticket references for codes
    found = []
    if _TC_RE.search(cleaned):
        found.append(TRIPCRAFT_AI_UNAVAILABLE)
    for match in _CODE_RE.finditer(cleaned):
        # Avoid matching amounts like "500 rupees" unless the word "error"/"code" or the title is near.
        code = match.group(1)
        window = cleaned[max(0, match.start() - 25): match.end() + 25].lower()
        entry = REGISTRY[code]
        if any(w in window for w in ("error", "code", "status", "http", "page")) or entry.title.lower() in cleaned.lower():
            if code not in found:
                found.append(code)
    lowered = cleaned.lower()
    for entry in REGISTRY.values():
        if entry.code not in found and any(re.search(rf"\b{re.escape(k)}\b", lowered) for k in entry.keywords):
            found.append(entry.code)
    return found[:3]


def as_text(entry):
    """Plain-text explanation used as AI context and as the deterministic fallback answer."""
    label = entry.code if not entry.code.isdigit() else f"Error {entry.code}"
    return (
        f"{label} — {entry.title}. {entry.meaning} "
        f"Common causes: {' '.join(entry.causes)} "
        f"What to do: {entry.user_action} "
        f"Troubleshooting: {' '.join(entry.troubleshooting)}"
    )

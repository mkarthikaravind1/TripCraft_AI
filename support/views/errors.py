"""Custom error handlers. Every page uses the central error registry and includes the assistant."""

import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from support.services import errors

logger = logging.getLogger(__name__)

SAFE_500_HTML = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, "
    "initial-scale=1'><title>Something went wrong · TripCraft AI</title></head><body style='font-family:system-ui,"
    "sans-serif;background:#faf7f2;color:#1e2421;display:grid;place-items:center;min-height:100vh;margin:0;padding:16px'>"
    "<main style='max-width:440px;text-align:center'><h1>Something went wrong on our side.</h1><p>Error 500 — "
    "please try again in a moment.</p><p><a href='/' style='color:#1f4d3f;font-weight:600'>Back to TripCraft AI</a>"
    "</p></main></body></html>"
)


def wants_json(request):
    return (
        request.content_type == "application/json"
        or "application/json" in request.headers.get("Accept", "")
        or request.path.startswith(("/support/chat/", "/health/"))
    )


def error_response(request, code, message=None, extra=None):
    """Render an error (HTML page or JSON for API callers) with the right HTTP status."""
    entry = errors.get(code)
    status = entry.http_status if entry.http_status >= 400 else 503
    if wants_json(request):
        payload = {"ok": False, "code": entry.code, "error": message or entry.meaning}
        payload.update(extra or {})
        return JsonResponse(payload, status=status)
    template = f"{entry.code}.html" if entry.code in {"400", "401", "403", "404", "429", "500", "503"} else "errors/error.html"
    return render(request, template, {"error": entry, "message": message, "request_id": getattr(request, "request_id", "")},
                  status=status)


def bad_request(request, exception=None):
    return error_response(request, "400")


def permission_denied(request, exception=None):
    return error_response(request, "403")


def page_not_found(request, exception=None):
    return error_response(request, "404")


def csrf_failure(request, reason=""):
    return error_response(request, "403", message="The security check for this form failed. Please reload the page and try again.")


def server_error(request):
    """Safe 500 page: no traceback or configuration details, and a plain fallback if rendering fails."""
    try:
        if wants_json(request):
            return JsonResponse({"ok": False, "code": "500", "error": errors.get("500").meaning}, status=500)
        return render(request, "500.html", {"error": errors.get("500"), "request_id": getattr(request, "request_id", "")},
                      status=500)
    except Exception:  # the error page itself must never fail
        logger.exception("Rendering the 500 page failed")
        return HttpResponse(SAFE_500_HTML, status=500)

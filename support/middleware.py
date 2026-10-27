import logging
import re
import time
import uuid

logger = logging.getLogger("tripcraft.requests")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class RequestLoggingMiddleware:
    """Log method, path, status, duration and a request id for every request.

    Query strings and bodies are never logged (they may contain personal data).
    The request id is returned in the X-Request-ID response header so a user
    can quote it in a support ticket.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request.request_id = incoming if REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex[:16]
        start = time.perf_counter()
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            response["X-Request-ID"] = request.request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            path = request.path[:200]
            level = logging.DEBUG if path.startswith("/static/") else (
                logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
            )
            logger.log(level, "%s %s %s %.1fms id=%s", request.method, path, status, duration_ms, request.request_id,
                       extra={"request_id": request.request_id, "status_code": status, "duration_ms": round(duration_ms, 1)})

"""Health endpoints. They never expose hostnames, credentials or stack traces."""

import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache

from planner.services.ai import get_provider
from support.services import mongo

logger = logging.getLogger(__name__)


@never_cache
def health(request):
    """Liveness: the application process is running and serving requests."""
    return JsonResponse({"status": "ok"})


@never_cache
def ready(request):
    """Readiness: the required SQL database is reachable. Optional services are reported, not required."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database = "ok"
    except Exception as exc:
        logger.error("Readiness check: database unavailable (%s)", type(exc).__name__)
        database = "unavailable"
    healthy = database == "ok"
    return JsonResponse(
        {
            "status": "ok" if healthy else "unavailable",
            "checks": {"database": database},
            "optional": {
                "mongodb": mongo.status(),
                "ai": "configured" if get_provider().configured else "not_configured",
            },
        },
        status=200 if healthy else 503,
    )

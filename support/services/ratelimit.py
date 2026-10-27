"""
Fixed-window rate limiting for expensive operations (AI calls), backed by
Django's cache. With the default local-memory cache the limit is per server
process — adequate for a single small Render instance; use a shared cache
(e.g. Redis) if the app is scaled out.
"""

import time

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    # Render's proxy appends the real client address to X-Forwarded-For.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded and settings.TRUST_X_FORWARDED_FOR:
        return forwarded.split(",")[0].strip()[:45]
    return request.META.get("REMOTE_ADDR", "unknown")[:45]


def hit(request, scope):
    """Count one request. Returns (allowed, retry_after_seconds)."""
    limit, window = settings.RATE_LIMITS[scope]
    now = int(time.time())
    bucket = now // window
    key = f"rl:{scope}:{client_ip(request)}:{bucket}"
    added = cache.add(key, 1, timeout=window + 1)
    count = 1 if added else cache.incr(key)
    if count > limit:
        return False, window - (now % window)
    return True, 0

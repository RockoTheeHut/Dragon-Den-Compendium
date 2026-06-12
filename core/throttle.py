import time

from django.conf import settings
from django.core.cache import cache


def _client_ip(request):
    if getattr(settings, "TRUST_PROXY_SSL_HEADER", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def rate_limit_exceeded(request, scope, limit, window_seconds):
    """Fixed-window counter per client IP; returns True once over the limit."""
    window = int(time.time() // window_seconds)
    key = f"throttle:{scope}:{_client_ip(request)}:{window}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=window_seconds * 2)
        count = 1
    return count > limit

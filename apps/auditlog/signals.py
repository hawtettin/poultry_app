from __future__ import annotations

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

def _client_ip(request) -> str:
    if not request:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""

@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    from .models import AccessLog
    ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:500]
    AccessLog.objects.create(
        actor=user,
        event="LOGIN",
        path=(request.path if request else ""),
        ip_address=_client_ip(request),
        user_agent=ua,
    )

@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    from .models import AccessLog
    ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:500]
    AccessLog.objects.create(
        actor=user if getattr(user, "is_authenticated", False) else None,
        event="LOGOUT",
        path=(request.path if request else ""),
        ip_address=_client_ip(request),
        user_agent=ua,
    )

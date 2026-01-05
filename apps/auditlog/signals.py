from __future__ import annotations

import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import OperationalError, ProgrammingError
from django.dispatch import receiver

logger = logging.getLogger(__name__)

def _client_ip(request) -> str:
    if not request:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""

def _write_access_log(*, user, event: str, request):
    from .models import AccessLog
    ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:500]
    try:
        AccessLog.objects.create(
            actor=user if getattr(user, "is_authenticated", False) else None,
            event=event,
            path=(request.path if request else ""),
            ip_address=_client_ip(request),
            user_agent=ua,
        )
    except (OperationalError, ProgrammingError):
        logger.warning("Nu am putut salva AccessLog (%s) - probabil lipsesc migrațiile.", event)
    except Exception:
        logger.exception("Eroare la salvarea AccessLog (%s)", event)


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    _write_access_log(user=user, event="LOGIN", request=request)

@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    _write_access_log(user=user, event="LOGOUT", request=request)

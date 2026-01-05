from __future__ import annotations

from django.forms.models import model_to_dict
from django.http import HttpRequest

from .models import AuditEvent

def _client_ip(request: HttpRequest | None) -> str:
    if not request:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""

def log_event(
    *,
    actor,
    action: str,
    instance,
    message: str = "",
    before: dict | None = None,
    after: dict | None = None,
    request: HttpRequest | None = None,
):
    model_label = f"{instance._meta.app_label}.{instance._meta.model_name}"
    ua = ""
    if request:
        ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:500]

    AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        model=model_label,
        object_id=str(getattr(instance, "pk", "")),
        message=message,
        before=before,
        after=after,
        path=(request.path if request else ""),
        method=(request.method if request else ""),
        ip_address=_client_ip(request),
        user_agent=ua,
    )

def snapshot(instance) -> dict:
    # model_to_dict e suficient: FK ca id, date/datetime/Decimal sunt ok in JSONField
    return model_to_dict(instance)

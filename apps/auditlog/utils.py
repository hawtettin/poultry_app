from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model, QuerySet
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


def to_jsonable(obj):
    """
    Converteste recursiv obiecte Python/Django in ceva JSON-serializabil.
    - Model -> pk (sau daca are 'name', folosim name pentru claritate)
    - QuerySet/set/tuple -> list
    - dict/list -> recursiv
    - date/datetime/Decimal -> lasam DjangoJSONEncoder sa le converteasca
    """
    if obj is None:
        return None

    # primitive
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # date/time/decimal (encoder le stie)
    if isinstance(obj, (date, datetime, Decimal)):
        return obj

    # Django Model
    if isinstance(obj, Model):
        # daca are name, e mai util in audit (ex: Group.name)
        if hasattr(obj, "name"):
            try:
                return str(getattr(obj, "name"))
            except Exception:
                pass
        # fallback: pk
        try:
            return str(obj.pk)
        except Exception:
            return str(obj)

    # QuerySet / iterabile
    if isinstance(obj, QuerySet):
        return [to_jsonable(x) for x in obj]

    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(x) for x in obj]

    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    # fallback: string
    return str(obj)


def json_safe(value):
    """
    Face un obiect JSON-safe (inclusiv Model / Group / User etc.).
    """
    value = to_jsonable(value)
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def snapshot(instance) -> dict:
    """
    Snapshot sigur pentru orice model, inclusiv User cu M2M.
    model_to_dict include m2m ca listă (uneori de obiecte) -> le normalizăm.
    """
    d = model_to_dict(instance)
    return json_safe(d)


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
        before=json_safe(before) if before is not None else None,
        after=json_safe(after) if after is not None else None,
        path=(request.path if request else ""),
        method=(request.method if request else ""),
        ip_address=_client_ip(request),
        user_agent=ua,
    )

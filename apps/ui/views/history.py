from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.auditlog.models import AuditEvent

from .utils import is_manager


@login_required
def history(request):
    # Employee: sees only own history; Manager/Admin: sees all.
    qs = AuditEvent.objects.select_related("actor").all()
    if not is_manager(request.user):
        qs = qs.filter(actor=request.user)

    qs = qs.order_by("-created_at", "-id")[:300]
    return render(request, "ui/history.html", {"events": qs, "is_manager": is_manager(request.user)})

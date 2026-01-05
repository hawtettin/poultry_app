from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.auditlog.utils import log_event, snapshot
from apps.health.models import MortalityEvent

from ..forms import MortalityEditForm
from .utils import can_modify_mortality


@login_required
def mortality_edit(request, pk: int):
    m = get_object_or_404(MortalityEvent.objects.select_related("flock", "created_by"), pk=pk)
    if not can_modify_mortality(request.user, m):
        messages.error(request, "Nu ai drepturi să editezi această înregistrare.")
        return redirect("ui:dashboard")

    before = snapshot(m)

    if request.method == "POST":
        form = MortalityEditForm(request.POST, instance=m)
        if form.is_valid():
            m2 = form.save()
            after = snapshot(m2)
            log_event(
                actor=request.user,
                action="UPDATE",
                instance=m2,
                message=f"UPDATE mortalitate #{m2.id}: {before.get('count')} -> {after.get('count')}",
                before=before,
                after=after,
                request=request,
            )
            messages.success(request, "Mortalitatea a fost actualizată.")
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva modificările. Verifică formularul.")
    else:
        form = MortalityEditForm(instance=m)

    return render(request, "ui/mortality_edit.html", {"form": form, "m": m})


@login_required
def mortality_delete(request, pk: int):
    m = get_object_or_404(MortalityEvent.objects.select_related("flock", "created_by"), pk=pk)
    if not can_modify_mortality(request.user, m):
        messages.error(request, "Nu ai drepturi să ștergi această înregistrare.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        before = snapshot(m)
        mid = m.id
        m.delete()

        # Log after delete (keep object_id and before snapshot)
        class Dummy:
            _meta = type("M", (), {"app_label": "health", "model_name": "mortalityevent"})()
            pk = mid

        log_event(
            actor=request.user,
            action="DELETE",
            instance=Dummy(),
            message=(
                f"DELETE mortalitate #{mid}: -{before.get('count')} (lot {before.get('flock')}) la {before.get('date')}"
            ),
            before=before,
            after=None,
            request=request,
        )
        messages.success(request, "Înregistrarea a fost ștearsă.")
        return redirect("ui:dashboard")

    return render(request, "ui/mortality_confirm_delete.html", {"m": m})

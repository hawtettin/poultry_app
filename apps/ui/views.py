from __future__ import annotations

from datetime import date as _date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import Flock
from apps.health.models import MortalityEvent
from apps.auditlog.models import AuditEvent, AccessLog
from apps.auditlog.utils import log_event, snapshot

from .forms import CreateSeriesForm, MortalityQuickAddForm, MortalityEditForm, EmployeeCreateForm

WEEKDAYS_RO = ["luni","marți","miercuri","joi","vineri","sâmbătă","duminică"]

def is_manager(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["ADMIN","MANAGER"]).exists()

def can_modify_mortality(user, m: MortalityEvent) -> bool:
    if not user.is_authenticated:
        return False
    if is_manager(user):
        return True
    return m.created_by_id == user.id

@login_required
def dashboard(request):
    if request.method == "POST" and request.POST.get("_action") == "add_mortality":
        f = MortalityQuickAddForm(request.POST)
        if f.is_valid():
            m = MortalityEvent.objects.create(
                flock=f.cleaned_data["flock"],
                date=f.cleaned_data["date"],
                count=f.cleaned_data["count"],
                reason=f.cleaned_data.get("reason",""),
                created_by=request.user,
            )
            log_event(actor=request.user, action="CREATE", instance=m,
                      message=f"CREATE mortalitate: -{m.count} (lot {m.flock_id}) la {m.date}",
                      after=snapshot(m), request=request)
            messages.success(request, "Mortalitatea a fost salvată.")
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva. Verifică datele.")
    else:
        f = MortalityQuickAddForm()

    flocks = (Flock.objects.select_related("season","house")
              .annotate(mortality_total=Coalesce(Sum("mortality_events__count"), 0))
              .order_by("-start_date","-id"))

    for x in flocks:
        x.current_count = max(int(x.initial_count) - int(x.mortality_total or 0), 0)
        x.mortality_pct = (100.0 * float(x.mortality_total or 0) / float(x.initial_count)) if x.initial_count else 0.0

    recent = (MortalityEvent.objects.select_related("flock","flock__season","flock__house","created_by")
              .order_by("-date","-id")[:40])
    for m in recent:
        m.can_modify = can_modify_mortality(request.user, m)

    today = timezone.localdate()
    return render(request, "ui/dashboard.html", {
        "flocks": flocks,
        "mortality_form": f,
        "recent_mortalities": recent,
        "today": today,
        "today_weekday": WEEKDAYS_RO[today.weekday()],
    })

@login_required
def create_series(request):
    if not is_manager(request.user):
        messages.error(request, "Doar MANAGER/ADMIN pot crea serii.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        form = CreateSeriesForm(request.POST)
        if form.is_valid():
            season, flock = form.save()
            log_event(actor=request.user, action="CREATE", instance=season, message=f"CREATE sezon: {season.name}", after=snapshot(season), request=request)
            log_event(actor=request.user, action="CREATE", instance=flock, message=f"CREATE lot: {season.name} / {flock.house.name} / {flock.initial_count}", after=snapshot(flock), request=request)
            messages.success(request, f"Serie creată: {season.name}")
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva seria.")
    else:
        form = CreateSeriesForm()
    return render(request, "ui/create_series.html", {"form": form})

@login_required
def mortality_edit(request, pk: int):
    m = get_object_or_404(MortalityEvent, pk=pk)
    if not can_modify_mortality(request.user, m):
        messages.error(request, "Nu ai drepturi să editezi.")
        return redirect("ui:dashboard")

    before = snapshot(m)
    if request.method == "POST":
        form = MortalityEditForm(request.POST, instance=m)
        if form.is_valid():
            m2 = form.save()
            after = snapshot(m2)
            log_event(actor=request.user, action="UPDATE", instance=m2,
                      message=f"UPDATE mortalitate #{m2.id}: {before.get('count')} -> {after.get('count')}",
                      before=before, after=after, request=request)
            messages.success(request, "Actualizat.")
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva.")
    else:
        form = MortalityEditForm(instance=m)
    return render(request, "ui/mortality_edit.html", {"form": form, "m": m})

@login_required
def mortality_delete(request, pk: int):
    m = get_object_or_404(MortalityEvent, pk=pk)
    if not can_modify_mortality(request.user, m):
        messages.error(request, "Nu ai drepturi să ștergi.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        before = snapshot(m)
        mid = m.id
        m.delete()

        class Dummy:
            _meta = type("M", (), {"app_label": "health", "model_name": "mortalityevent"})()
            pk = mid

        log_event(actor=request.user, action="DELETE", instance=Dummy(),
                  message=f"DELETE mortalitate #{mid}: -{before.get('count')} la {before.get('date')}",
                  before=before, after=None, request=request)
        messages.success(request, "Șters.")
        return redirect("ui:dashboard")

    return render(request, "ui/mortality_confirm_delete.html", {"m": m})

@login_required
def users_list(request):
    if not is_manager(request.user):
        messages.error(request, "Doar MANAGER/ADMIN pot vedea angajații.")
        return redirect("ui:dashboard")

    employees = User.objects.filter(groups__name="EMPLOYEE").order_by("username").distinct()
    return render(request, "ui/users_list.html", {"employees": employees})


@login_required
def user_create(request):
    if not is_manager(request.user):
        messages.error(request, "Doar MANAGER/ADMIN pot crea angajați.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    u = form.save_employee()
            except IntegrityError:
                form.add_error("username", "Acest username există deja. Alege altul (ex: vasilica1).")
                messages.error(request, "Username duplicat.")
                return render(request, "ui/user_create.html", {"form": form})

            log_event(
                actor=request.user,
                action="CREATE",
                instance=u,
                message=f"CREATE angajat: {u.username}",
                after=snapshot(u),
                request=request,
            )
            messages.success(request, f"Angajat creat: {u.username}")
            return redirect("ui:users_list")
        messages.error(request, "Nu am putut crea angajatul.")
    else:
        form = EmployeeCreateForm()

    return render(request, "ui/user_create.html", {"form": form})


@login_required
def history(request):
    qs = AuditEvent.objects.select_related("actor").all()
    if not is_manager(request.user):
        qs = qs.filter(actor=request.user)

    user_id = request.GET.get("user","")
    day = request.GET.get("day","")

    if is_manager(request.user) and user_id.isdigit():
        qs = qs.filter(actor_id=int(user_id))

    if day:
        try:
            y,m,d = [int(x) for x in day.split("-")]
            qs = qs.filter(created_at__date=_date(y,m,d))
        except Exception:
            pass

    qs = qs.order_by("-created_at","-id")[:500]
    employees = User.objects.filter(groups__name="EMPLOYEE").order_by("username").distinct() if is_manager(request.user) else []
    return render(request, "ui/history.html", {"events": qs, "employees": employees, "selected_user": user_id, "selected_day": day, "is_manager": is_manager(request.user)})

@login_required
def access_history(request):
    qs = AccessLog.objects.select_related("actor").all()
    if not is_manager(request.user):
        qs = qs.filter(actor=request.user)

    user_id = request.GET.get("user","")
    day = request.GET.get("day","")

    if is_manager(request.user) and user_id.isdigit():
        qs = qs.filter(actor_id=int(user_id))

    if day:
        try:
            y,m,d = [int(x) for x in day.split("-")]
            qs = qs.filter(created_at__date=_date(y,m,d))
        except Exception:
            pass

    qs = qs.order_by("-created_at","-id")[:500]
    employees = User.objects.filter(groups__name="EMPLOYEE").order_by("username").distinct() if is_manager(request.user) else []
    return render(request, "ui/access.html", {"events": qs, "employees": employees, "selected_user": user_id, "selected_day": day, "is_manager": is_manager(request.user)})

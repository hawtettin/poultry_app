# apply_manager_patch.py
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

def w(rel: str, content: str) -> None:
    p = BASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.replace("\r\n", "\n"), encoding="utf-8")

def ensure_installed_app(app_label: str) -> None:
    p = BASE / "config" / "settings.py"
    text = p.read_text(encoding="utf-8")

    if f'"{app_label}"' in text:
        return

    # Insert after apps.reports if possible
    lines = text.splitlines(True)
    inserted = False
    for i, line in enumerate(lines):
        if '"apps.reports"' in line:
            lines.insert(i + 1, f'    "{app_label}",\n')
            inserted = True
            break
    if not inserted:
        for i, line in enumerate(lines):
            if line.strip() == "]":
                lines.insert(i, f'    "{app_label}",\n')
                break

    text = "".join(lines)
    if "LOGIN_URL" not in text:
        text += "\n\n# UI auth\nLOGIN_URL = \"/login/\"\nLOGIN_REDIRECT_URL = \"/\"\nLOGOUT_REDIRECT_URL = \"/login/\"\n"
    p.write_text(text, encoding="utf-8")

def ensure_ui_url_include() -> None:
    p = BASE / "config" / "urls.py"
    text = p.read_text(encoding="utf-8")

    if 'include("apps.ui.urls")' in text:
        return

    # ensure include imported
    if "from django.urls import" in text:
        m = re.search(r"from django\.urls import ([^\n]+)", text)
        if m and "include" not in m.group(1):
            text = text.replace(m.group(0), m.group(0).replace("import ", "import include, "))
    else:
        # fallback: add include import
        text = "from django.urls import include\n" + text

    # insert path("", include(...)) at top of urlpatterns
    lines = text.splitlines(True)
    for i, line in enumerate(lines):
        if line.strip() == "urlpatterns = [":
            lines.insert(i + 1, '    path("", include("apps.ui.urls")),\n')
            break

    p.write_text("".join(lines), encoding="utf-8")

def run_manage(*args: str) -> int:
    return subprocess.call([sys.executable, "manage.py", *args], cwd=str(BASE))

def main() -> None:
    # -------------------------
    # Fix roles: ADMIN/MANAGER/EMPLOYEE only
    # -------------------------
    w("apps/accounts/management/commands/init_roles.py", """\
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

ROLE_NAMES = ["ADMIN", "MANAGER", "EMPLOYEE"]

class Command(BaseCommand):
    help = "Creeaza grupurile de roluri: ADMIN, MANAGER, EMPLOYEE"

    def handle(self, *args, **options):
        for name in ROLE_NAMES:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("OK: Grupurile au fost create/exista deja."))
""")

    # -------------------------
    # AUDITLOG: AuditEvent + AccessLog + signals + utils (json-safe)
    # -------------------------
    w("apps/auditlog/__init__.py", "")
    w("apps/auditlog/apps.py", """\
from django.apps import AppConfig

class AuditlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auditlog"

    def ready(self):
        from . import signals  # noqa
""")
    w("apps/auditlog/models.py", """\
from __future__ import annotations

from django.conf import settings
from django.db import models

class AuditEvent(models.Model):
    ACTIONS = [("CREATE","CREATE"),("UPDATE","UPDATE"),("DELETE","DELETE")]
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    action = models.CharField(max_length=10, choices=ACTIONS)
    model = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    message = models.CharField(max_length=300, blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    path = models.CharField(max_length=300, blank=True, default="")
    method = models.CharField(max_length=10, blank=True, default="")
    ip_address = models.CharField(max_length=45, blank=True, default="")
    user_agent = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["model", "created_at"]),
        ]

class AccessLog(models.Model):
    EVENTS = [("LOGIN","LOGIN"),("LOGOUT","LOGOUT")]
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="access_logs")
    event = models.CharField(max_length=10, choices=EVENTS)
    path = models.CharField(max_length=300, blank=True, default="")
    ip_address = models.CharField(max_length=45, blank=True, default="")
    user_agent = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["event", "created_at"]),
        ]
""")
    w("apps/auditlog/signals.py", """\
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
""")
    w("apps/auditlog/utils.py", """\
from __future__ import annotations

import json
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest

from .models import AuditEvent

def _client_ip(request: HttpRequest | None) -> str:
    if not request:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""

def json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))

def snapshot(instance) -> dict:
    return json_safe(model_to_dict(instance))

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
""")
    w("apps/auditlog/admin.py", """\
from django.contrib import admin
from .models import AuditEvent, AccessLog

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "actor", "action", "model", "object_id", "message")
    list_filter = ("action", "model", "created_at")
    search_fields = ("message", "model", "object_id", "actor__username")

@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "actor", "event", "path", "ip_address")
    list_filter = ("event", "created_at")
    search_fields = ("actor__username", "path", "ip_address")
""")
    w("apps/auditlog/migrations/__init__.py", "")

    # -------------------------
    # UI templatetags fix (NO junk in __init__.py)
    # -------------------------
    w("apps/ui/templatetags/__init__.py", "")
    w("apps/ui/templatetags/ui_extras.py", """\
from django import template

register = template.Library()

@register.filter
def in_groups(user, csv_names: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    names = [x.strip() for x in (csv_names or "").split(",") if x.strip()]
    if not names:
        return False
    return user.groups.filter(name__in=names).exists()
""")

    # -------------------------
    # UI forms/views/urls
    # -------------------------
    w("apps/ui/forms.py", """\
from __future__ import annotations

from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User, Group
from django.db.models import Sum

from apps.core.models import House, Season, Flock
from apps.health.models import MortalityEvent

class BootstrapAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-control")
            f.widget.attrs.setdefault("autocomplete", "off")

class CreateSeriesForm(forms.Form):
    series_name = forms.CharField(label="Serie (nume)", max_length=80,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: Seria 1"}))
    year = forms.IntegerField(label="An", initial=lambda: timezone.now().year,
        widget=forms.NumberInput(attrs={"class": "form-control"}))
    start_date = forms.DateField(label="Data populare", initial=timezone.localdate,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))

    house_existing = forms.ModelChoiceField(label="Hală (existentă)", queryset=House.objects.none(),
        required=False, widget=forms.Select(attrs={"class": "form-select"}))
    house_name = forms.CharField(label="Hală nouă", max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: Hala 1"}))

    initial_count = forms.IntegerField(label="Număr pui (inițial)", min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["house_existing"].queryset = House.objects.all().order_by("name")

    def clean(self):
        cleaned = super().clean()
        house_existing = cleaned.get("house_existing")
        house_name = (cleaned.get("house_name") or "").strip()
        if not house_existing and not house_name:
            raise ValidationError("Alege o hală existentă sau introdu o hală nouă.")

        series_name = (cleaned.get("series_name") or "").strip()
        year = cleaned.get("year")
        if series_name and year:
            season_name = f"{series_name} {int(year)}"
            if Season.objects.filter(name=season_name).exists():
                raise ValidationError(f"Sezonul '{season_name}' există deja.")
        return cleaned

    def save(self):
        series_name = self.cleaned_data["series_name"].strip()
        year = int(self.cleaned_data["year"])
        start_date = self.cleaned_data["start_date"]
        initial_count = int(self.cleaned_data["initial_count"])

        house = self.cleaned_data.get("house_existing")
        house_name = (self.cleaned_data.get("house_name") or "").strip()
        if house_name:
            house, _ = House.objects.get_or_create(name=house_name)

        season = Season.objects.create(name=f"{series_name} {year}", start_date=start_date, is_active=True)
        flock = Flock.objects.create(season=season, house=house, start_date=start_date, initial_count=initial_count)
        return season, flock

class MortalityQuickAddForm(forms.Form):
    date = forms.DateField(label="Data", initial=timezone.localdate,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    flock = forms.ModelChoiceField(label="Lot (serie/hală)", queryset=Flock.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}))
    count = forms.IntegerField(label="Mortalitate (nr)", min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "autofocus": "autofocus", "inputmode": "numeric"}))
    reason = forms.CharField(label="Motiv (opțional)", required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: stres termic"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["flock"].queryset = Flock.objects.select_related("season","house").all().order_by("-start_date","-id")

    def clean(self):
        cleaned = super().clean()
        flock = cleaned.get("flock")
        count = cleaned.get("count")
        if flock and count:
            total = MortalityEvent.objects.filter(flock=flock).aggregate(s=Sum("count"))["s"] or 0
            current = flock.initial_count - int(total)
            if int(count) > max(current, 0):
                raise ValidationError(f"Nu poți scădea {count}. În lot mai sunt ~{max(current,0)} capete.")
        return cleaned

class MortalityEditForm(forms.ModelForm):
    class Meta:
        model = MortalityEvent
        fields = ["date", "flock", "count", "reason"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "flock": forms.Select(attrs={"class": "form-select"}),
            "count": forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
        }

class EmployeeCreateForm(UserCreationForm):
    first_name = forms.CharField(label="Prenume", required=False, widget=forms.TextInput(attrs={"class":"form-control"}))
    last_name = forms.CharField(label="Nume", required=False, widget=forms.TextInput(attrs={"class":"form-control"}))
    email = forms.EmailField(label="Email", required=False, widget=forms.EmailInput(attrs={"class":"form-control"}))

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username","first_name","last_name","email","password1","password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-control")

    def save_employee(self) -> User:
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("first_name","") or ""
        user.last_name = self.cleaned_data.get("last_name","") or ""
        user.email = self.cleaned_data.get("email","") or ""
        user.is_active = True
        user.is_staff = False
        user.save()

        g, _ = Group.objects.get_or_create(name="EMPLOYEE")
        user.groups.add(g)
        return user
""")

    w("apps/ui/views.py", """\
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
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
            u = form.save_employee()
            log_event(actor=request.user, action="CREATE", instance=u, message=f"CREATE angajat: {u.username}", after=snapshot(u), request=request)
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
            qs = qs.filter(created_at__date=timezone.datetime(y,m,d).date())
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
            qs = qs.filter(created_at__date=timezone.datetime(y,m,d).date())
        except Exception:
            pass

    qs = qs.order_by("-created_at","-id")[:500]
    employees = User.objects.filter(groups__name="EMPLOYEE").order_by("username").distinct() if is_manager(request.user) else []
    return render(request, "ui/access.html", {"events": qs, "employees": employees, "selected_user": user_id, "selected_day": day, "is_manager": is_manager(request.user)})
""")

    w("apps/ui/urls.py", """\
from __future__ import annotations

from django.urls import path
from django.contrib.auth import views as auth_views

from .forms import BootstrapAuthenticationForm
from . import views

app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("series/new/", views.create_series, name="create_series"),
    path("mortality/<int:pk>/edit/", views.mortality_edit, name="mortality_edit"),
    path("mortality/<int:pk>/delete/", views.mortality_delete, name="mortality_delete"),

    path("users/", views.users_list, name="users_list"),
    path("users/new/", views.user_create, name="user_create"),

    path("history/", views.history, name="history"),
    path("access/", views.access_history, name="access_history"),

    path("login/", auth_views.LoginView.as_view(
        template_name="ui/login.html",
        authentication_form=BootstrapAuthenticationForm,
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
""")

    # -------------------------
    # Templates (rewrite as UTF-8 to fix UnicodeDecodeError)
    # -------------------------
    w("apps/ui/templates/ui/base.html", """\
{% load ui_extras %}
<!doctype html>
<html lang="ro">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Ferma Avicolă{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
      <div class="container-fluid">
        <a class="navbar-brand" href="{% url 'ui:dashboard' %}">Ferma Avicolă</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbars">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbars">
          <ul class="navbar-nav me-auto mb-2 mb-lg-0">
            <li class="nav-item"><a class="nav-link" href="{% url 'ui:dashboard' %}">Dashboard</a></li>

            {% if user.is_authenticated and (user.is_superuser or user|in_groups:"ADMIN,MANAGER") %}
              <li class="nav-item"><a class="nav-link" href="{% url 'ui:create_series' %}">Serie nouă</a></li>
              <li class="nav-item"><a class="nav-link" href="{% url 'ui:users_list' %}">Angajați</a></li>
              <li class="nav-item"><a class="nav-link" href="{% url 'ui:access_history' %}">Accesări</a></li>
            {% endif %}

            <li class="nav-item"><a class="nav-link" href="{% url 'ui:history' %}">Istoric</a></li>

            {% if user.is_authenticated and (user.is_superuser or user|in_groups:"ADMIN") %}
              <li class="nav-item"><a class="nav-link" href="/admin/">Admin</a></li>
            {% endif %}
          </ul>

          <ul class="navbar-nav ms-auto">
            {% if user.is_authenticated %}
              <li class="nav-item"><span class="navbar-text me-2">Salut, {{ user.username }}</span></li>
              <li class="nav-item"><a class="nav-link" href="{% url 'ui:logout' %}">Logout</a></li>
            {% else %}
              <li class="nav-item"><a class="nav-link" href="{% url 'ui:login' %}">Login</a></li>
            {% endif %}
          </ul>
        </div>
      </div>
    </nav>

    <div class="container py-3">
      {% if messages %}
        {% for message in messages %}
          <div class="alert alert-{{ message.tags }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
          </div>
        {% endfor %}
      {% endif %}
      {% block content %}{% endblock %}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    {% block scripts %}{% endblock %}
  </body>
</html>
""")

    # Keep your existing dashboard/create_series/login templates if already present.
    # But we overwrite users/history/access templates to ensure UTF-8.
    w("apps/ui/templates/ui/users_list.html", """\
{% extends "ui/base.html" %}
{% block title %}Angajați{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="mb-0">Angajați</h2>
  <a class="btn btn-primary" href="{% url 'ui:user_create' %}">+ Creează angajat</a>
</div>

{% if employees %}
<div class="table-responsive">
  <table class="table table-striped align-middle">
    <thead>
      <tr>
        <th>Username</th>
        <th>Nume</th>
        <th>Activ</th>
        <th>Ultimul login</th>
        <th class="text-end">Acțiuni</th>
      </tr>
    </thead>
    <tbody>
      {% for u in employees %}
      <tr>
        <td class="fw-semibold">{{ u.username }}</td>
        <td>{{ u.first_name }} {{ u.last_name }}</td>
        <td>{% if u.is_active %}Da{% else %}Nu{% endif %}</td>
        <td>{% if u.last_login %}{{ u.last_login }}{% else %}-{% endif %}</td>
        <td class="text-end">
          <a class="btn btn-sm btn-outline-secondary" href="{% url 'ui:history' %}?user={{ u.id }}">Istoric schimbări</a>
          <a class="btn btn-sm btn-outline-secondary" href="{% url 'ui:access_history' %}?user={{ u.id }}">Accesări</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% else %}
  <div class="alert alert-info">Nu există angajați încă.</div>
{% endif %}
{% endblock %}
""")

    w("apps/ui/templates/ui/user_create.html", """\
{% extends "ui/base.html" %}
{% block title %}Creează angajat{% endblock %}

{% block content %}
<h2 class="mb-3">Creează cont de angajat</h2>

<div class="card">
  <div class="card-body">
    <form method="post" novalidate>
      {% csrf_token %}
      {{ form.non_field_errors }}

      <div class="row g-3">
        <div class="col-md-4">
          <label class="form-label">Username</label>
          {{ form.username }}
          {{ form.username.errors }}
        </div>
        <div class="col-md-4">
          <label class="form-label">Prenume</label>
          {{ form.first_name }}
          {{ form.first_name.errors }}
        </div>
        <div class="col-md-4">
          <label class="form-label">Nume</label>
          {{ form.last_name }}
          {{ form.last_name.errors }}
        </div>

        <div class="col-md-6">
          <label class="form-label">Email</label>
          {{ form.email }}
          {{ form.email.errors }}
        </div>

        <div class="col-md-6"></div>

        <div class="col-md-6">
          <label class="form-label">Parolă</label>
          {{ form.password1 }}
          {{ form.password1.errors }}
        </div>
        <div class="col-md-6">
          <label class="form-label">Parolă (confirmare)</label>
          {{ form.password2 }}
          {{ form.password2.errors }}
        </div>
      </div>

      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Creează</button>
        <a class="btn btn-outline-secondary" href="{% url 'ui:users_list' %}">Înapoi</a>
      </div>

      <div class="text-muted small mt-3">
        Contul creat intră automat în grupul <code>EMPLOYEE</code>.
      </div>
    </form>
  </div>
</div>
{% endblock %}
""")

    w("apps/ui/templates/ui/history.html", """\
{% extends "ui/base.html" %}
{% block title %}Istoric schimbări{% endblock %}

{% block content %}
<h2 class="mb-3">Istoric schimbări</h2>

{% if is_manager %}
<div class="card mb-3">
  <div class="card-body">
    <form method="get" class="row g-2 align-items-end">
      <div class="col-md-4">
        <label class="form-label">Angajat</label>
        <select class="form-select" name="user">
          <option value="">(toți)</option>
          {% for u in employees %}
            <option value="{{ u.id }}" {% if selected_user == u.id|stringformat:"s" %}selected{% endif %}>
              {{ u.username }}
            </option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-3">
        <label class="form-label">Zi</label>
        <input class="form-control" type="date" name="day" value="{{ selected_day }}">
      </div>
      <div class="col-md-5 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Filtrează</button>
        <a class="btn btn-outline-secondary" href="{% url 'ui:history' %}">Reset</a>
      </div>
    </form>
  </div>
</div>
{% endif %}

<div class="table-responsive">
  <table class="table table-striped align-middle">
    <thead>
      <tr>
        <th>Data/ora</th>
        <th>Utilizator</th>
        <th>Acțiune</th>
        <th>Entitate</th>
        <th>Detalii</th>
      </tr>
    </thead>
    <tbody>
      {% for e in events %}
        <tr>
          <td>{{ e.created_at }}</td>
          <td>{% if e.actor %}{{ e.actor.username }}{% else %}-{% endif %}</td>
          <td><span class="badge text-bg-secondary">{{ e.action }}</span></td>
          <td><code>{{ e.model }}</code> #{{ e.object_id }}</td>
          <td>{{ e.message }}</td>
        </tr>
      {% empty %}
        <tr><td colspan="5" class="text-muted">Nu există evenimente.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
""")

    w("apps/ui/templates/ui/access.html", """\
{% extends "ui/base.html" %}
{% block title %}Accesări{% endblock %}

{% block content %}
<h2 class="mb-3">Accesări (LOGIN/LOGOUT)</h2>

{% if is_manager %}
<div class="card mb-3">
  <div class="card-body">
    <form method="get" class="row g-2 align-items-end">
      <div class="col-md-4">
        <label class="form-label">Angajat</label>
        <select class="form-select" name="user">
          <option value="">(toți)</option>
          {% for u in employees %}
            <option value="{{ u.id }}" {% if selected_user == u.id|stringformat:"s" %}selected{% endif %}>
              {{ u.username }}
            </option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-3">
        <label class="form-label">Zi</label>
        <input class="form-control" type="date" name="day" value="{{ selected_day }}">
      </div>
      <div class="col-md-5 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Filtrează</button>
        <a class="btn btn-outline-secondary" href="{% url 'ui:access_history' %}">Reset</a>
      </div>
    </form>
  </div>
</div>
{% endif %}

<div class="table-responsive">
  <table class="table table-striped align-middle">
    <thead>
      <tr>
        <th>Data/ora</th>
        <th>Utilizator</th>
        <th>Eveniment</th>
        <th>IP</th>
        <th>Path</th>
      </tr>
    </thead>
    <tbody>
      {% for e in events %}
        <tr>
          <td>{{ e.created_at }}</td>
          <td>{% if e.actor %}{{ e.actor.username }}{% else %}-{% endif %}</td>
          <td><span class="badge text-bg-secondary">{{ e.event }}</span></td>
          <td>{{ e.ip_address }}</td>
          <td><code>{{ e.path }}</code></td>
        </tr>
      {% empty %}
        <tr><td colspan="5" class="text-muted">Nu există accesări.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
""")

    # Make sure apps are installed and ui is included
    ensure_installed_app("apps.auditlog")
    ensure_installed_app("apps.ui")
    ensure_ui_url_include()

    print("✅ Patch files written (UTF-8). Now running migrations & role init...")

    # Run migrations and init roles
    rc = run_manage("makemigrations", "auditlog")
    if rc != 0:
        print("⚠️ makemigrations auditlog failed. Check output above.")
        sys.exit(rc)

    rc = run_manage("migrate")
    if rc != 0:
        print("⚠️ migrate failed. Check output above.")
        sys.exit(rc)

    rc = run_manage("init_roles")
    if rc != 0:
        print("⚠️ init_roles failed. Check output above.")
        sys.exit(rc)

    print("✅ Done. Start server with: python manage.py runserver")
    print("   UI:     http://127.0.0.1:8000/")
    print("   Users:  http://127.0.0.1:8000/users/ (manager/admin)")
    print("   Audit:  http://127.0.0.1:8000/history/")
    print("   Access: http://127.0.0.1:8000/access/")

if __name__ == "__main__":
    main()

# add_ui.py
# Adauga un UI prietenos (Django templates) peste proiectul existent.
# Rulare: python add_ui.py

from __future__ import annotations
from pathlib import Path

BASE = Path(__file__).resolve().parent

def write(rel: str, content: str) -> None:
    p = BASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.replace("\r\n", "\n"), encoding="utf-8")

def patch_settings() -> None:
    p = BASE / "config" / "settings.py"
    text = p.read_text(encoding="utf-8")

    # 1) adaugam apps.ui in INSTALLED_APPS (daca nu exista)
    if '"apps.ui"' not in text:
        lines = text.splitlines(True)
        inserted = False
        for i, line in enumerate(lines):
            if '"apps.reports"' in line:
                lines.insert(i + 1, '    "apps.ui",\n')
                inserted = True
                break
        if not inserted:
            # fallback: insertam chiar inainte de inchiderea listei
            for i, line in enumerate(lines):
                if line.strip() == "]":
                    lines.insert(i, '    "apps.ui",\n')
                    break
        text = "".join(lines)

    # 2) setari login/logout (daca nu exista deja)
    if "LOGIN_URL" not in text:
        text += "\n\n# UI auth\nLOGIN_URL = \"/login/\"\nLOGIN_REDIRECT_URL = \"/\"\nLOGOUT_REDIRECT_URL = \"/login/\"\n"

    p.write_text(text, encoding="utf-8")

def patch_urls() -> None:
    p = BASE / "config" / "urls.py"
    text = p.read_text(encoding="utf-8")

    if 'include("apps.ui.urls")' in text:
        return

    lines = text.splitlines(True)
    for i, line in enumerate(lines):
        if line.strip() == "urlpatterns = [":
            lines.insert(i + 1, '    path("", include("apps.ui.urls")),\n')
            break

    p.write_text("".join(lines), encoding="utf-8")

def main() -> None:
    # ---------- app skeleton ----------
    write("apps/ui/__init__.py", "")
    write("apps/ui/apps.py", """\
from django.apps import AppConfig

class UiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ui"
""")

    # ---------- forms ----------
    write("apps/ui/forms.py", """\
from __future__ import annotations

from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm
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
    series_name = forms.CharField(
        label="Serie (nume)",
        max_length=80,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: Seria 1"}),
    )
    year = forms.IntegerField(
        label="An",
        initial=lambda: timezone.now().year,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    start_date = forms.DateField(
        label="Data populare",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    house_existing = forms.ModelChoiceField(
        label="Hală (existentă)",
        queryset=House.objects.all().order_by("name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    house_name = forms.CharField(
        label="Hală nouă",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: Hala 1"}),
    )

    initial_count = forms.IntegerField(
        label="Număr pui (inițial)",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
    )

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
                raise ValidationError(f"Sezonul '{season_name}' există deja. Alege alt nume sau alt an.")

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

        season_name = f"{series_name} {year}"
        season = Season.objects.create(name=season_name, start_date=start_date, is_active=True)
        flock = Flock.objects.create(season=season, house=house, start_date=start_date, initial_count=initial_count)
        return season, flock


class MortalityQuickAddForm(forms.Form):
    date = forms.DateField(
        label="Data",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    flock = forms.ModelChoiceField(
        label="Lot (serie/hală)",
        queryset=Flock.objects.select_related("season", "house").all().order_by("-start_date", "-id"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    count = forms.IntegerField(
        label="Mortalitate (nr)",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "autofocus": "autofocus", "inputmode": "numeric"}),
    )
    reason = forms.CharField(
        label="Motiv (opțional)",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: stres termic"}),
    )

    def clean(self):
        cleaned = super().clean()
        flock = cleaned.get("flock")
        count = cleaned.get("count")

        if flock and count:
            total = MortalityEvent.objects.filter(flock=flock).aggregate(s=Sum("count"))["s"] or 0
            current = flock.initial_count - int(total)
            if int(count) > max(current, 0):
                raise ValidationError(f"Nu poți scădea {count}. În lot mai sunt ~{max(current, 0)} capete.")
        return cleaned
""")

    # ---------- views ----------
    write("apps/ui/views.py", """\
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.core.models import Flock
from apps.health.models import MortalityEvent
from .forms import CreateSeriesForm, MortalityQuickAddForm


WEEKDAYS_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]

def is_manager(user) -> bool:
    # ADMIN / MANAGER / superuser
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["ADMIN", "MANAGER"]).exists()


@login_required
def dashboard(request):
    if request.method == "POST":
        mortality_form = MortalityQuickAddForm(request.POST)
        if mortality_form.is_valid():
            MortalityEvent.objects.create(
                flock=mortality_form.cleaned_data["flock"],
                date=mortality_form.cleaned_data["date"],
                count=mortality_form.cleaned_data["count"],
                reason=mortality_form.cleaned_data.get("reason", ""),
                created_by=request.user,
            )
            messages.success(request, "Mortalitatea a fost salvată și s-a actualizat numărul curent.")
            return redirect("ui:dashboard")
        else:
            messages.error(request, "Nu am putut salva. Verifică datele din formular.")
    else:
        mortality_form = MortalityQuickAddForm()

    flocks = (
        Flock.objects.select_related("season", "house")
        .annotate(mortality_total=Coalesce(Sum("mortality_events__count"), 0))
        .order_by("-start_date", "-id")
    )

    # calcule "cati sunt in prezent" (nu modificam initial_count, doar calculam)
    for f in flocks:
        f.current_count = max(int(f.initial_count) - int(f.mortality_total or 0), 0)
        f.mortality_pct = (100.0 * float(f.mortality_total or 0) / float(f.initial_count)) if f.initial_count else 0.0

    recent = (
        MortalityEvent.objects.select_related("flock", "flock__season", "flock__house")
        .order_by("-date", "-id")[:30]
    )

    today = timezone.localdate()
    today_weekday = WEEKDAYS_RO[today.weekday()]

    return render(request, "ui/dashboard.html", {
        "flocks": flocks,
        "mortality_form": mortality_form,
        "recent_mortalities": recent,
        "today": today,
        "today_weekday": today_weekday,
    })


@login_required
def create_series(request):
    if not is_manager(request.user):
        messages.error(request, "Nu ai permisiuni să creezi serii/loturi. Cere acces de la administrator.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        form = CreateSeriesForm(request.POST)
        if form.is_valid():
            season, flock = form.save()
            messages.success(request, f"Serie creată: {season.name}. Lot nou în {flock.house.name} cu {flock.initial_count} capete.")
            return redirect("ui:dashboard")
        else:
            messages.error(request, "Nu am putut salva seria. Verifică formularul.")
    else:
        form = CreateSeriesForm()

    return render(request, "ui/create_series.html", {"form": form})
""")

    # ---------- urls ----------
    write("apps/ui/urls.py", """\
from __future__ import annotations

from django.urls import path
from django.contrib.auth import views as auth_views

from .forms import BootstrapAuthenticationForm
from . import views

app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("series/new/", views.create_series, name="create_series"),

    path("login/", auth_views.LoginView.as_view(
        template_name="ui/login.html",
        authentication_form=BootstrapAuthenticationForm,
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
""")

    # ---------- templates ----------
    write("apps/ui/templates/ui/base.html", """\
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
            <li class="nav-item"><a class="nav-link" href="{% url 'ui:create_series' %}">Serie nouă</a></li>
            <li class="nav-item"><a class="nav-link" href="/admin/">Admin</a></li>
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

    write("apps/ui/templates/ui/login.html", """\
{% extends "ui/base.html" %}
{% block title %}Login{% endblock %}

{% block content %}
<div class="row justify-content-center">
  <div class="col-md-6 col-lg-4">
    <div class="card">
      <div class="card-header">Autentificare</div>
      <div class="card-body">
        <form method="post">
          {% csrf_token %}
          {{ form.non_field_errors }}
          <div class="mb-2">
            <label class="form-label">Utilizator</label>
            {{ form.username }}
          </div>
          <div class="mb-2">
            <label class="form-label">Parolă</label>
            {{ form.password }}
          </div>
          <button class="btn btn-primary w-100" type="submit">Intră</button>
        </form>

        <div class="text-muted small mt-3">
          Conturile se creează din <a href="/admin/">Admin</a>.
        </div>
      </div>
    </div>
  </div>
</div>
{% endblock %}
""")

    write("apps/ui/templates/ui/dashboard.html", """\
{% extends "ui/base.html" %}
{% block title %}Dashboard{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <div>
    <h2 class="mb-0">Dashboard</h2>
    <div class="text-muted">Azi: {{ today }} ({{ today_weekday }})</div>
  </div>
  <a class="btn btn-primary" href="{% url 'ui:create_series' %}">+ Serie nouă</a>
</div>

<ul class="nav nav-tabs" id="dashTabs" role="tablist">
  <li class="nav-item" role="presentation">
    <button class="nav-link active" id="flocks-tab" data-bs-toggle="tab" data-bs-target="#flocks" type="button" role="tab">
      Câți sunt în prezent
    </button>
  </li>
  <li class="nav-item" role="presentation">
    <button class="nav-link" id="mort-tab" data-bs-toggle="tab" data-bs-target="#mort" type="button" role="tab">
      Mortalitate
    </button>
  </li>
</ul>

<div class="tab-content pt-3">
  <div class="tab-pane fade show active" id="flocks" role="tabpanel">
    {% if flocks %}
      <div class="table-responsive">
        <table class="table table-striped align-middle">
          <thead>
            <tr>
              <th>Serie/Sezon</th>
              <th>Hală</th>
              <th>Data populare</th>
              <th class="text-end">Nr inițial</th>
              <th class="text-end">Mortalitate</th>
              <th class="text-end">Nr curent</th>
              <th class="text-end">Mortalitate %</th>
            </tr>
          </thead>
          <tbody>
            {% for f in flocks %}
              <tr>
                <td>{{ f.season.name }}</td>
                <td>{{ f.house.name }}</td>
                <td>{{ f.start_date }}</td>
                <td class="text-end">{{ f.initial_count }}</td>
                <td class="text-end">{{ f.mortality_total }}</td>
                <td class="text-end fw-semibold">{{ f.current_count }}</td>
                <td class="text-end">{{ f.mortality_pct|floatformat:2 }}%</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="alert alert-info">Nu ai încă loturi. Creează o serie nouă.</div>
    {% endif %}
  </div>

  <div class="tab-pane fade" id="mort" role="tabpanel">
    <div class="row g-3">
      <div class="col-lg-5">
        <div class="card">
          <div class="card-header">Adaugă mortalitate (Enter = salvează)</div>
          <div class="card-body">
            <form method="post" novalidate>
              {% csrf_token %}
              {{ mortality_form.non_field_errors }}

              <div class="mb-2">
                <label class="form-label">{{ mortality_form.date.label }}</label>
                {{ mortality_form.date }}
                <div class="form-text">Ziua: <span id="weekdayLabel">—</span></div>
                {{ mortality_form.date.errors }}
              </div>

              <div class="mb-2">
                <label class="form-label">{{ mortality_form.flock.label }}</label>
                {{ mortality_form.flock }}
                {{ mortality_form.flock.errors }}
              </div>

              <div class="mb-2">
                <label class="form-label">{{ mortality_form.count.label }}</label>
                {{ mortality_form.count }}
                {{ mortality_form.count.errors }}
              </div>

              <div class="mb-2">
                <label class="form-label">{{ mortality_form.reason.label }}</label>
                {{ mortality_form.reason }}
                {{ mortality_form.reason.errors }}
              </div>

              <button class="btn btn-danger" type="submit">Salvează mortalitatea</button>
            </form>
          </div>
        </div>
      </div>

      <div class="col-lg-7">
        <div class="card">
          <div class="card-header">Ultimele înregistrări</div>
          <div class="card-body">
            {% if recent_mortalities %}
              <div class="table-responsive">
                <table class="table table-sm align-middle">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Serie</th>
                      <th>Hală</th>
                      <th class="text-end">Nr</th>
                      <th>Motiv</th>
                    </tr>
                  </thead>
                  <tbody>
                    {% for m in recent_mortalities %}
                      <tr>
                        <td>{{ m.date }}</td>
                        <td>{{ m.flock.season.name }}</td>
                        <td>{{ m.flock.house.name }}</td>
                        <td class="text-end">{{ m.count }}</td>
                        <td>{{ m.reason }}</td>
                      </tr>
                    {% endfor %}
                  </tbody>
                </table>
              </div>
            {% else %}
              <div class="text-muted">Nicio înregistrare încă.</div>
            {% endif %}
          </div>
        </div>
      </div>
    </div>

  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
  (function(){
    function weekdayFromDate(val){
      if(!val) return "—";
      const d = new Date(val + "T00:00:00");
      return d.toLocaleDateString("ro-RO", { weekday: "long" });
    }

    const dateInput = document.querySelector('input[name="date"]');
    const label = document.getElementById("weekdayLabel");
    if(dateInput && label){
      label.textContent = weekdayFromDate(dateInput.value);
      dateInput.addEventListener("change", function(){ label.textContent = weekdayFromDate(this.value); });
    }

    const countInput = document.querySelector('input[name="count"]');
    if(countInput){
      countInput.addEventListener("keydown", function(e){
        if(e.key === "Enter"){
          e.preventDefault();
          this.form.submit();
        }
      });
    }
  })();
</script>
{% endblock %}
""")

    write("apps/ui/templates/ui/create_series.html", """\
{% extends "ui/base.html" %}
{% block title %}Serie nouă{% endblock %}

{% block content %}
<h2 class="mb-3">Creează serie / lot nou</h2>

<div class="card">
  <div class="card-body">
    <form method="post" novalidate>
      {% csrf_token %}
      {{ form.non_field_errors }}

      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">{{ form.series_name.label }}</label>
          {{ form.series_name }}
          {{ form.series_name.errors }}
        </div>

        <div class="col-md-2">
          <label class="form-label">{{ form.year.label }}</label>
          {{ form.year }}
          {{ form.year.errors }}
        </div>

        <div class="col-md-4">
          <label class="form-label">{{ form.start_date.label }}</label>
          {{ form.start_date }}
          {{ form.start_date.errors }}
        </div>

        <div class="col-md-6">
          <label class="form-label">{{ form.house_existing.label }}</label>
          {{ form.house_existing }}
          <div class="form-text">Sau completează “Hală nouă” mai jos.</div>
          {{ form.house_existing.errors }}
        </div>

        <div class="col-md-6">
          <label class="form-label">{{ form.house_name.label }}</label>
          {{ form.house_name }}
          {{ form.house_name.errors }}
        </div>

        <div class="col-md-4">
          <label class="form-label">{{ form.initial_count.label }}</label>
          {{ form.initial_count }}
          {{ form.initial_count.errors }}
        </div>
      </div>

      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Salvează</button>
        <a class="btn btn-outline-secondary" href="{% url 'ui:dashboard' %}">Înapoi</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
""")

    # ---------- patch project ----------
    patch_settings()
    patch_urls()

    print("✅ UI adăugat cu succes.")
    print("➡️ Rulează: python manage.py runserver")
    print("➡️ Deschide: http://127.0.0.1:8000/ (login la /login/)")

if __name__ == "__main__":
    main()

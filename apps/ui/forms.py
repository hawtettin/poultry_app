from __future__ import annotations

from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.db.models import Sum

from apps.core.models import House, Season, Flock
from apps.health.models import MortalityEvent
from apps.finance.models import Document, DocumentLine, Category, Partner


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
        queryset=House.objects.none(),
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
        queryset=Flock.objects.none(),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["flock"].queryset = Flock.objects.select_related("season", "house").all().order_by("-start_date", "-id")

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


class MortalityEditForm(forms.ModelForm):
    class Meta:
        model = MortalityEvent
        fields = ["date", "flock", "count", "reason", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "flock": forms.Select(attrs={"class": "form-select"}),
            "count": forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        flock = cleaned.get("flock")
        count = cleaned.get("count")
        if flock and count:
            other_total = (
                MortalityEvent.objects.filter(flock=flock)
                .exclude(pk=self.instance.pk)
                .aggregate(s=Sum("count"))["s"]
                or 0
            )
            current = flock.initial_count - int(other_total)
            if int(count) > max(current, 0):
                raise ValidationError(f"Valoare prea mare. În lot mai sunt ~{max(current, 0)} capete (fără această înregistrare).")
        return cleaned

# =============================================================
# Admin: user provisioning (EMPLOYEE / MANAGER)
# =============================================================

ROLE_CHOICES = [
    ("EMPLOYEE", "Angajat"),
    ("MANAGER", "Manager fermă"),
]


class UserProvisionForm(UserCreationForm):
    role = forms.ChoiceField(
        label="Rol",
        choices=ROLE_CHOICES,
        initial="EMPLOYEE",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email", "role", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # bootstrap styling
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def save(self, commit: bool = True):
        user = super().save(commit=commit)
        role = self.cleaned_data.get("role")
        # assign group (idempotent)
        from apps.accounts.utils import ensure_group

        grp = ensure_group(role)
        user.groups.add(grp)
        return user


# =============================================================
# Sales: edit/create documents of type "sale"
# =============================================================


class SaleDocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            "season",
            "flock",
            "partner",
            "doc_no",
            "date",
            "currency",
            "vat",
            "status",
            "notes",
        ]
        widgets = {
            "season": forms.Select(attrs={"class": "form-select"}),
            "flock": forms.Select(attrs={"class": "form-select"}),
            "partner": forms.Select(attrs={"class": "form-select"}),
            "doc_no": forms.TextInput(attrs={"class": "form-control"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "currency": forms.TextInput(attrs={"class": "form-control"}),
            "vat": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        # enforce doc_type sale at UI level
        if self.instance and self.instance.pk:
            if self.instance.doc_type != "sale":
                raise ValidationError("Acest formular poate edita doar documente de tip vânzare.")
        return cleaned


class SaleLineForm(forms.ModelForm):
    class Meta:
        model = DocumentLine
        fields = ["category", "description", "qty", "unit", "unit_price"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "qty": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "unit": forms.TextInput(attrs={"class": "form-control"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # for sales, prefer income categories
        self.fields["category"].queryset = Category.objects.filter(kind="income").order_by("name")


SaleLineFormSet = inlineformset_factory(
    parent_model=Document,
    model=DocumentLine,
    form=SaleLineForm,
    extra=1,
    can_delete=True,
)

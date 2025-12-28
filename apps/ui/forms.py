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

    def clean(self):
        cleaned = super().clean()
        flock = cleaned.get("flock")
        count = cleaned.get("count")
        if flock and count:
            # total fara aceasta inregistrare
            other_total = (
                MortalityEvent.objects
                .filter(flock=flock)
                .exclude(pk=self.instance.pk)
                .aggregate(s=Sum("count"))["s"] or 0
            )
            current = int(flock.initial_count) - int(other_total)
            if int(count) > max(current, 0):
                raise forms.ValidationError(
                    f"Valoare prea mare. În lot mai sunt ~{max(current, 0)} capete (fără această înregistrare)."
                )
        return cleaned


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
    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            return username
        # case-insensitive unique
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Acest username există deja. Alege altul (ex: vasilica1).")
        return username


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

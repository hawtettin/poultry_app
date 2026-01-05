from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import House, Season, Flock


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

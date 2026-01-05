from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import Flock
from apps.health.models import MortalityEvent


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
        self.fields["flock"].queryset = (
            Flock.objects.select_related("season", "house").all().order_by("-start_date", "-id")
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
                raise ValidationError(
                    f"Valoare prea mare. În lot mai sunt ~{max(current, 0)} capete (fără această înregistrare)."
                )

        return cleaned

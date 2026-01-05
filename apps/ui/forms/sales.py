from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import Flock
from apps.finance.services import SaleInput, calc_sale_total, create_sale, validate_sale_input


class SaleQuickAddForm(forms.Form):
    """Quick-add pentru vânzări.

    UI rules:
    - Totalul (BANI) se calculează automat: qty * preț.
    - DATORIE este opțională; dacă există, se creează un Payment scadent.
    - Vânzarea se leagă de lot (flock) -> serie + hală.
    - Validare stoc: nu poți vinde mai mulți pui (albi+colorați) decât sunt disponibili.
    """

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

    buyer_name = forms.CharField(
        label="Cumpărător",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Nume cumpărător"}),
    )

    pui_albi = forms.IntegerField(
        label="Pui albi (cap)",
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
    )
    pret_pui_albi = forms.DecimalField(
        label="Preț pui albi (RON/cap)",
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=4,
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}),
    )

    pui_colorati = forms.IntegerField(
        label="Pui colorați (cap)",
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
    )
    pret_pui_colorati = forms.DecimalField(
        label="Preț pui colorați (RON/cap)",
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=4,
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}),
    )

    furaj_kg = forms.DecimalField(
        label="Furaj (kg)",
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=3,
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "inputmode": "decimal"}),
    )
    pret_furaj = forms.DecimalField(
        label="Preț furaj (RON/kg)",
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=4,
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}),
    )

    datorie = forms.DecimalField(
        label="Datorie (RON) – opțional",
        required=False,
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["flock"].queryset = (
            Flock.objects.select_related("season", "house").all().order_by("-start_date", "-id")
        )

    def _to_input(self) -> SaleInput:
        flock: Flock = self.cleaned_data["flock"]
        sale_date = self.cleaned_data["date"]
        return SaleInput(
            flock=flock,
            sale_date=sale_date,
            buyer_name=(self.cleaned_data.get("buyer_name") or "").strip(),
            pui_albi=int(self.cleaned_data.get("pui_albi") or 0),
            pret_pui_albi=self.cleaned_data.get("pret_pui_albi") or Decimal("0"),
            pui_colorati=int(self.cleaned_data.get("pui_colorati") or 0),
            pret_pui_colorati=self.cleaned_data.get("pret_pui_colorati") or Decimal("0"),
            furaj_kg=self.cleaned_data.get("furaj_kg") or Decimal("0"),
            pret_furaj=self.cleaned_data.get("pret_furaj") or Decimal("0"),
            datorie=(self.cleaned_data.get("datorie") or Decimal("0")).quantize(Decimal("0.01")),
        )

    def clean(self):
        cleaned = super().clean()
        # If required fields are missing, let Django show field-level errors first.
        if cleaned.get("flock") is None or cleaned.get("date") is None:
            return cleaned

        try:
            data = self._to_input()
            validate_sale_input(data)
            cleaned["_total"] = calc_sale_total(data)
        except ValidationError as e:
            raise ValidationError(e.messages)

        return cleaned

    def save(self, *, user):
        data = self._to_input()
        return create_sale(user=user, data=data)

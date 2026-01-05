from __future__ import annotations

from decimal import Decimal

from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models import Q, Sum

from apps.core.models import House, Season, Flock
from apps.health.models import MortalityEvent
from apps.finance.models import Document, DocumentLine, Payment, Partner
from apps.accounts.permissions import ROLE_CHOICES, assign_role, get_current_role

User = get_user_model()


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


class SaleQuickAddForm(forms.Form):
    """Quick-add pentru vânzări.

    Cerințe:
    - BANI = valoarea totală a vânzării (calculată automat din cantitate * preț).
    - DATORIE = opțională (dacă există, se creează un Payment status=due).
    - Vânzarea se leagă de serie (flock) și implicit de hală.
    - Validare stoc: nu poți vinde mai mulți pui (albi+colorați) decât sunt disponibili la data respectivă.
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
            Flock.objects.select_related("season", "house")
            .all()
            .order_by("-start_date", "-id")
        )

    def clean(self):
        cleaned = super().clean()

        date = cleaned.get("date")
        flock = cleaned.get("flock")
        buyer_name = (cleaned.get("buyer_name") or "").strip()

        pui_albi = int(cleaned.get("pui_albi") or 0)
        pui_colorati = int(cleaned.get("pui_colorati") or 0)
        furaj_kg = cleaned.get("furaj_kg") or Decimal("0")

        pret_pui_albi = cleaned.get("pret_pui_albi") or Decimal("0")
        pret_pui_colorati = cleaned.get("pret_pui_colorati") or Decimal("0")
        pret_furaj = cleaned.get("pret_furaj") or Decimal("0")

        datorie = cleaned.get("datorie")
        datorie = datorie if datorie is not None else Decimal("0")

        if not buyer_name:
            raise ValidationError("Completează cumpărătorul.")

        if pui_albi <= 0 and pui_colorati <= 0 and furaj_kg <= 0:
            raise ValidationError("Completează cel puțin un câmp: pui albi / pui colorați / furaj.")

        # total vânzare (BANI)
        total = (
            (Decimal(pui_albi) * pret_pui_albi)
            + (Decimal(pui_colorati) * pret_pui_colorati)
            + (furaj_kg * pret_furaj)
        ).quantize(Decimal("0.01"))

        if total <= 0:
            raise ValidationError("Totalul vânzării este 0. Verifică cantitățile și prețurile.")

        if datorie < 0:
            raise ValidationError("Datoria nu poate fi negativă.")

        if datorie > total:
            raise ValidationError(f"Datoria ({datorie} RON) nu poate depăși totalul ({total} RON).")

        # validare stoc pui la data respectivă
        if flock and date:
            if date < flock.start_date:
                raise ValidationError("Data vânzării nu poate fi înainte de data populării lotului.")

            # Mortalitate până la data vânzării
            mort = (
                MortalityEvent.objects.filter(flock=flock, date__lte=date)
                .aggregate(s=Sum("count"))["s"]
                or 0
            )

            # Vânzări pui până la data vânzării (albi+colorați)
            sold = (
                DocumentLine.objects.filter(
                    document__doc_type="sale",
                    document__flock=flock,
                    document__date__lte=date,
                )
                .filter(
                    Q(description__iexact="Pui albi")
                    | Q(description__iexact="Pui colorați")
                    | Q(description__iexact="Pui colorati")
                )
                .aggregate(s=Sum("qty"))["s"]
                or Decimal("0")
            )

            available = max(int(flock.initial_count) - int(mort) - int(sold), 0)
            to_sell = pui_albi + pui_colorati

            if to_sell > available:
                raise ValidationError(
                    f"Stoc insuficient: în lot mai sunt ~{available} capete la {date}. "
                    f"Ai încercat să vinzi {to_sell} (albi+colorați)."
                )

        cleaned["buyer_name"] = buyer_name
        cleaned["_total"] = total
        cleaned["_datorie"] = datorie
        return cleaned

    def save(self, *, user):
        """Creează Document (sale) + DocumentLine-uri și, dacă există datorie, Payment status=due."""
        date = self.cleaned_data["date"]
        flock: Flock = self.cleaned_data["flock"]
        buyer_name = self.cleaned_data["buyer_name"]

        pui_albi = int(self.cleaned_data.get("pui_albi") or 0)
        pui_colorati = int(self.cleaned_data.get("pui_colorati") or 0)
        furaj_kg: Decimal = self.cleaned_data.get("furaj_kg") or Decimal("0")

        pret_pui_albi: Decimal = self.cleaned_data.get("pret_pui_albi") or Decimal("0")
        pret_pui_colorati: Decimal = self.cleaned_data.get("pret_pui_colorati") or Decimal("0")
        pret_furaj: Decimal = self.cleaned_data.get("pret_furaj") or Decimal("0")
        datorie: Decimal = self.cleaned_data.get("_datorie") or Decimal("0")

        partner, _ = Partner.objects.get_or_create(
            name=buyer_name,
            defaults={"partner_type": "client"},
        )

        doc = Document.objects.create(
            doc_type="sale",
            status="approved",
            season=flock.season,
            flock=flock,
            partner=partner,
            date=date,
            currency="RON",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

        if pui_albi > 0:
            DocumentLine.objects.create(
                document=doc,
                description="Pui albi",
                qty=Decimal(pui_albi),
                unit="cap",
                unit_price=pret_pui_albi,
            )
        if pui_colorati > 0:
            DocumentLine.objects.create(
                document=doc,
                description="Pui colorați",
                qty=Decimal(pui_colorati),
                unit="cap",
                unit_price=pret_pui_colorati,
            )
        if furaj_kg and furaj_kg > 0:
            DocumentLine.objects.create(
                document=doc,
                description="Furaj",
                qty=furaj_kg,
                unit="kg",
                unit_price=pret_furaj,
            )

        # recalc (în caz că nu există linii sau pentru siguranță)
        doc.recalc_totals()
        doc.save(update_fields=["subtotal", "total"])

        if datorie and datorie > 0:
            Payment.objects.create(
                document=doc,
                due_date=date,
                amount=datorie.quantize(Decimal("0.01")),
                method="other",
                status="due",
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )

        return doc


class UserCreateForm(UserCreationForm):
    role = forms.ChoiceField(
        label="Rol",
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = "form-control"
            if name == "role":
                css = "form-select"
            field.widget.attrs.setdefault("class", css)
            field.widget.attrs.setdefault("autocomplete", "off")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
            assign_role(user, self.cleaned_data.get("role", "EMPLOYEE"))
        return user


class UserUpdateForm(forms.ModelForm):
    role = forms.ChoiceField(
        label="Rol",
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    is_active = forms.BooleanField(label="Activ", required=False)
    new_password1 = forms.CharField(
        label="Parolă nouă",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    new_password2 = forms.CharField(
        label="Parolă nouă (confirmare)",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_active", "role", "new_password1", "new_password2"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        u: User = self.instance
        self.fields["role"].initial = get_current_role(u)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 or p2:
            if p1 != p2:
                raise ValidationError("Parolele nu coincid.")
            if p1 and len(p1) < 8:
                raise ValidationError("Parola trebuie să aibă minim 8 caractere.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("new_password1"):
            user.set_password(self.cleaned_data["new_password1"])
        if commit:
            user.save()
            assign_role(user, self.cleaned_data.get("role", "EMPLOYEE"))
        return user


class PaymentEditForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["due_date", "paid_date", "amount", "method", "status"]
        widgets = {
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "paid_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "method": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status") or "due"
        paid_date = cleaned.get("paid_date")
        if status == "paid" and not paid_date:
            cleaned["paid_date"] = timezone.localdate()
        if status == "due":
            cleaned["paid_date"] = None
        return cleaned

    def save(self, commit=True):
        obj: Payment = super().save(commit=False)
        obj.amount = (obj.amount or Decimal("0"))
        obj.amount = obj.amount.quantize(Decimal("0.01"))
        if obj.status == "due":
            obj.paid_date = None
        if commit:
            obj.save()
        return obj

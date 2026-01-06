from __future__ import annotations

from decimal import Decimal

from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User
from django.db.models import Q, Sum

# Django's built-in ClearableFileInput raises ValueError when using the
# "multiple" attribute unless the widget explicitly allows multiple selection.
# We need this to support attaching multiple files (factură + chitanță/OP etc.).


class MultipleClearableFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A FileField that accepts multiple uploaded files."""

    def to_python(self, data):
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return list(data)
        return [data]

    def validate(self, data):
        # data is a list
        if self.required and not data:
            raise ValidationError(self.error_messages["required"], code="required")

    def run_validators(self, data):
        for f in data:
            super().run_validators(f)

    def clean(self, data, initial=None):
        data = self.to_python(data)
        self.validate(data)
        self.run_validators(data)
        return data

from apps.core.models import House, Season, Flock
from apps.health.models import MortalityEvent
from apps.finance.models import Document, DocumentLine, Payment, Partner


ROLE_CHOICES = [
    ("EMPLOYEE", "Angajat"),
    ("MANAGER", "Manager fermă"),
]


class BootstrapAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-control")
            f.widget.attrs.setdefault("autocomplete", "off")


class StaffUserCreateForm(UserCreationForm):
    """Formular pentru creare conturi (EMPLOYEE / MANAGER).

    Folosit în UI (nu în Django Admin).
    """

    role = forms.ChoiceField(
        label="Rol",
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Bootstrap styles
        for name, f in self.fields.items():
            # role are deja form-select
            if name == "role":
                continue
            f.widget.attrs.setdefault("class", "form-control")
            f.widget.attrs.setdefault("autocomplete", "off")

        # Email optional (implicit este blank=True în User)
        self.fields["email"].required = False

    def save(self, commit: bool = True):
        # UserCreationForm face set_password; folosim commit=False ca să putem seta grupul după save.
        user = super().save(commit=False)
        if commit:
            user.save()

        role = (self.cleaned_data.get("role") or "").strip() or "EMPLOYEE"
        if commit:
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)

        return user


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

    initial_white_count = forms.IntegerField(
        label="Pui albi (inițial)",
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
    )

    initial_colored_count = forms.IntegerField(
        label="Pui colorați (inițial)",
        min_value=0,
        initial=0,
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
        # Validare stoc inițial (pe tip)
        w = int(cleaned.get("initial_white_count") or 0)
        c = int(cleaned.get("initial_colored_count") or 0)
        if (w + c) <= 0:
            raise ValidationError("Completează numărul inițial pentru pui albi și/sau pui colorați.")
        return cleaned

    def save(self):
        series_name = self.cleaned_data["series_name"].strip()
        year = int(self.cleaned_data["year"])
        start_date = self.cleaned_data["start_date"]
        initial_white_count = int(self.cleaned_data.get("initial_white_count") or 0)
        initial_colored_count = int(self.cleaned_data.get("initial_colored_count") or 0)
        initial_count = int(initial_white_count + initial_colored_count)

        house = self.cleaned_data.get("house_existing")
        house_name = (self.cleaned_data.get("house_name") or "").strip()
        if house_name:
            house, _ = House.objects.get_or_create(name=house_name)

        season_name = f"{series_name} {year}"
        season = Season.objects.create(name=season_name, start_date=start_date, is_active=True)
        flock = Flock.objects.create(
            season=season,
            house=house,
            start_date=start_date,
            initial_count=initial_count,
            initial_white_count=initial_white_count,
            initial_colored_count=initial_colored_count,
        )
        return season, flock


class FlockEditForm(forms.ModelForm):
    """Editare lot: defalcare pui albi / pui colorați.

    Folosim acest formular ca să poți corecta / actualiza loturile existente fără a intra în Django Admin.
    """

    class Meta:
        model = Flock
        fields = ["initial_white_count", "initial_colored_count"]
        widgets = {
            "initial_white_count": forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "initial_colored_count": forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
        }

    def clean(self):
        cleaned = super().clean()
        w = int(cleaned.get("initial_white_count") or 0)
        c = int(cleaned.get("initial_colored_count") or 0)
        if (w + c) <= 0:
            raise ValidationError("Totalul inițial trebuie să fie > 0 (completează pui albi și/sau pui colorați).")
        return cleaned

    def save(self, commit: bool = True):
        inst: Flock = super().save(commit=False)
        inst.initial_count = int((inst.initial_white_count or 0) + (inst.initial_colored_count or 0))
        if commit:
            inst.save(update_fields=["initial_white_count", "initial_colored_count", "initial_count"])
        return inst


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

    poultry_type = forms.ChoiceField(
        label="Tip pui",
        choices=MortalityEvent.POULTRY_TYPES,
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
        date = cleaned.get("date")
        flock: Flock | None = cleaned.get("flock")
        ptype = (cleaned.get("poultry_type") or "").strip() or "white"
        count = cleaned.get("count")

        if flock and date and count:
            if date < flock.start_date:
                raise ValidationError("Data mortalității nu poate fi înainte de data populării lotului.")

            # inventar inițial pe tip (fallback pentru date vechi)
            if ptype == "colored":
                initial = int(getattr(flock, "initial_colored_count", 0) or 0)
            else:
                initial = int(getattr(flock, "initial_white_count", 0) or 0)
                if initial == 0:
                    initial = int(getattr(flock, "initial_count", 0) or 0)

            mort = (
                MortalityEvent.objects.filter(flock=flock, poultry_type=ptype, date__lte=date)
                .aggregate(s=Sum("count"))["s"]
                or 0
            )

            # vânzări pui până la data mortalității (pe tip)
            if ptype == "colored":
                sold = (
                    DocumentLine.objects.filter(
                        document__doc_type="sale",
                        document__flock=flock,
                        document__date__lte=date,
                    )
                    .filter(Q(description__iexact="Pui colorați") | Q(description__iexact="Pui colorati"))
                    .aggregate(s=Sum("qty"))["s"]
                    or Decimal("0")
                )
            else:
                sold = (
                    DocumentLine.objects.filter(
                        document__doc_type="sale",
                        document__flock=flock,
                        document__date__lte=date,
                    )
                    .filter(description__iexact="Pui albi")
                    .aggregate(s=Sum("qty"))["s"]
                    or Decimal("0")
                )

            available = max(int(initial) - int(mort) - int(sold), 0)
            if int(count) > available:
                label = "pui colorați" if ptype == "colored" else "pui albi"
                raise ValidationError(f"Nu poți scădea {count} ({label}). În lot mai sunt ~{available} capete la {date}.")
        return cleaned


class MortalityEditForm(forms.ModelForm):
    class Meta:
        model = MortalityEvent
        fields = ["date", "flock", "poultry_type", "count", "reason", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "flock": forms.Select(attrs={"class": "form-select"}),
            "poultry_type": forms.Select(attrs={"class": "form-select"}),
            "count": forms.NumberInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("date")
        flock: Flock | None = cleaned.get("flock")
        ptype = (cleaned.get("poultry_type") or "").strip() or "white"
        count = cleaned.get("count")

        if flock and date and count:
            if date < flock.start_date:
                raise ValidationError("Data mortalității nu poate fi înainte de data populării lotului.")

            if ptype == "colored":
                initial = int(getattr(flock, "initial_colored_count", 0) or 0)
            else:
                initial = int(getattr(flock, "initial_white_count", 0) or 0)
                if initial == 0:
                    initial = int(getattr(flock, "initial_count", 0) or 0)

            other_mort = (
                MortalityEvent.objects.filter(flock=flock, poultry_type=ptype, date__lte=date)
                .exclude(pk=self.instance.pk)
                .aggregate(s=Sum("count"))["s"]
                or 0
            )

            if ptype == "colored":
                sold = (
                    DocumentLine.objects.filter(
                        document__doc_type="sale",
                        document__flock=flock,
                        document__date__lte=date,
                    )
                    .filter(Q(description__iexact="Pui colorați") | Q(description__iexact="Pui colorati"))
                    .aggregate(s=Sum("qty"))["s"]
                    or Decimal("0")
                )
            else:
                sold = (
                    DocumentLine.objects.filter(
                        document__doc_type="sale",
                        document__flock=flock,
                        document__date__lte=date,
                    )
                    .filter(description__iexact="Pui albi")
                    .aggregate(s=Sum("qty"))["s"]
                    or Decimal("0")
                )

            available = max(int(initial) - int(other_mort) - int(sold), 0)
            if int(count) > available:
                label = "pui colorați" if ptype == "colored" else "pui albi"
                raise ValidationError(
                    f"Valoare prea mare. În lot mai sunt ~{available} capete ({label}) la {date} (fără această înregistrare)."
                )
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
        # Important: îl calculăm "line-wise" (cu rotunjire pe linie la 0.01)
        # ca să corespundă cu DocumentLine.line_total (care este quantize(0.01)).
        total = (
            (Decimal(pui_albi) * pret_pui_albi).quantize(Decimal("0.01"))
            + (Decimal(pui_colorati) * pret_pui_colorati).quantize(Decimal("0.01"))
            + (furaj_kg * pret_furaj).quantize(Decimal("0.01"))
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

            # Inventar inițial pe tip (fallback pentru date vechi)
            initial_white = int(getattr(flock, "initial_white_count", 0) or 0)
            if initial_white == 0:
                initial_white = int(getattr(flock, "initial_count", 0) or 0)
            initial_colored = int(getattr(flock, "initial_colored_count", 0) or 0)

            # Mortalitate până la data vânzării (pe tip)
            mort_white = (
                MortalityEvent.objects.filter(flock=flock, poultry_type="white", date__lte=date)
                .aggregate(s=Sum("count"))["s"]
                or 0
            )
            mort_colored = (
                MortalityEvent.objects.filter(flock=flock, poultry_type="colored", date__lte=date)
                .aggregate(s=Sum("count"))["s"]
                or 0
            )

            # Vânzări până la data vânzării (pe tip)
            sold_white = (
                DocumentLine.objects.filter(
                    document__doc_type="sale",
                    document__flock=flock,
                    document__date__lte=date,
                )
                .filter(description__iexact="Pui albi")
                .aggregate(s=Sum("qty"))["s"]
                or Decimal("0")
            )
            sold_colored = (
                DocumentLine.objects.filter(
                    document__doc_type="sale",
                    document__flock=flock,
                    document__date__lte=date,
                )
                .filter(Q(description__iexact="Pui colorați") | Q(description__iexact="Pui colorati"))
                .aggregate(s=Sum("qty"))["s"]
                or Decimal("0")
            )

            avail_white = max(int(initial_white) - int(mort_white) - int(sold_white), 0)
            avail_colored = max(int(initial_colored) - int(mort_colored) - int(sold_colored), 0)

            if pui_albi > avail_white:
                raise ValidationError(
                    f"Stoc insuficient pentru pui albi: în lot mai sunt ~{avail_white} capete la {date}. "
                    f"Ai încercat să vinzi {pui_albi}."
                )
            if pui_colorati > avail_colored:
                raise ValidationError(
                    f"Stoc insuficient pentru pui colorați: în lot mai sunt ~{avail_colored} capete la {date}. "
                    f"Ai încercat să vinzi {pui_colorati}."
                )

        cleaned["buyer_name"] = buyer_name
        cleaned["_total"] = total
        cleaned["_datorie"] = datorie
        return cleaned

    def save(self, *, user):
        """Creează Document (sale) + DocumentLine-uri și plăți asociate.

        Convenție (pentru ledger):
        - Dacă vânzarea are parte încasată pe loc (cash), creăm un Payment status=paid
          cu suma = total - datorie (paid_date = data vânzării).
        - Dacă există datorie (>0), creăm un Payment status=due pentru partea restantă.

        Astfel, ledger-ul arată și vânzările plătite integral, nu doar datoriile.
        """
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
                house=flock.house,
                flock=flock,
                description="Pui albi",
                qty=Decimal(pui_albi),
                unit="cap",
                unit_price=pret_pui_albi,
            )
        if pui_colorati > 0:
            DocumentLine.objects.create(
                document=doc,
                house=flock.house,
                flock=flock,
                description="Pui colorați",
                qty=Decimal(pui_colorati),
                unit="cap",
                unit_price=pret_pui_colorati,
            )
        if furaj_kg and furaj_kg > 0:
            DocumentLine.objects.create(
                document=doc,
                house=flock.house,
                flock=flock,
                description="Furaj",
                qty=furaj_kg,
                unit="kg",
                unit_price=pret_furaj,
            )

        # recalc (în caz că nu există linii sau pentru siguranță)
        doc.recalc_totals()
        doc.save(update_fields=["subtotal", "vat", "total"])

        # 1) Încasat (cash) = total - datorie
        cash_amount = (doc.total or Decimal("0.00")) - (datorie or Decimal("0.00"))
        cash_amount = cash_amount.quantize(Decimal("0.01"))
        if cash_amount > 0:
            Payment.objects.create(
                document=doc,
                due_date=date,
                paid_date=date,
                amount=cash_amount,
                method="cash",
                status="paid",
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )

        # 2) Datorie (restant)
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


class PaymentEditForm(forms.ModelForm):
    """Editare plată (datorie / plată efectuată).

    Notă: permisiunile sunt aplicate în view (ADMIN/MANAGER orice, EMPLOYEE doar azi + doar ale lui).
    """

    class Meta:
        model = Payment
        fields = ["due_date", "paid_date", "amount", "method", "status"]
        widgets = {
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "paid_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}),
            "method": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned = super().clean()
        status = (cleaned.get("status") or "").strip() or "due"
        paid_date = cleaned.get("paid_date")

        # Dacă marcăm ca "paid" și nu există paid_date -> folosim azi.
        if status == "paid" and not paid_date:
            cleaned["paid_date"] = timezone.localdate()

        # Dacă marcăm ca "due" -> paid_date trebuie gol.
        if status == "due":
            cleaned["paid_date"] = None

        amount = cleaned.get("amount")
        if amount is not None and amount <= 0:
            raise ValidationError("Suma trebuie să fie pozitivă.")

        return cleaned


# -----------------------------
# Cheltuieli (mini-ERP)
# -----------------------------


EXPENSE_PAYMENT_STATUS = [
    ("unpaid", "Neplătit"),
    ("paid", "Plătit"),
    ("partial", "Parțial"),
]


EXPENSE_PAYMENT_METHOD = [
    ("cash", "Cash"),
    # În model, metoda se cheamă "bank"; în UI o afișăm ca OP.
    ("bank", "OP (transfer bancar)"),
    ("other", "Altul"),
]


class ExpenseDocumentForm(forms.Form):
    """Header cheltuială (Document doc_type='expense').

    Notă: este Form (nu ModelForm) ca să putem:
      - crea furnizorul dintr-un câmp text
      - seta status de plată / scadență / plăți inițiale
      - încărca atașamente multiple
    """

    date = forms.DateField(
        label="Data",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    season = forms.ModelChoiceField(
        label="Serie (sezon)",
        queryset=Season.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    supplier_name = forms.CharField(
        label="Furnizor",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: E.ON, Dedeman"}),
    )

    doc_no = forms.CharField(
        label="Nr document (factură/bon/OP)",
        max_length=80,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: FV123 / Bon 456"}),
    )

    vat_rate = forms.DecimalField(
        label="TVA (%)",
        required=False,
        min_value=Decimal("0"),
        max_digits=5,
        decimal_places=2,
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}),
    )

    payment_status = forms.ChoiceField(
        label="Status plată",
        choices=EXPENSE_PAYMENT_STATUS,
        initial="unpaid",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    payment_method = forms.ChoiceField(
        label="Metoda plată",
        choices=EXPENSE_PAYMENT_METHOD,
        initial="bank",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    due_date = forms.DateField(
        label="Scadență",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    paid_amount = forms.DecimalField(
        label="Suma plătită (doar pentru 'Parțial')",
        required=False,
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}),
    )

    notes = forms.CharField(
        label="Note (opțional)",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "detalii utile"}),
    )

    attachments = MultipleFileField(
        label="Atașamente (factură, chitanță, OP)",
        required=False,
        widget=MultipleClearableFileInput(attrs={"class": "form-control", "multiple": True}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["season"].queryset = Season.objects.all().order_by("-start_date", "-id")

        # default: primul sezon activ, dacă există
        if not self.initial.get("season"):
            active = Season.objects.filter(is_active=True).order_by("-start_date", "-id").first()
            if active:
                self.initial["season"] = active

    def clean(self):
        cleaned = super().clean()
        supplier = (cleaned.get("supplier_name") or "").strip()
        if not supplier:
            raise ValidationError("Completează furnizorul.")

        status = (cleaned.get("payment_status") or "").strip() or "unpaid"
        due = cleaned.get("due_date")

        if status in ("unpaid", "partial") and not due:
            raise ValidationError("Completează scadența pentru facturi neplătite/parțiale.")

        cleaned["supplier_name"] = supplier
        return cleaned


class ExpenseLineForm(forms.ModelForm):
    """Linie de cheltuială (DocumentLine) cu alocare pe hală/serie."""

    class Meta:
        model = DocumentLine
        fields = ["house", "flock", "description", "qty", "unit", "unit_price"]
        widgets = {
            "house": forms.Select(attrs={"class": "form-select"}),
            "flock": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: Gaz / Apă / Motorină"}),
            "qty": forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "inputmode": "decimal"}),
            "unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "kg / L / buc"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Querysets
        self.fields["house"].queryset = House.objects.all().order_by("name")
        self.fields["flock"].queryset = Flock.objects.select_related("season", "house").all().order_by("-start_date", "-id")
        self.fields["flock"].required = False

        # UX defaults
        if self.fields.get("qty") and self.initial.get("qty") is None:
            self.initial["qty"] = Decimal("1.000")

    def clean(self):
        cleaned = super().clean()
        house = cleaned.get("house")
        flock = cleaned.get("flock")

        # Dacă user alege flock, house trebuie să corespundă.
        if flock and house and getattr(flock, "house_id", None) != getattr(house, "id", None):
            raise ValidationError("Seria (lotul) selectată nu aparține halei selectate.")

        # Dacă alege flock, dar uită house, îl completăm automat.
        if flock and not house:
            cleaned["house"] = flock.house

        return cleaned

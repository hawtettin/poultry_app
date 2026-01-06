from __future__ import annotations
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Season, Flock


def _q2(v: Decimal) -> Decimal:
    """Quantize helper: 2 decimals."""
    return (v or Decimal("0.00")).quantize(Decimal("0.01"))

class Partner(models.Model):
    PARTNER_TYPES = [
        ("supplier", "Furnizor"),
        ("client", "Client"),
        ("other", "Altul"),
    ]
    name = models.CharField(max_length=200, unique=True)
    partner_type = models.CharField(max_length=20, choices=PARTNER_TYPES, default="other")
    tax_id = models.CharField(max_length=50, blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return self.name

class Category(models.Model):
    KIND = [("expense", "Cheltuiala"), ("income", "Venit")]
    name = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=10, choices=KIND, default="expense")

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"

class Document(models.Model):
    DOC_TYPES = [("expense", "Cheltuiala"), ("sale", "Vanzare")]
    STATUS = [("draft", "Draft"), ("approved", "Aprobat"), ("locked", "Blocat")]

    doc_type = models.CharField(max_length=10, choices=DOC_TYPES)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")

    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="documents")
    flock = models.ForeignKey(Flock, null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    partner = models.ForeignKey(Partner, null=True, blank=True, on_delete=models.PROTECT, related_name="documents")

    doc_no = models.CharField(max_length=80, blank=True, default="")
    date = models.DateField(default=timezone.localdate)
    currency = models.CharField(max_length=10, default="RON")

    # TVA (procent). Exemplu: 19.00 = 19%
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    vat = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    notes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_documents")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def recalc_totals(self):
        subtotal = sum((ln.line_total for ln in self.lines.all()), Decimal("0.00"))
        self.subtotal = _q2(subtotal)

        # TVA calculat automat din vat_rate.
        try:
            rate = Decimal(str(self.vat_rate or "0"))
        except Exception:
            rate = Decimal("0")
        if rate < 0:
            rate = Decimal("0")
        self.vat = _q2(self.subtotal * rate / Decimal("100"))
        self.total = _q2(self.subtotal + self.vat)

class DocumentLine(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lines")

    # Pentru mini-ERP cheltuieli: o factură poate avea linii alocate pe hale/serii.
    # Pentru compatibilitate cu vânzările existente, câmpurile sunt opționale.
    house = models.ForeignKey(
        "core.House",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="document_lines",
    )
    flock = models.ForeignKey(
        Flock,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="document_lines",
    )
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=250, blank=True, default="")
    qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1.000"))
    unit = models.CharField(max_length=20, blank=True, default="")
    unit_price = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    def save(self, *args, **kwargs):
        self.line_total = (self.qty * self.unit_price).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
        self.document.recalc_totals()
        self.document.save(update_fields=["subtotal", "vat", "total"])


class ExpenseAttachment(models.Model):
    """Atașamente multiple pentru cheltuieli.

    Legăm atașamentele de Document (doc_type='expense').
    Nu impunem la nivel DB ca documentul să fie expense, dar UI-ul folosește doar pe cheltuieli.
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="expense_attachments/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self) -> str:
        return self.original_name or (getattr(self.file, "name", "") or f"attachment#{self.pk}")

class Payment(models.Model):
    METHODS = [("cash", "Cash"), ("bank", "OP"), ("card", "Card"), ("other", "Altul")]
    STATUS = [("due", "Scadent"), ("paid", "Platit")]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="payments")
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHODS, default="bank")
    status = models.CharField(max_length=10, choices=STATUS, default="due")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    # Folosit pentru permisiuni (employee poate modifica doar plăți create de el în ziua curentă)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "due_date", "-id"]

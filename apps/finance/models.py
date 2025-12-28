from __future__ import annotations
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Season, Flock

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
        self.subtotal = subtotal
        self.total = (self.subtotal + self.vat).quantize(Decimal("0.01"))

class DocumentLine(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lines")
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
        self.document.save(update_fields=["subtotal", "total"])

class Payment(models.Model):
    METHODS = [("cash", "Cash"), ("bank", "Banca"), ("card", "Card"), ("other", "Altul")]
    STATUS = [("due", "Scadent"), ("paid", "Platit")]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="payments")
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHODS, default="bank")
    status = models.CharField(max_length=10, choices=STATUS, default="due")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["status", "due_date", "-id"]

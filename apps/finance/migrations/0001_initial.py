# Generated manually for initial deployment (Render)
from __future__ import annotations

import decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Partner",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("partner_type", models.CharField(choices=[("supplier", "Furnizor"), ("client", "Client"), ("other", "Altul")], default="other", max_length=20)),
                ("tax_id", models.CharField(blank=True, default="", max_length=50)),
                ("phone", models.CharField(blank=True, default="", max_length=50)),
                ("email", models.CharField(blank=True, default="", max_length=120)),
                ("notes", models.TextField(blank=True, default="")),
            ],
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("kind", models.CharField(choices=[("expense", "Cheltuiala"), ("income", "Venit")], default="expense", max_length=10)),
            ],
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("expense", "Cheltuiala"), ("sale", "Vanzare")], max_length=10)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("approved", "Aprobat"), ("locked", "Blocat")], default="draft", max_length=10)),
                ("doc_no", models.CharField(blank=True, default="", max_length=80)),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("currency", models.CharField(default="RON", max_length=10)),
                ("subtotal", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=14)),
                ("vat", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=14)),
                ("total", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=14)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_documents", to=settings.AUTH_USER_MODEL)),
                ("flock", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="documents", to="core.flock")),
                ("partner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="documents", to="finance.partner")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="documents", to="core.season")),
            ],
            options={
                "ordering": ["-date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="DocumentLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(blank=True, default="", max_length=250)),
                ("qty", models.DecimalField(decimal_places=3, default=decimal.Decimal("1.000"), max_digits=14)),
                ("unit", models.CharField(blank=True, default="", max_length=20)),
                ("unit_price", models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=14)),
                ("line_total", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=14)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="finance.category")),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="finance.document")),
            ],
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("due_date", models.DateField()),
                ("paid_date", models.DateField(blank=True, null=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("method", models.CharField(choices=[("cash", "Cash"), ("bank", "Banca"), ("card", "Card"), ("other", "Altul")], default="bank", max_length=10)),
                ("status", models.CharField(choices=[("due", "Scadent"), ("paid", "Platit")], default="due", max_length=10)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="finance.document")),
            ],
            options={
                "ordering": ["status", "due_date", "-id"],
            },
        ),
    ]

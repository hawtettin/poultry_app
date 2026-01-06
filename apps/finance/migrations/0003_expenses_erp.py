from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_flock_split_initial_counts"),
        ("finance", "0002_payment_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="vat_rate",
            field=models.DecimalField(default=Decimal("0.00"), max_digits=5, decimal_places=2),
        ),
        migrations.AddField(
            model_name="documentline",
            name="house",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="document_lines",
                to="core.house",
            ),
        ),
        migrations.AddField(
            model_name="documentline",
            name="flock",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="document_lines",
                to="core.flock",
            ),
        ),
        migrations.CreateModel(
            name="ExpenseAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="expense_attachments/%Y/%m/")),
                ("original_name", models.CharField(blank=True, default="", max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(on_delete=models.CASCADE, related_name="attachments", to="finance.document"),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-uploaded_at", "-id"],
            },
        ),
    ]

from __future__ import annotations

from datetime import datetime, time

from django.db import migrations, models
import django.utils.timezone


def backfill_payment_created_at(apps, schema_editor):
    """Backfill pentru created_at la Payment.

    Motiv: când adăugăm coloana, Django cere un default pentru rândurile existente.
    Dacă am folosi `timezone.now()`, toate plățile vechi ar părea "create azi",
    ceea ce ar permite angajaților să le editeze în ziua migrării.

    Soluție:
      - pentru plățile existente, setăm created_at = document.created_at (dacă există)
        altfel fallback la due_date (00:00 în timezone local), iar în ultimă instanță now().
    """

    Payment = apps.get_model("finance", "Payment")

    tz = django.utils.timezone.get_current_timezone()

    for p in Payment.objects.select_related("document").all():
        doc = getattr(p, "document", None)
        doc_created_at = getattr(doc, "created_at", None) if doc else None

        if doc_created_at:
            p.created_at = doc_created_at
        else:
            due_date = getattr(p, "due_date", None)
            if due_date:
                naive = datetime.combine(due_date, time(0, 0, 0))
                p.created_at = django.utils.timezone.make_aware(naive, tz)
            else:
                p.created_at = django.utils.timezone.now()

        p.save(update_fields=["created_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_payment_created_at, migrations.RunPython.noop),
    ]

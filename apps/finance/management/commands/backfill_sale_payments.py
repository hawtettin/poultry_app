from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils.dateparse import parse_date

from apps.finance.models import Document, Payment


class Command(BaseCommand):
    """Backfill pentru ledger: creează Payment (paid) pentru vânzări "cash".

    În versiunile anterioare, dacă la vânzare nu era completată "Datorie", nu se crea niciun Payment.
    Ledger-ul (registrul) lista doar Payment-uri, deci acele vânzări nu apăreau.

    Comanda creează câte un Payment status=paid pentru fiecare Document(doc_type=sale)
    care nu are niciun Payment asociat.

    E safe de rulat: nu atinge documentele care au deja plăți.
    """

    help = "Backfill: create paid payments for sale documents that have no payments (cash sales)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nu creează nimic, doar afișează câte documente ar fi afectate.",
        )
        parser.add_argument(
            "--since",
            type=str,
            default="",
            help="Opțional: doar vânzări cu date >= YYYY-MM-DD.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Opțional: limitează numărul de documente procesate.",
        )

    def handle(self, *args, **opts):
        dry_run: bool = bool(opts.get("dry_run"))
        since_raw: str = (opts.get("since") or "").strip()
        limit: int = int(opts.get("limit") or 0)

        since = parse_date(since_raw) if since_raw else None

        qs = (
            Document.objects.filter(doc_type="sale")
            .annotate(pcount=Count("payments"))
            .filter(pcount=0)
        )
        if since:
            qs = qs.filter(date__gte=since)

        qs = qs.order_by("date", "id")
        if limit and limit > 0:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(self.style.WARNING(f"Found {total} sale documents with 0 payments."))
        if total == 0:
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run: no changes applied."))
            return

        created = 0
        skipped = 0
        with transaction.atomic():
            for doc in qs:
                amount = (doc.total or Decimal("0.00")).quantize(Decimal("0.01"))
                if amount <= 0:
                    skipped += 1
                    continue

                Payment.objects.create(
                    document=doc,
                    due_date=doc.date,
                    paid_date=doc.date,
                    amount=amount,
                    method="cash",
                    status="paid",
                    created_by=doc.created_by,
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} payments. Skipped {skipped}."))

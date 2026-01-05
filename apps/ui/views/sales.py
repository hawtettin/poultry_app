from __future__ import annotations

import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.auditlog.utils import log_event, snapshot
from apps.finance.models import Payment
from apps.finance.selectors import SalesFilters, list_sales
from apps.finance.services import mark_payment_paid


@login_required
def sales_export_csv(request):
    """Export CSV pentru vânzări.

    Filtre (GET):
      - sales_from=YYYY-MM-DD
      - sales_to=YYYY-MM-DD
      - sales_buyer=string
      - sales_flock=<id>
      - sales_only_debts=1

    Coloane: DATA, ORA, CUMPĂRĂTOR, PUI ALBI, PUI COLORATI, FURAJ(KG), BANI, DATORIE
    """
    sales_from = parse_date((request.GET.get("sales_from") or "").strip())
    sales_to = parse_date((request.GET.get("sales_to") or "").strip())
    sales_buyer = (request.GET.get("sales_buyer") or "").strip()
    sales_flock = (request.GET.get("sales_flock") or "").strip()
    sales_only_debts = (request.GET.get("sales_only_debts") or "").strip().lower() in {"1", "true", "yes"}

    flock_id = int(sales_flock) if sales_flock.isdigit() else None

    docs = list_sales(
        filters=SalesFilters(
            date_from=sales_from,
            date_to=sales_to,
            buyer_contains=sales_buyer,
            flock_id=flock_id,
            only_debts=sales_only_debts,
        ),
        # For exports we allow more rows
        limit=5000,
    )

    filename = f"vanzari_{timezone.localdate().isoformat()}.csv"
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'

    # Excel-friendly BOM
    resp.write("\ufeff")

    writer = csv.writer(resp, delimiter=";")
    writer.writerow(
        ["DATA", "ORA", "CUMPĂRĂTOR", "PUI ALBI", "PUI COLORATI", "FURAJ(KG)", "BANI", "DATORIE", "SERIE", "HALA"]
    )

    for d in docs:
        ora = timezone.localtime(d.created_at).strftime("%H:%M") if d.created_at else ""
        buyer = d.partner.name if d.partner else ""
        serie = d.flock.season.name if getattr(d, "flock_id", None) else ""
        hala = d.flock.house.name if getattr(d, "flock_id", None) else ""

        writer.writerow(
            [
                d.date.isoformat() if d.date else "",
                ora,
                buyer,
                int(getattr(d, "qty_pui_albi", 0) or 0),
                int(getattr(d, "qty_pui_colorati", 0) or 0),
                str((getattr(d, "qty_furaj", Decimal("0")) or Decimal("0")).quantize(Decimal("0.001"))),
                str((d.total or Decimal("0.00")).quantize(Decimal("0.01"))),
                str((getattr(d, "datorie", Decimal("0.00")) or Decimal("0.00")).quantize(Decimal("0.01"))),
                serie,
                hala,
            ]
        )

    return resp


@login_required
def payment_mark_paid(request, pk: int):
    """Marchează o datorie (Payment status=due) ca fiind plătită."""
    p = get_object_or_404(
        Payment.objects.select_related("document", "document__partner"),
        pk=pk,
    )

    if p.status != "due":
        messages.info(request, "Această înregistrare nu mai este scadentă.")
        return redirect(f"{reverse('ui:dashboard')}?tab=sales")

    if request.method == "POST":
        paid_date = parse_date((request.POST.get("paid_date") or "").strip()) or timezone.localdate()
        method = (request.POST.get("method") or "cash").strip() or "cash"

        mark_payment_paid(payment=p, paid_date=paid_date, method=method)

        log_event(
            actor=request.user,
            action="UPDATE",
            instance=p,
            message=f"PAYMENT paid: #{p.id} ({p.amount} {p.document.currency})",
            before=None,
            after=snapshot(p),
            request=request,
        )
        messages.success(request, "Datoria a fost marcată ca plătită.")

    return redirect(f"{reverse('ui:dashboard')}?tab=sales")

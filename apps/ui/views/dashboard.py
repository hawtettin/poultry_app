from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.core.exceptions import ValidationError

from apps.auditlog.utils import log_event, snapshot
from apps.core.models import Flock
from apps.finance.selectors import (
    SalesFilters,
    debts_by_buyer,
    due_payments,
    list_sales,
    sales_report,
    sold_birds_map,
)
from apps.health.models import MortalityEvent

from ..forms import MortalityQuickAddForm, SaleQuickAddForm
from .utils import WEEKDAYS_RO, can_modify_mortality, is_manager


@login_required
def dashboard(request):
    active_tab = (request.GET.get("tab") or "flocks").strip() or "flocks"

    # Use prefixes to avoid name collisions (e.g., both forms have a "date" field)
    mortality_form = MortalityQuickAddForm(prefix="mort")
    sale_form = SaleQuickAddForm(prefix="sale")

    if request.method == "POST":
        action = (request.POST.get("_action") or "").strip()

        # --------------------
        # Quick-add mortality
        # --------------------
        if action == "add_mortality":
            mortality_form = MortalityQuickAddForm(request.POST, prefix="mort")
            if mortality_form.is_valid():
                m = MortalityEvent.objects.create(
                    flock=mortality_form.cleaned_data["flock"],
                    date=mortality_form.cleaned_data["date"],
                    count=mortality_form.cleaned_data["count"],
                    reason=mortality_form.cleaned_data.get("reason", ""),
                    created_by=request.user,
                )
                log_event(
                    actor=request.user,
                    action="CREATE",
                    instance=m,
                    message=f"CREATE mortalitate: -{m.count} (lot {m.flock_id}) la {m.date}",
                    before=None,
                    after=snapshot(m),
                    request=request,
                )
                messages.success(request, "Mortalitatea a fost salvată (și s-a actualizat numărul curent).")
                return redirect(f"{request.path}?tab=mort")

            messages.error(request, "Nu am putut salva mortalitatea. Verifică datele din formular.")
            active_tab = "mort"

        # -------------
        # Quick-add sale
        # -------------
        elif action == "add_sale":
            sale_form = SaleQuickAddForm(request.POST, prefix="sale")
            if sale_form.is_valid():
                try:
                    doc = sale_form.save(user=request.user)
                except ValidationError as e:
                    # Defensive: service can still raise if something changed meanwhile.
                    sale_form.add_error(None, e)
                    messages.error(request, "Nu am putut salva vânzarea. Verifică datele.")
                    active_tab = "sales"
                else:
                    log_event(
                        actor=request.user,
                        action="CREATE",
                        instance=doc,
                        message=f"CREATE vânzare: doc#{doc.id} ({doc.total} {doc.currency})",
                        before=None,
                        after=snapshot(doc),
                        request=request,
                    )
                    messages.success(request, "Vânzarea a fost salvată.")
                    return redirect(f"{request.path}?tab=sales")
            else:
                messages.error(request, "Nu am putut salva vânzarea. Verifică datele din formular.")
                active_tab = "sales"

    # ---------------------
    # Flocks (current stock)
    # ---------------------
    flocks = (
        Flock.objects.select_related("season", "house")
        .annotate(mortality_total=Coalesce(Sum("mortality_events__count"), 0))
        .order_by("-start_date", "-id")
    )

    sold_map = sold_birds_map(flock_ids=[f.id for f in flocks])

    for f in flocks:
        f.sold_total = sold_map.get(int(f.id), 0)
        f.current_count = max(int(f.initial_count) - int(f.mortality_total or 0) - int(f.sold_total or 0), 0)
        f.mortality_pct = (100.0 * float(f.mortality_total or 0) / float(f.initial_count)) if f.initial_count else 0.0

    # -----------------
    # Mortality (recent)
    # -----------------
    recent_mortalities = (
        MortalityEvent.objects.select_related("flock", "flock__season", "flock__house", "created_by")
        .order_by("-date", "-id")[:40]
    )
    for m in recent_mortalities:
        m.can_modify = can_modify_mortality(request.user, m)

    # -----------------
    # Sales (filters)
    # -----------------
    sales_from = parse_date((request.GET.get("sales_from") or "").strip())
    sales_to = parse_date((request.GET.get("sales_to") or "").strip())
    sales_buyer = (request.GET.get("sales_buyer") or "").strip()
    sales_flock = (request.GET.get("sales_flock") or "").strip()
    sales_only_debts = (request.GET.get("sales_only_debts") or "").strip().lower() in {"1", "true", "yes"}

    flock_id = int(sales_flock) if sales_flock.isdigit() else None

    filters = SalesFilters(
        date_from=sales_from,
        date_to=sales_to,
        buyer_contains=sales_buyer,
        flock_id=flock_id,
        only_debts=sales_only_debts,
    )

    sales_docs = list_sales(filters=filters, limit=100)

    # -----------------
    # Debts
    # -----------------
    debts_rows = debts_by_buyer(limit=30)
    due_rows = due_payments(limit=80)

    # -----------------
    # Quick report
    # -----------------
    today = timezone.localdate()
    report_from = sales_from or (today - timedelta(days=6))
    report_to = sales_to or today

    report = sales_report(date_from=report_from, date_to=report_to)

    today_weekday = WEEKDAYS_RO[today.weekday()]

    return render(
        request,
        "ui/dashboard.html",
        {
            "flocks": flocks,
            "mortality_form": mortality_form,
            "sale_form": sale_form,
            "recent_mortalities": recent_mortalities,
            "sales": sales_docs,
            "debts_by_buyer": debts_rows,
            "due_payments": due_rows,
            "sales_from": sales_from,
            "sales_to": sales_to,
            "sales_buyer": sales_buyer,
            "sales_flock": sales_flock,
            "sales_only_debts": sales_only_debts,
            "report_from": report.date_from,
            "report_to": report.date_to,
            "report_total_sales": report.total_sales,
            "report_total_debts": report.total_debts,
            "report_pui_total": report.pui_total,
            "report_furaj": report.furaj_total,
            "top_buyers": report.top_buyers,
            "top_debtors": report.top_debtors,
            "active_tab": active_tab,
            "today": today,
            "today_weekday": today_weekday,
            "is_manager": is_manager(request.user),
        },
    )

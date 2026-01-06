from __future__ import annotations

import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.utils import is_admin, is_manager, is_employee_or_above
from apps.auditlog.models import AuditEvent
from apps.auditlog.utils import log_event, snapshot
from apps.core.models import Flock
from apps.finance.models import Document, DocumentLine, Payment
from apps.health.models import MortalityEvent

from .forms import (
    CreateSeriesForm,
    MortalityQuickAddForm,
    MortalityEditForm,
    SaleQuickAddForm,
    SaleDocumentForm,
    SaleLineFormSet,
    UserProvisionForm,
)


WEEKDAYS_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]


def can_modify_mortality(user, m: MortalityEvent) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if is_manager(user):
        return True
    # employee: doar ce a creat el
    return (m.created_by_id is not None) and (m.created_by_id == user.id)


@login_required
def dashboard(request):
    """Dashboard + quick add mortalitate."""

    # Quick-add mortalitate din tab
    if request.method == "POST" and request.POST.get("_action") == "add_mortality":
        mortality_form = MortalityQuickAddForm(request.POST)
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
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva. Verifică datele din formular.")
    else:
        mortality_form = MortalityQuickAddForm()

    flocks = (
        Flock.objects.select_related("season", "house")
        .annotate(mortality_total=Coalesce(Sum("mortality_events__count"), 0))
        .order_by("-start_date", "-id")
    )
    for f in flocks:
        f.current_count = max(int(f.initial_count) - int(f.mortality_total or 0), 0)
        f.mortality_pct = (100.0 * float(f.mortality_total or 0) / float(f.initial_count)) if f.initial_count else 0.0

    recent = (
        MortalityEvent.objects.select_related("flock", "flock__season", "flock__house", "created_by")
        .order_by("-date", "-id")[:40]
    )
    # pregatim in template daca user poate modifica
    for m in recent:
        m.can_modify = can_modify_mortality(request.user, m)

    today = timezone.localdate()
    today_weekday = WEEKDAYS_RO[today.weekday()]

    return render(
        request,
        "ui/dashboard.html",
        {
            "flocks": flocks,
            "mortality_form": mortality_form,
            "recent_mortalities": recent,
            "today": today,
            "today_weekday": today_weekday,
        },
    )


@login_required
def create_series(request):
    if not is_manager(request.user):
        messages.error(request, "Nu ai permisiuni să creezi serii/loturi. Cere acces de la administrator.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        form = CreateSeriesForm(request.POST)
        if form.is_valid():
            season, flock = form.save()

            # audit (2 evenimente, pentru sezon si pentru flock)
            log_event(
                actor=request.user,
                action="CREATE",
                instance=season,
                message=f"CREATE sezon: {season.name}",
                after=snapshot(season),
                request=request,
            )
            log_event(
                actor=request.user,
                action="CREATE",
                instance=flock,
                message=f"CREATE lot: sezon={season.name}, hala={flock.house.name}, initial={flock.initial_count}",
                after=snapshot(flock),
                request=request,
            )

            messages.success(
                request,
                f"Serie creată: {season.name}. Lot nou în {flock.house.name} cu {flock.initial_count} capete.",
            )
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva seria. Verifică formularul.")
    else:
        form = CreateSeriesForm()

    return render(request, "ui/create_series.html", {"form": form})


@login_required
def mortality_edit(request, pk: int):
    m = get_object_or_404(MortalityEvent.objects.select_related("flock", "created_by"), pk=pk)
    if not can_modify_mortality(request.user, m):
        messages.error(request, "Nu ai drepturi să editezi această înregistrare.")
        return redirect("ui:dashboard")

    before = snapshot(m)

    if request.method == "POST":
        form = MortalityEditForm(request.POST, instance=m)
        if form.is_valid():
            m2 = form.save()
            after = snapshot(m2)
            log_event(
                actor=request.user,
                action="UPDATE",
                instance=m2,
                message=f"UPDATE mortalitate #{m2.id}: {before.get('count')} -> {after.get('count')}",
                before=before,
                after=after,
                request=request,
            )
            messages.success(request, "Mortalitatea a fost actualizată.")
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva modificările. Verifică formularul.")
    else:
        form = MortalityEditForm(instance=m)

    return render(request, "ui/mortality_edit.html", {"form": form, "m": m})


@login_required
def mortality_delete(request, pk: int):
    m = get_object_or_404(MortalityEvent.objects.select_related("flock", "created_by"), pk=pk)
    if not can_modify_mortality(request.user, m):
        messages.error(request, "Nu ai drepturi să ștergi această înregistrare.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        before = snapshot(m)
        mid = m.id
        m.delete()
        # log dupa delete (pastram object_id si inainte)
        class Dummy:  # doar ca sa avem meta label ok
            _meta = type("M", (), {"app_label": "health", "model_name": "mortalityevent"})()
            pk = mid

        dummy = Dummy()
        log_event(
            actor=request.user,
            action="DELETE",
            instance=dummy,
            message=(
                f"DELETE mortalitate #{mid}: -{before.get('count')} (lot {before.get('flock')}) "
                f"la {before.get('date')}"
            ),
            before=before,
            after=None,
            request=request,
        )
        messages.success(request, "Înregistrarea a fost ștearsă.")
        return redirect("ui:dashboard")

    return render(request, "ui/mortality_confirm_delete.html", {"m": m})


@login_required
def history(request):
    # employee vede doar istoricul lui; manager/admin vede tot
    qs = AuditEvent.objects.select_related("actor").all()
    if not is_manager(request.user):
        qs = qs.filter(actor=request.user)

    qs = qs.order_by("-created_at", "-id")[:300]
    return render(request, "ui/history.html", {"events": qs})


# =============================================================
# Sales UI (Document doc_type="sale")
# =============================================================


def _sale_snapshot(doc: Document) -> dict:
    data = snapshot(doc)
    data["lines"] = list(
        doc.lines.all().values(
            "id",
            "category_id",
            "description",
            "qty",
            "unit",
            "unit_price",
            "line_total",
        )
    )
    return data



@login_required
def sales_quick(request):
    """Pagina clasică de vânzări (înregistrare rapidă + rapoarte).

    Păstrează /sales/ ca ledger, dar oferă o interfață rapidă pentru înregistrare,
    similară cu versiunea veche a aplicației.
    """
    can_create = is_employee_or_above(request.user)
    can_advanced = is_manager(request.user) or is_admin(request.user)
    can_payments = is_manager(request.user) or is_admin(request.user)

    if not can_create:
        messages.error(request, "Nu ai permisiuni să înregistrezi vânzări.")
        return redirect("ui:sales_list")

    sale_form = SaleQuickAddForm(prefix="sale")
    if request.method == "POST" and request.POST.get("_action") == "add_sale":
        sale_form = SaleQuickAddForm(request.POST, prefix="sale")
        if sale_form.is_valid():
            doc = sale_form.save(user=request.user)
            log_event(
                actor=request.user,
                action="CREATE",
                instance=doc,
                message=f"CREATE vânzare (rapid): doc#{doc.id} ({doc.total} {doc.currency})",
                before=None,
                after=snapshot(doc),
                request=request,
            )
            messages.success(request, "Vânzarea a fost salvată.")
            return redirect("ui:sales_quick")

        messages.error(request, "Nu am putut salva vânzarea. Verifică datele din formular.")

    # -------------------------
    # Filtre listă vânzări
    # -------------------------
    sales_from = parse_date((request.GET.get("sales_from") or "").strip())
    sales_to = parse_date((request.GET.get("sales_to") or "").strip())
    sales_buyer = (request.GET.get("sales_buyer") or "").strip()
    sales_flock = (request.GET.get("sales_flock") or "").strip()
    sales_only_debts = (request.GET.get("sales_only_debts") or "").strip() in ["1", "true", "on", "yes"]

    flocks = (
        Flock.objects.select_related("season", "house")
        .order_by("-start_date", "-id")
    )

    sales_qs = (
        Document.objects.filter(doc_type="sale")
        .select_related("partner", "flock", "flock__season", "flock__house")
        .prefetch_related("lines", "payments")
    )

    if sales_from:
        sales_qs = sales_qs.filter(date__gte=sales_from)
    if sales_to:
        sales_qs = sales_qs.filter(date__lte=sales_to)
    if sales_buyer:
        sales_qs = sales_qs.filter(partner__name__icontains=sales_buyer)
    if sales_flock:
        try:
            sales_qs = sales_qs.filter(flock_id=int(sales_flock))
        except ValueError:
            pass
    if sales_only_debts:
        sales_qs = sales_qs.filter(payments__status="due").distinct()

    sales_docs = list(sales_qs.order_by("-date", "-id")[:100])

    def _sum_qty(doc: Document, *, keys: set[str]) -> Decimal:
        total = Decimal("0")
        for ln in getattr(doc, "lines", []).all():
            desc = (ln.description or "").strip().lower()
            if desc in keys:
                total += (ln.qty or Decimal("0"))
        return total

    for d in sales_docs:
        d.qty_pui_albi = int(_sum_qty(d, keys={"pui albi"}) or 0)
        d.qty_pui_colorati = int(_sum_qty(d, keys={"pui colorați", "pui colorati"}) or 0)
        d.qty_furaj = (_sum_qty(d, keys={"furaj"}) or Decimal("0")).quantize(Decimal("0.001"))
        d.datorie = (
            sum((p.amount for p in d.payments.all() if p.status == "due"), Decimal("0.00"))
        ).quantize(Decimal("0.01"))

    # -------------------------
    # Datorii / plăți
    # -------------------------
    due_payments = (
        Payment.objects.filter(status="due")
        .select_related("document", "document__partner")
        .order_by("due_date", "-id")[:50]
    )

    debts_by_buyer = (
        Payment.objects.filter(status="due")
        .values("document__partner__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:20]
    )

    # -------------------------
    # Raport rapid (implicit: ultimele 7 zile sau range-ul din filtre)
    # -------------------------
    today = timezone.localdate()
    report_from = sales_from or (today - timedelta(days=6))
    report_to = sales_to or today

    report_docs = Document.objects.filter(doc_type="sale", date__gte=report_from, date__lte=report_to)
    report_total_sales = (report_docs.aggregate(s=Sum("total"))["s"] or Decimal("0.00")).quantize(Decimal("0.01"))
    report_total_debts = (
        Payment.objects.filter(status="due", document__in=report_docs)
        .aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    ).quantize(Decimal("0.01"))

    report_pui_albi = (
        DocumentLine.objects.filter(document__in=report_docs)
        .filter(description__iexact="Pui albi")
        .aggregate(s=Sum("qty"))["s"]
        or Decimal("0")
    )
    report_pui_colorati = (
        DocumentLine.objects.filter(document__in=report_docs)
        .filter(Q(description__iexact="Pui colorați") | Q(description__iexact="Pui colorati"))
        .aggregate(s=Sum("qty"))["s"]
        or Decimal("0")
    )
    report_furaj = (
        DocumentLine.objects.filter(document__in=report_docs)
        .filter(description__iexact="Furaj")
        .aggregate(s=Sum("qty"))["s"]
        or Decimal("0")
    )

    report_pui_total = int(report_pui_albi or 0) + int(report_pui_colorati or 0)
    report_furaj = (report_furaj or Decimal("0")).quantize(Decimal("0.001"))

    top_buyers = (
        report_docs.values("partner__name")
        .annotate(total=Sum("total"))
        .order_by("-total")[:7]
    )

    top_debtors = (
        Payment.objects.filter(status="due", document__doc_type="sale", document__date__gte=report_from, document__date__lte=report_to)
        .values("document__partner__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:7]
    )

    return render(
        request,
        "ui/sales_quick.html",
        {
            "sale_form": sale_form,
            "sales": sales_docs,
            "flocks": flocks,
            "sales_from": sales_from,
            "sales_to": sales_to,
            "sales_buyer": sales_buyer,
            "sales_flock": int(sales_flock) if sales_flock.isdigit() else None,
            "sales_only_debts": sales_only_debts,
            "due_payments": due_payments,
            "debts_by_buyer": debts_by_buyer,
            "today": today,
            "report_from": report_from,
            "report_to": report_to,
            "report_total_sales": report_total_sales,
            "report_total_debts": report_total_debts,
            "report_pui_total": report_pui_total,
            "report_furaj": report_furaj,
            "top_buyers": top_buyers,
            "top_debtors": top_debtors,
            "can_advanced": can_advanced,
            "can_payments": can_payments,
        },
    )


@login_required
def sales_export_csv(request):
    """Export CSV pentru vânzări (folosește aceleași filtre ca pagina rapidă)."""
    sales_from = parse_date((request.GET.get("sales_from") or "").strip())
    sales_to = parse_date((request.GET.get("sales_to") or "").strip())
    sales_buyer = (request.GET.get("sales_buyer") or "").strip()
    sales_flock = (request.GET.get("sales_flock") or "").strip()
    sales_only_debts = (request.GET.get("sales_only_debts") or "").strip() in ["1", "true", "on", "yes"]

    sales_qs = (
        Document.objects.filter(doc_type="sale")
        .select_related("partner", "flock")
        .prefetch_related("lines", "payments")
    )
    if sales_from:
        sales_qs = sales_qs.filter(date__gte=sales_from)
    if sales_to:
        sales_qs = sales_qs.filter(date__lte=sales_to)
    if sales_buyer:
        sales_qs = sales_qs.filter(partner__name__icontains=sales_buyer)
    if sales_flock:
        try:
            sales_qs = sales_qs.filter(flock_id=int(sales_flock))
        except ValueError:
            pass
    if sales_only_debts:
        sales_qs = sales_qs.filter(payments__status="due").distinct()

    docs = list(sales_qs.order_by("-date", "-id")[:2000])

    def _sum_qty(doc: Document, *, keys: set[str]) -> Decimal:
        total = Decimal("0")
        for ln in getattr(doc, "lines", []).all():
            desc = (ln.description or "").strip().lower()
            if desc in keys:
                total += (ln.qty or Decimal("0"))
        return total

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="vanzari.csv"'
    writer = csv.writer(response)
    writer.writerow(["DATA", "ORA", "CUMPARĂTOR", "PUI_ALBI", "PUI_COLORATI", "FURAJ_KG", "BANI", "DATORIE"])

    for d in docs:
        pui_albi = int(_sum_qty(d, keys={"pui albi"}) or 0)
        pui_colorati = int(_sum_qty(d, keys={"pui colorați", "pui colorati"}) or 0)
        furaj = (_sum_qty(d, keys={"furaj"}) or Decimal("0")).quantize(Decimal("0.001"))
        datorie = (
            sum((p.amount for p in d.payments.all() if p.status == "due"), Decimal("0.00"))
        ).quantize(Decimal("0.01"))
        ora = d.created_at.strftime("%H:%M") if getattr(d, "created_at", None) else ""
        writer.writerow([
            str(d.date),
            ora,
            (d.partner.name if d.partner_id else ""),
            str(pui_albi),
            str(pui_colorati),
            str(furaj),
            str(d.total),
            str(datorie),
        ])

    return response


@login_required
def payment_mark_paid(request, pk: int):
    """Marchează o datorie (Payment status=due) ca fiind plătită."""
    if not (is_manager(request.user) or is_admin(request.user)):
        messages.error(request, "Nu ai permisiuni să marchezi plăți ca fiind plătite.")
        return redirect("ui:sales_quick")

    p = get_object_or_404(
        Payment.objects.select_related("document", "document__partner"),
        pk=pk,
    )

    if p.status != "due":
        messages.info(request, "Această înregistrare nu mai este scadentă.")
        return redirect("ui:sales_quick")

    if request.method == "POST":
        paid_date = parse_date((request.POST.get("paid_date") or "").strip()) or timezone.localdate()
        method = (request.POST.get("method") or "cash").strip() or "cash"
        p.status = "paid"
        p.paid_date = paid_date
        p.method = method
        p.save(update_fields=["status", "paid_date", "method"])

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

    return redirect("ui:sales_quick")


@login_required
def sales_list(request):
    qs = (
        Document.objects.filter(doc_type="sale")
        .select_related("season", "flock", "partner")
        .order_by("-date", "-id")
    )
    can_modify = is_manager(request.user)

    return render(
        request,
        "ui/sales_list.html",
        {
            "sales": qs,
            "can_modify": can_modify,
        },
    )


@login_required
def sale_create(request):
    if not is_manager(request.user):
        messages.error(request, "Nu ai permisiuni să creezi/editezi vânzări.")
        return redirect("ui:sales_list")

    sale = Document(doc_type="sale", status="draft")

    if request.method == "POST":
        form = SaleDocumentForm(request.POST, instance=sale)
        formset = SaleLineFormSet(request.POST, instance=sale)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                sale = form.save(commit=False)
                sale.doc_type = "sale"
                sale.created_by = request.user
                sale.save()
                formset.instance = sale
                formset.save()
                sale.recalc_totals()
                sale.save(update_fields=["subtotal", "total"])

            log_event(
                actor=request.user,
                action="CREATE",
                instance=sale,
                message=f"CREATE vânzare #{sale.id} ({sale.doc_no or 'fără număr'})",
                after=_sale_snapshot(sale),
                request=request,
            )
            messages.success(request, "Vânzarea a fost creată.")
            return redirect("ui:sales_list")

        messages.error(request, "Nu am putut salva vânzarea. Verifică formularul.")
    else:
        form = SaleDocumentForm(instance=sale)
        formset = SaleLineFormSet(instance=sale)

    return render(
        request,
        "ui/sale_form.html",
        {
            "form": form,
            "formset": formset,
            "sale": sale,
            "mode": "create",
        },
    )


@login_required
def sale_edit(request, pk: int):
    sale = get_object_or_404(
        Document.objects.filter(doc_type="sale")
        .select_related("season", "flock", "partner")
        .prefetch_related("lines"),
        pk=pk,
    )

    if not is_manager(request.user):
        messages.error(request, "Nu ai permisiuni să editezi vânzări.")
        return redirect("ui:sales_list")

    if sale.status == "locked":
        messages.error(request, "Documentul este blocat (locked) și nu poate fi modificat.")
        return redirect("ui:sales_list")

    before = _sale_snapshot(sale)

    if request.method == "POST":
        form = SaleDocumentForm(request.POST, instance=sale)
        formset = SaleLineFormSet(request.POST, instance=sale)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                sale = form.save()
                formset.save()
                sale.recalc_totals()
                sale.save(update_fields=["subtotal", "total"])

            after = _sale_snapshot(sale)
            log_event(
                actor=request.user,
                action="UPDATE",
                instance=sale,
                message=f"UPDATE vânzare #{sale.id} ({sale.doc_no or 'fără număr'})",
                before=before,
                after=after,
                request=request,
            )
            messages.success(request, "Vânzarea a fost actualizată.")
            return redirect("ui:sales_list")

        messages.error(request, "Nu am putut salva modificările. Verifică formularul.")
    else:
        form = SaleDocumentForm(instance=sale)
        formset = SaleLineFormSet(instance=sale)

    return render(
        request,
        "ui/sale_form.html",
        {
            "form": form,
            "formset": formset,
            "sale": sale,
            "mode": "edit",
        },
    )


@login_required
def sale_delete(request, pk: int):
    sale = get_object_or_404(Document.objects.filter(doc_type="sale"), pk=pk)

    if not is_manager(request.user):
        messages.error(request, "Nu ai permisiuni să ștergi vânzări.")
        return redirect("ui:sales_list")

    if sale.status == "locked":
        messages.error(request, "Documentul este blocat (locked) și nu poate fi șters.")
        return redirect("ui:sales_list")

    if request.method == "POST":
        before = _sale_snapshot(sale)
        sid = sale.id
        sale.delete()

        # log after delete (keep object_id)
        class Dummy:
            _meta = type("M", (), {"app_label": "finance", "model_name": "document"})()
            pk = sid

        dummy = Dummy()
        log_event(
            actor=request.user,
            action="DELETE",
            instance=dummy,
            message=f"DELETE vânzare #{sid}",
            before=before,
            after=None,
            request=request,
        )

        messages.success(request, "Vânzarea a fost ștearsă.")
        return redirect("ui:sales_list")

    return render(request, "ui/sale_confirm_delete.html", {"sale": sale})


# =============================================================
# Admin users UI
# =============================================================


def _safe_user_snapshot(u) -> dict:
    return {
        "id": u.id,
        "username": getattr(u, "username", ""),
        "first_name": getattr(u, "first_name", ""),
        "last_name": getattr(u, "last_name", ""),
        "email": getattr(u, "email", ""),
        "is_active": getattr(u, "is_active", False),
        "is_staff": getattr(u, "is_staff", False),
        "is_superuser": getattr(u, "is_superuser", False),
        "groups": list(u.groups.values_list("name", flat=True)),
    }


@login_required
def users_list(request):
    if not is_admin(request.user):
        messages.error(request, "Nu ai permisiuni pentru administrarea utilizatorilor.")
        return redirect("ui:dashboard")

    User = get_user_model()
    users = User.objects.all().prefetch_related("groups").order_by("username")

    return render(request, "ui/users_list.html", {"users": users})


@login_required
def user_create(request):
    if not is_admin(request.user):
        messages.error(request, "Nu ai permisiuni pentru administrarea utilizatorilor.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        form = UserProvisionForm(request.POST)
        if form.is_valid():
            user = form.save()

            log_event(
                actor=request.user,
                action="CREATE",
                instance=user,
                message=f"CREATE user #{user.id}: {user.username}",
                after=_safe_user_snapshot(user),
                request=request,
            )

            messages.success(request, f"Utilizator creat: {user.username}")
            return redirect("ui:users_list")

        messages.error(request, "Nu am putut crea utilizatorul. Verifică formularul.")
    else:
        form = UserProvisionForm()

    return render(request, "ui/user_create.html", {"form": form})

from __future__ import annotations

import csv
from io import BytesIO

import openpyxl
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum, Count
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from apps.core.models import Flock
from apps.health.models import MortalityEvent
from apps.auditlog.utils import log_event, snapshot
from apps.auditlog.models import AuditEvent
from apps.finance.models import Document, DocumentLine, Payment

from .forms import (
    CreateSeriesForm,
    FlockEditForm,
    MortalityQuickAddForm,
    MortalityEditForm,
    SaleQuickAddForm,
    StaffUserCreateForm,
    PaymentEditForm,
)


WEEKDAYS_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]

def is_manager(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["ADMIN", "MANAGER"]).exists()


def is_admin(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name="ADMIN").exists()


def can_modify_mortality(user, m: MortalityEvent) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or is_manager(user):
        return True
    # employee: doar ce a creat el
    return (m.created_by_id is not None) and (m.created_by_id == user.id)


def can_modify_payment(user, p: Payment) -> bool:
    """Permisiuni UI pentru edit/ștergere/mark-paid la Payment.

    - ADMIN/MANAGER/superuser: orice plată.
    - EMPLOYEE: doar plățile create de el și doar în ziua curentă (după created_at).
    """

    if not getattr(user, "is_authenticated", False):
        return False

    if is_manager(user):
        return True

    # EMPLOYEE: doar ale lui
    if not user.groups.filter(name="EMPLOYEE").exists():
        return False

    if getattr(p, "created_by_id", None) != user.id:
        return False

    created_at = getattr(p, "created_at", None)
    if not created_at:
        return False

    try:
        created_day = timezone.localtime(created_at).date()
    except Exception:
        # dacă USE_TZ=False (datetime naive)
        created_day = created_at.date()
    return created_day == timezone.localdate()


def can_modify_sale(user, d: Document) -> bool:
    """Permisiuni UI pentru ștergere vânzare (Document doc_type='sale').

    - ADMIN/MANAGER/superuser: orice vânzare.
    - EMPLOYEE: doar vânzările create de el și doar în ziua curentă (după created_at).

    Notă: nu permitem ștergere pentru documente non-sale prin acest helper.
    """

    if not getattr(user, "is_authenticated", False):
        return False

    # doar pentru vânzări
    if getattr(d, "doc_type", None) != "sale":
        return False

    if is_manager(user):
        return True

    # EMPLOYEE: doar ale lui
    if not user.groups.filter(name="EMPLOYEE").exists():
        return False

    if getattr(d, "created_by_id", None) != user.id:
        return False

    created_at = getattr(d, "created_at", None)
    if not created_at:
        return False

    try:
        created_day = timezone.localtime(created_at).date()
    except Exception:
        created_day = created_at.date()

    return created_day == timezone.localdate()


def safe_next_url(request, default: str) -> str:
    """Returnează un next URL safe (doar intern), altfel default."""

    nxt = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if nxt and url_has_allowed_host_and_scheme(
        url=nxt,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return nxt
    return default


@never_cache
@login_required
def dashboard(request):
    active_tab = (request.GET.get("tab") or "flocks").strip() or "flocks"

    # Folosim prefix-uri ca să evităm coliziuni (ex: ambele formulare au câmpul "date")
    mortality_form = MortalityQuickAddForm(prefix="mort")
    sale_form = SaleQuickAddForm(prefix="sale")

    if request.method == "POST":
        action = (request.POST.get("_action") or "").strip()

        # --------------------
        # Quick-add mortalitate
        # --------------------
        if action == "add_mortality":
            mortality_form = MortalityQuickAddForm(request.POST, prefix="mort")
            if mortality_form.is_valid():
                m = MortalityEvent.objects.create(
                    flock=mortality_form.cleaned_data["flock"],
                    date=mortality_form.cleaned_data["date"],
                    poultry_type=mortality_form.cleaned_data.get("poultry_type") or "white",
                    count=mortality_form.cleaned_data["count"],
                    reason=mortality_form.cleaned_data.get("reason", ""),
                    created_by=request.user,
                )
                log_event(
                    actor=request.user,
                    action="CREATE",
                    instance=m,
                    message=f"CREATE mortalitate: -{m.count} ({m.get_poultry_type_display()}) (lot {m.flock_id}) la {m.date}",
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
                doc = sale_form.save(user=request.user)
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
            messages.error(request, "Nu am putut salva vânzarea. Verifică datele din formular.")
            active_tab = "sales"

    flocks = (
        Flock.objects.select_related("season", "house")
        .annotate(mortality_total=Coalesce(Sum("mortality_events__count"), 0))
        .order_by("-start_date", "-id")
    )

    # Mortalitate pe tip (pui albi / pui colorați)
    mort_rows = (
        MortalityEvent.objects
        .values("flock_id", "poultry_type")
        .annotate(s=Sum("count"))
    )
    mort_map = {
        (int(r["flock_id"]), str(r["poultry_type"])): int(r["s"] or 0)
        for r in mort_rows
    }

    # Vânzări pe tip (derivate din description; păstrăm compatibilitate cu datele existente)
    sold_white_rows = (
        DocumentLine.objects
        .filter(document__doc_type="sale", document__flock__isnull=False)
        .filter(description__iexact="Pui albi")
        .values("document__flock")
        .annotate(s=Sum("qty"))
    )
    sold_colored_rows = (
        DocumentLine.objects
        .filter(document__doc_type="sale", document__flock__isnull=False)
        .filter(Q(description__iexact="Pui colorați") | Q(description__iexact="Pui colorati"))
        .values("document__flock")
        .annotate(s=Sum("qty"))
    )

    sold_white_map = {int(r["document__flock"]): int(r["s"] or 0) for r in sold_white_rows}
    sold_colored_map = {int(r["document__flock"]): int(r["s"] or 0) for r in sold_colored_rows}

    for f in flocks:
        # inventar inițial pe tip (fallback pentru loturi vechi)
        init_white = int(getattr(f, "initial_white_count", 0) or 0)
        init_colored = int(getattr(f, "initial_colored_count", 0) or 0)
        if (init_white + init_colored) <= 0:
            init_white = int(getattr(f, "initial_count", 0) or 0)
            init_colored = 0
        init_total = int(init_white + init_colored)

        # mortalitate / vânzări pe tip
        mort_white = mort_map.get((int(f.id), "white"), 0)
        mort_colored = mort_map.get((int(f.id), "colored"), 0)
        sold_white = sold_white_map.get(int(f.id), 0)
        sold_colored = sold_colored_map.get(int(f.id), 0)

        # expunem în template
        f.initial_total = init_total
        f.initial_white = init_white
        f.initial_colored = init_colored

        f.mortality_white = mort_white
        f.mortality_colored = mort_colored
        f.mortality_total = int(mort_white + mort_colored)

        f.sold_white = sold_white
        f.sold_colored = sold_colored
        f.sold_total = int(sold_white + sold_colored)

        f.current_white = max(int(init_white) - int(mort_white) - int(sold_white), 0)
        f.current_colored = max(int(init_colored) - int(mort_colored) - int(sold_colored), 0)
        f.current_count = int(f.current_white + f.current_colored)

        f.mortality_pct = (100.0 * float(f.mortality_total) / float(init_total)) if init_total else 0.0

    recent = (
        MortalityEvent.objects.select_related("flock", "flock__season", "flock__house", "created_by")
        .order_by("-date", "-id")[:40]
    )
    # pregatim in template daca user poate modifica
    for m in recent:
        m.can_modify = can_modify_mortality(request.user, m)

    # -----------------
    # Vânzări (listare)
    # -----------------
    sales_from = parse_date((request.GET.get("sales_from") or "").strip())
    sales_to = parse_date((request.GET.get("sales_to") or "").strip())
    sales_buyer = (request.GET.get("sales_buyer") or "").strip()
    sales_flock = (request.GET.get("sales_flock") or "").strip()
    sales_only_debts = (request.GET.get("sales_only_debts") or "").strip() in ("1", "true", "True", "yes")
    sales_include_orphans = (request.GET.get("sales_include_orphans") or "").strip() in ("1", "true", "True", "yes")

    # Implicit, ascundem "orfanele" (vânzări care nu mai au plăți), dar le putem afișa la cerere.
    sales_qs = (
        Document.objects.filter(doc_type="sale")
        .select_related("flock", "flock__season", "flock__house", "partner")
        .prefetch_related("lines", "payments")
    )
    if not sales_include_orphans:
        sales_qs = sales_qs.filter(payments__isnull=False).distinct()
    if sales_from:
        sales_qs = sales_qs.filter(date__gte=sales_from)
    if sales_to:
        sales_qs = sales_qs.filter(date__lte=sales_to)
    if sales_buyer:
        sales_qs = sales_qs.filter(partner__name__icontains=sales_buyer)
    if sales_flock.isdigit():
        sales_qs = sales_qs.filter(flock_id=int(sales_flock))
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
        d.qty_furaj = _sum_qty(d, keys={"furaj"}).quantize(Decimal("0.001"))
        d.datorie = sum((p.amount for p in d.payments.all() if p.status == "due"), Decimal("0.00")).quantize(Decimal("0.01"))
        d.bani = sum((p.amount for p in d.payments.all() if p.status == "paid"), Decimal("0.00")).quantize(Decimal("0.01"))
        try:
            d.is_orphan = len(list(d.payments.all())) == 0
        except Exception:
            d.is_orphan = False
        d.can_delete = can_modify_sale(request.user, d)

    # -----------------
    # Datorii pe cumpărător
    # -----------------
    debts_by_buyer = (
        Payment.objects.filter(status="due", document__doc_type="sale")
        .values("document__partner_id", "document__partner__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:30]
    )

    due_payments_qs = (
        Payment.objects.filter(status="due", document__doc_type="sale")
        .select_related(
            "document",
            "document__partner",
            "document__flock",
            "document__flock__season",
            "document__flock__house",
            "created_by",
        )
        .order_by("due_date", "id")[:80]
    )
    due_payments = list(due_payments_qs)
    for p in due_payments:
        p.can_modify = can_modify_payment(request.user, p)

    # -----------------
    # Raport rapid
    # -----------------
    today = timezone.localdate()
    report_from = sales_from or (today - timezone.timedelta(days=6) if hasattr(timezone, "timedelta") else today)
    report_to = sales_to or today
    # dacă nu există timezone.timedelta (în unele versiuni), importăm din datetime
    if not hasattr(timezone, "timedelta"):
        from datetime import timedelta
        report_from = sales_from or (today - timedelta(days=6))

    report_payments = Payment.objects.filter(
        document__doc_type="sale",
        document__date__gte=report_from,
        document__date__lte=report_to,
    )

    report_total_sales = (report_payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")).quantize(Decimal("0.01"))
    report_total_debts = (
        report_payments.filter(status="due").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    ).quantize(Decimal("0.01"))

    report_doc_ids = list(report_payments.values_list("document_id", flat=True).distinct())

    report_pui_albi = DocumentLine.objects.filter(document_id__in=report_doc_ids).filter(
        description__iexact="Pui albi"
    ).aggregate(s=Sum("qty"))["s"] or Decimal("0")

    report_pui_colorati = DocumentLine.objects.filter(document_id__in=report_doc_ids).filter(
        Q(description__iexact="Pui colorați") | Q(description__iexact="Pui colorati")
    ).aggregate(s=Sum("qty"))["s"] or Decimal("0")

    report_furaj = DocumentLine.objects.filter(document_id__in=report_doc_ids).filter(
        description__iexact="Furaj"
    ).aggregate(s=Sum("qty"))["s"] or Decimal("0")

    report_pui_total = int(report_pui_albi or 0) + int(report_pui_colorati or 0)
    report_furaj = (report_furaj or Decimal("0")).quantize(Decimal("0.001"))

    top_buyers = (
        report_payments.filter(status="paid")
        .values("document__partner__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:7]
    )

    top_debtors = (
        report_payments.filter(status="due")
        .values("document__partner__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:7]
    )

    today_weekday = WEEKDAYS_RO[today.weekday()]

    return render(request, "ui/dashboard.html", {
        "flocks": flocks,
        "mortality_form": mortality_form,
        "sale_form": sale_form,
        "recent_mortalities": recent,
        "sales": sales_docs,
        "debts_by_buyer": debts_by_buyer,
        "due_payments": due_payments,
        "sales_from": sales_from,
        "sales_to": sales_to,
        "sales_buyer": sales_buyer,
        "sales_flock": sales_flock,
        "sales_only_debts": sales_only_debts,
        "sales_include_orphans": sales_include_orphans,
        "report_from": report_from,
        "report_to": report_to,
        "report_total_sales": report_total_sales,
        "report_total_debts": report_total_debts,
        "report_pui_total": report_pui_total,
        "report_furaj": report_furaj,
        "top_buyers": top_buyers,
        "top_debtors": top_debtors,
        "active_tab": active_tab,
        "today": today,
        "today_weekday": today_weekday,
        "is_manager": is_manager(request.user),
    })


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

            messages.success(request, f"Serie creată: {season.name}. Lot nou în {flock.house.name} cu {flock.initial_count} capete.")
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva seria. Verifică formularul.")
    else:
        form = CreateSeriesForm()

    return render(request, "ui/create_series.html", {"form": form})


@login_required
def flock_edit(request, pk: int):
    """Editare lot: defalcare inițială pui albi / pui colorați.

    Doar MANAGER/ADMIN/superuser.
    """

    if not is_manager(request.user):
        messages.error(request, "Nu ai permisiuni să editezi loturi. Cere acces de la administrator.")
        return redirect("ui:dashboard")

    flock = get_object_or_404(Flock.objects.select_related("season", "house"), pk=pk)
    before = snapshot(flock)

    if request.method == "POST":
        form = FlockEditForm(request.POST, instance=flock)
        if form.is_valid():
            f2 = form.save()
            after = snapshot(f2)
            log_event(
                actor=request.user,
                action="UPDATE",
                instance=f2,
                message=(
                    f"UPDATE lot #{f2.id}: inițial_albi={before.get('initial_white_count')} -> {after.get('initial_white_count')}, "
                    f"inițial_colorați={before.get('initial_colored_count')} -> {after.get('initial_colored_count')}"
                ),
                before=before,
                after=after,
                request=request,
            )
            messages.success(request, "Lotul a fost actualizat.")
            return redirect("ui:dashboard")
        messages.error(request, "Nu am putut salva modificările. Verifică formularul.")
    else:
        form = FlockEditForm(instance=flock)

    return render(request, "ui/flock_edit.html", {"form": form, "flock": flock})


@login_required
def users_list(request):
    """Listă utilizatori (angajați + manageri).

    Doar ADMIN (sau superuser) poate vedea această pagină.
    """

    if not is_admin(request.user):
        messages.error(request, "Nu ai permisiuni să vezi lista de utilizatori.")
        return redirect("ui:dashboard")

    User = get_user_model()

    qs = (
        User.objects.filter(groups__name__in=["EMPLOYEE", "MANAGER"])
        .distinct()
        .order_by("username")
    )
    users = list(qs)

    # adăugăm un label simplu pentru rol (pentru tabel)
    for u in users:
        if getattr(u, "is_superuser", False):
            u.role_label = "Admin"
        elif u.groups.filter(name="MANAGER").exists():
            u.role_label = "Manager fermă"
        elif u.groups.filter(name="EMPLOYEE").exists():
            u.role_label = "Angajat"
        else:
            u.role_label = "-"

    return render(request, "ui/users_list.html", {"employees": users, "is_manager": is_manager(request.user)})


@login_required
def user_create(request):
    """Creează cont pentru EMPLOYEE sau MANAGER.

    Doar ADMIN (sau superuser) poate crea conturi.
    """

    if not is_admin(request.user):
        messages.error(request, "Doar ADMIN poate crea conturi.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        form = StaffUserCreateForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    u = form.save(commit=True)
            except IntegrityError:
                form.add_error("username", "Acest username există deja. Alege altul (ex: vasile1).")
                messages.error(request, "Username duplicat.")
                return render(request, "ui/user_create.html", {"form": form})

            log_event(
                actor=request.user,
                action="CREATE",
                instance=u,
                message=f"CREATE utilizator: {u.username}",
                after=snapshot(u),
                request=request,
            )
            messages.success(request, f"Utilizator creat: {u.username}")
            return redirect("ui:users_list")

        messages.error(request, "Nu am putut crea utilizatorul. Verifică formularul.")
    else:
        form = StaffUserCreateForm()

    return render(request, "ui/user_create.html", {"form": form})


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
            message=f"DELETE mortalitate #{mid}: -{before.get('count')} (lot {before.get('flock')}) la {before.get('date')}",
            before=before,
            after=None,
            request=request,
        )
        messages.success(request, "Înregistrarea a fost ștearsă.")
        return redirect("ui:dashboard")

    return render(request, "ui/mortality_confirm_delete.html", {"m": m})


@login_required
def history(request):
    """Istoric schimbări (audit CRUD).

    - EMPLOYEE: vede doar istoricul lui
    - MANAGER/ADMIN: vede tot + poate filtra după utilizator și zi
    """

    mgr = is_manager(request.user)
    User = get_user_model()

    selected_user = (request.GET.get("user") or "").strip()
    day = parse_date((request.GET.get("day") or "").strip())

    qs = AuditEvent.objects.select_related("actor").all()

    if not mgr:
        qs = qs.filter(actor=request.user)
    else:
        if selected_user.isdigit():
            qs = qs.filter(actor_id=int(selected_user))
        if day:
            qs = qs.filter(created_at__date=day)

    qs = qs.order_by("-created_at", "-id")[:300]

    employees = []
    if mgr:
        employees = (
            User.objects.filter(groups__name__in=["EMPLOYEE", "MANAGER"])
            .distinct()
            .order_by("username")
        )

    return render(
        request,
        "ui/history.html",
        {
            "events": qs,
            "is_manager": mgr,
            "employees": employees,
            "selected_user": selected_user,
            "selected_day": (day.isoformat() if day else ""),
        },
    )


@login_required
def access_history(request):
    """Istoric accesări (LOGIN/LOGOUT)."""

    from apps.auditlog.models import AccessLog

    mgr = is_manager(request.user)
    User = get_user_model()

    selected_user = (request.GET.get("user") or "").strip()
    day = parse_date((request.GET.get("day") or "").strip())

    qs = AccessLog.objects.select_related("actor").all()
    if not mgr:
        qs = qs.filter(actor=request.user)
    else:
        if selected_user.isdigit():
            qs = qs.filter(actor_id=int(selected_user))
        if day:
            qs = qs.filter(created_at__date=day)

    qs = qs.order_by("-created_at", "-id")[:400]

    employees = []
    if mgr:
        employees = (
            User.objects.filter(groups__name__in=["EMPLOYEE", "MANAGER"])
            .distinct()
            .order_by("username")
        )

    return render(
        request,
        "ui/access.html",
        {
            "events": qs,
            "is_manager": mgr,
            "employees": employees,
            "selected_user": selected_user,
            "selected_day": (day.isoformat() if day else ""),
        },
    )


@never_cache
@login_required
def payment_ledger(request):
    """Ledger (registru) plăți.

    Vizibilitate:
    - ADMIN/MANAGER: toate plățile
    - EMPLOYEE: doar plățile create de el

    Acțiuni (edit/delete):
    - ADMIN/MANAGER: orice plată
    - EMPLOYEE: doar plățile lui, doar în ziua curentă (după created_at)

    Filtre (GET):
      - status: all|due|paid
      - due_from / due_to (YYYY-MM-DD)  (după due_date)
      - paid_from / paid_to (YYYY-MM-DD) (după paid_date)
      - buyer (string)  (document.partner.name)
      - user (id) (doar manager/admin)
    """

    mgr = is_manager(request.user)
    User = get_user_model()

    status = (request.GET.get("status") or "all").strip() or "all"
    due_from = parse_date((request.GET.get("due_from") or "").strip())
    due_to = parse_date((request.GET.get("due_to") or "").strip())
    paid_from = parse_date((request.GET.get("paid_from") or "").strip())
    paid_to = parse_date((request.GET.get("paid_to") or "").strip())
    buyer = (request.GET.get("buyer") or "").strip()
    selected_user = (request.GET.get("user") or "").strip()

    qs = (
        Payment.objects.select_related("document", "document__partner", "created_by")
        .all()
    )

    if not mgr:
        qs = qs.filter(created_by=request.user)
    else:
        if selected_user.isdigit():
            qs = qs.filter(created_by_id=int(selected_user))

    if status in ("due", "paid"):
        qs = qs.filter(status=status)

    if due_from:
        qs = qs.filter(due_date__gte=due_from)
    if due_to:
        qs = qs.filter(due_date__lte=due_to)

    if paid_from:
        qs = qs.filter(paid_date__gte=paid_from)
    if paid_to:
        qs = qs.filter(paid_date__lte=paid_to)

    if buyer:
        qs = qs.filter(document__partner__name__icontains=buyer)

    qs = qs.order_by("-due_date", "-id")

    # Totals pentru filtrul curent
    totals = qs.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00")),
        total_due=Coalesce(Sum("amount", filter=Q(status="due")), Decimal("0.00")),
        total_paid=Coalesce(Sum("amount", filter=Q(status="paid")), Decimal("0.00")),
    )

    payments = list(qs[:600])
    for p in payments:
        p.can_modify = can_modify_payment(request.user, p)
        # label simplu pentru tabel
        if p.created_by_id:
            p.created_by_label = getattr(p.created_by, "username", "") or ""
        else:
            p.created_by_label = "-"

    employees = []
    if mgr:
        employees = (
            User.objects.filter(groups__name__in=["EMPLOYEE", "MANAGER"]).distinct().order_by("username")
        )

    return render(
        request,
        "ui/payment_ledger.html",
        {
            "payments": payments,
            "is_manager": mgr,
            "employees": employees,
            "status": status,
            "due_from": (due_from.isoformat() if due_from else ""),
            "due_to": (due_to.isoformat() if due_to else ""),
            "paid_from": (paid_from.isoformat() if paid_from else ""),
            "paid_to": (paid_to.isoformat() if paid_to else ""),
            "buyer": buyer,
            "selected_user": selected_user,
            "totals": totals,
            "today": timezone.localdate().isoformat(),
        },
    )


@login_required
def payment_edit(request, pk: int):
    p = get_object_or_404(
        Payment.objects.select_related("document", "document__partner", "created_by"),
        pk=pk,
    )

    if not can_modify_payment(request.user, p):
        messages.error(request, "Nu ai drepturi să editezi această plată.")
        return redirect("ui:payment_ledger")

    before = snapshot(p)

    next_url = (request.GET.get("next") or "").strip() or reverse("ui:payment_ledger")

    if request.method == "POST":
        form = PaymentEditForm(request.POST, instance=p)
        if form.is_valid():
            p2 = form.save()

            log_event(
                actor=request.user,
                action="UPDATE",
                instance=p2,
                message=f"UPDATE payment: #{p2.id} ({p2.amount} {p2.document.currency}) status={p2.status}",
                before=before,
                after=snapshot(p2),
                request=request,
            )
            messages.success(request, "Plata a fost actualizată.")
            return redirect(next_url)

        messages.error(request, "Nu am putut salva plata. Verifică datele.")
    else:
        form = PaymentEditForm(instance=p)

    return render(
        request,
        "ui/payment_edit.html",
        {
            "form": form,
            "p": p,
            "next_url": next_url,
        },
    )


@login_required
def payment_delete(request, pk: int):
    p = get_object_or_404(
        Payment.objects.select_related("document", "document__partner", "created_by"),
        pk=pk,
    )

    if not can_modify_payment(request.user, p):
        messages.error(request, "Nu ai drepturi să ștergi această plată.")
        return redirect("ui:payment_ledger")

    next_url = (request.GET.get("next") or "").strip() or reverse("ui:payment_ledger")

    # Pentru UI: ștergerea plății nu înseamnă neapărat ștergerea vânzării.
    # Dacă user-ul vrea să anuleze vânzarea (și să se refacă Nr vânduți / Nr curent),
    # trebuie șters Document-ul.
    can_delete_sale = False
    if getattr(p, "document", None) is not None:
        try:
            can_delete_sale = can_modify_sale(request.user, p.document)
        except Exception:
            can_delete_sale = False

    if request.method == "POST":
        before = snapshot(p)
        log_event(
            actor=request.user,
            action="DELETE",
            instance=p,
            message=f"DELETE payment: #{p.id} ({p.amount} {p.document.currency}) status={p.status}",
            before=before,
            after=None,
            request=request,
        )
        p.delete()
        messages.success(request, "Plata a fost ștearsă.")
        return redirect(next_url)

    return render(
        request,
        "ui/payment_confirm_delete.html",
        {
            "p": p,
            "next_url": next_url,
            "can_delete_sale": can_delete_sale,
        },
    )


@login_required
def sale_delete(request, pk: int):
    """Șterge o vânzare (Document doc_type='sale') + liniile + plățile asociate.

    Important: pentru a actualiza "Nr vânduți" / "Nr curent", trebuie ștearsă vânzarea
    (Document + DocumentLine). Ștergerea unei plăți (Payment) nu elimină automat cantitățile vândute.
    """

    d = get_object_or_404(
        Document.objects
        .select_related("flock", "flock__season", "flock__house", "partner", "created_by")
        .prefetch_related("lines", "payments"),
        pk=pk,
        doc_type="sale",
    )

    if not can_modify_sale(request.user, d):
        messages.error(request, "Nu ai drepturi să ștergi această vânzare.")
        return redirect("ui:dashboard")

    default_next = reverse("ui:dashboard") + "?tab=sales"
    next_url = safe_next_url(request, default_next)

    if request.method == "POST":
        before = snapshot(d)

        buyer = ""
        try:
            buyer = d.partner.name if d.partner else ""
        except Exception:
            buyer = ""

        log_event(
            actor=request.user,
            action="DELETE",
            instance=d,
            message=f"DELETE vânzare: doc#{d.id} ({d.total} {d.currency}) buyer={buyer}",
            before=before,
            after=None,
            request=request,
        )

        # cascade: DocumentLine + Payment
        d.delete()
        messages.success(request, "Vânzarea a fost ștearsă. (Nr vânduți / Nr curent se recalculează automat)")
        return redirect(next_url)

    def _sum_qty(doc: Document, *, keys: set[str]) -> Decimal:
        total = Decimal("0")
        for ln in doc.lines.all():
            desc = (ln.description or "").strip().lower()
            if desc in keys:
                total += (ln.qty or Decimal("0"))
        return total

    d.qty_pui_albi = int(_sum_qty(d, keys={"pui albi"}) or 0)
    d.qty_pui_colorati = int(_sum_qty(d, keys={"pui colorați", "pui colorati"}) or 0)
    d.qty_furaj = _sum_qty(d, keys={"furaj"}).quantize(Decimal("0.001"))
    d.datorie = sum((p.amount for p in d.payments.all() if p.status == "due"), Decimal("0.00")).quantize(Decimal("0.01"))
    d.bani = sum((p.amount for p in d.payments.all() if p.status == "paid"), Decimal("0.00")).quantize(Decimal("0.01"))

    return render(
        request,
        "ui/sale_confirm_delete.html",
        {
            "d": d,
            "next_url": next_url,
        },
    )


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
    sales_only_debts = (request.GET.get("sales_only_debts") or "").strip() in ("1", "true", "True", "yes")
    sales_include_orphans = (request.GET.get("sales_include_orphans") or "").strip() in ("1", "true", "True", "yes")

    sales_qs = (
        Document.objects.filter(doc_type="sale")
        .select_related("flock", "flock__season", "flock__house", "partner")
        .prefetch_related("lines", "payments")
        .order_by("-date", "-id")
    )
    if not sales_include_orphans:
        sales_qs = sales_qs.filter(payments__isnull=False).distinct()
    if sales_from:
        sales_qs = sales_qs.filter(date__gte=sales_from)
    if sales_to:
        sales_qs = sales_qs.filter(date__lte=sales_to)
    if sales_buyer:
        sales_qs = sales_qs.filter(partner__name__icontains=sales_buyer)
    if sales_flock.isdigit():
        sales_qs = sales_qs.filter(flock_id=int(sales_flock))
    if sales_only_debts:
        sales_qs = sales_qs.filter(payments__status="due").distinct()

    filename = f"vanzari_{timezone.localdate().isoformat()}.csv"
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'

    # Excel-friendly BOM
    resp.write("\ufeff")

    writer = csv.writer(resp, delimiter=";")
    writer.writerow(["DATA", "ORA", "CUMPĂRĂTOR", "PUI ALBI", "PUI COLORATI", "FURAJ(KG)", "BANI", "DATORIE", "SERIE", "HALA"])

    def _sum_qty(doc: Document, *, keys: set[str]) -> Decimal:
        total = Decimal("0")
        for ln in doc.lines.all():
            desc = (ln.description or "").strip().lower()
            if desc in keys:
                total += (ln.qty or Decimal("0"))
        return total

    for d in sales_qs:
        pui_albi = int(_sum_qty(d, keys={"pui albi"}) or 0)
        pui_colorati = int(_sum_qty(d, keys={"pui colorați", "pui colorati"}) or 0)
        furaj = (_sum_qty(d, keys={"furaj"}) or Decimal("0")).quantize(Decimal("0.001"))
        datorie = sum((p.amount for p in d.payments.all() if p.status == "due"), Decimal("0.00")).quantize(Decimal("0.01"))
        ora = timezone.localtime(d.created_at).strftime("%H:%M") if d.created_at else ""
        buyer = d.partner.name if d.partner else ""
        serie = d.flock.season.name if d.flock_id else ""
        hala = d.flock.house.name if d.flock_id else ""

        writer.writerow([
            d.date.isoformat() if d.date else "",
            ora,
            buyer,
            pui_albi,
            pui_colorati,
            str(furaj),
            str((d.total or Decimal("0.00")).quantize(Decimal("0.01"))),
            str(datorie),
            serie,
            hala,
        ])

    return resp

@login_required
def sales_export_xlsx(request):
    """Export Excel (.xlsx) pentru vânzări (aceleași filtre ca CSV)."""
    sales_from = parse_date((request.GET.get("sales_from") or "").strip())
    sales_to = parse_date((request.GET.get("sales_to") or "").strip())
    sales_buyer = (request.GET.get("sales_buyer") or "").strip()
    sales_flock = (request.GET.get("sales_flock") or "").strip()
    sales_only_debts = (request.GET.get("sales_only_debts") or "").strip() in ("1", "true", "True", "yes")
    sales_include_orphans = (request.GET.get("sales_include_orphans") or "").strip() in ("1", "true", "True", "yes")

    sales_qs = (
        Document.objects.filter(doc_type="sale")
        .select_related("flock", "flock__season", "flock__house", "partner")
        .prefetch_related("lines", "payments")
        .order_by("-date", "-id")
    )
    if not sales_include_orphans:
        sales_qs = sales_qs.filter(payments__isnull=False).distinct()
    if sales_from:
        sales_qs = sales_qs.filter(date__gte=sales_from)
    if sales_to:
        sales_qs = sales_qs.filter(date__lte=sales_to)
    if sales_buyer:
        sales_qs = sales_qs.filter(partner__name__icontains=sales_buyer)
    if sales_flock.isdigit():
        sales_qs = sales_qs.filter(flock_id=int(sales_flock))
    if sales_only_debts:
        sales_qs = sales_qs.filter(payments__status="due").distinct()

    def _sum_qty(doc: Document, *, keys: set[str]) -> Decimal:
        total = Decimal("0")
        for ln in doc.lines.all():
            desc = (ln.description or "").strip().lower()
            if desc in keys:
                total += (ln.qty or Decimal("0"))
        return total

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vanzari"

    headers = ["DATA", "ORA", "CUMPĂRĂTOR", "PUI ALBI", "PUI COLORATI", "FURAJ(KG)", "BANI", "DATORIE", "SERIE", "HALA"]
    ws.append(headers)

    for d in sales_qs:
        pui_albi = int(_sum_qty(d, keys={"pui albi"}) or 0)
        pui_colorati = int(_sum_qty(d, keys={"pui colorați", "pui colorati"}) or 0)
        furaj = (_sum_qty(d, keys={"furaj"}) or Decimal("0")).quantize(Decimal("0.001"))
        datorie = sum((p.amount for p in d.payments.all() if p.status == "due"), Decimal("0.00")).quantize(Decimal("0.01"))
        ora = timezone.localtime(d.created_at).strftime("%H:%M") if getattr(d, "created_at", None) else ""
        buyer = d.partner.name if d.partner else ""
        serie = d.flock.season.name if d.flock_id else ""
        hala = d.flock.house.name if d.flock_id else ""
        bani = sum((p.amount for p in d.payments.all() if p.status == "paid"), Decimal("0.00")).quantize(Decimal("0.01"))

        ws.append([
            d.date.isoformat() if d.date else "",
            ora,
            buyer,
            pui_albi,
            pui_colorati,
            float(furaj),
            float(bani),
            float(datorie),
            serie,
            hala,
        ])

    # formatare numerică simplă
    for row in ws.iter_rows(min_row=2):
        # FURAJ(KG) col 6
        row[5].number_format = "0.000"
        # BANI col 7, DATORIE col 8
        row[6].number_format = "0.00"
        row[7].number_format = "0.00"

    # lățimi coloane
    widths = [12, 8, 28, 10, 12, 12, 12, 12, 16, 16]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"vanzari_{timezone.localdate().isoformat()}.xlsx"
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp



@login_required
def payment_mark_paid(request, pk: int):
    """Marchează o datorie (Payment status=due) ca fiind plătită."""
    p = get_object_or_404(
        Payment.objects.select_related("document", "document__partner", "created_by"),
        pk=pk,
    )

    next_url = (request.GET.get("next") or "").strip() or f"{reverse('ui:dashboard')}?tab=sales"

    if not can_modify_payment(request.user, p):
        messages.error(request, "Nu ai drepturi să modifici această plată.")
        return redirect(next_url)

    if p.status != "due":
        messages.info(request, "Această înregistrare nu mai este scadentă.")
        return redirect(next_url)

    if request.method == "POST":
        before = snapshot(p)
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
            before=before,
            after=snapshot(p),
            request=request,
        )
        messages.success(request, "Datoria a fost marcată ca plătită.")
        return redirect(next_url)

    # fallback GET
    return redirect(next_url)

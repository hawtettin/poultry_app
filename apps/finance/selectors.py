from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from apps.core.models import Flock
from apps.health.models import MortalityEvent

from .constants import (
    DESC_FURAJ,
    DESC_PUI_ALBI,
    DESC_PUI_ALL,
    DESC_PUI_COLORATI,
    LINE_FURAJ,
    LINE_PUI_ALBI,
    LINE_PUI_COLORATI,
    LINE_PUI_COLORATI_ASCII,
    norm_desc,
)
from .models import Document, DocumentLine, Payment


def sold_birds_qty(*, flock: Flock, up_to: date | None = None) -> int:
    """Total birds sold (white + colored) for a flock up to a date (inclusive)."""
    qs = DocumentLine.objects.filter(
        document__doc_type="sale",
        document__flock=flock,
    ).filter(
        Q(description__iexact=LINE_PUI_ALBI)
        | Q(description__iexact=LINE_PUI_COLORATI)
        | Q(description__iexact=LINE_PUI_COLORATI_ASCII)
    )
    if up_to:
        qs = qs.filter(document__date__lte=up_to)

    sold = qs.aggregate(s=Sum("qty"))["s"] or Decimal("0")
    return int(sold)


def sold_birds_map(*, flock_ids: list[int] | None = None) -> dict[int, int]:
    """Mapping flock_id -> sold birds qty (white+colored) for all time."""
    qs = DocumentLine.objects.filter(
        document__doc_type="sale",
        document__flock__isnull=False,
    ).filter(
        Q(description__iexact=LINE_PUI_ALBI)
        | Q(description__iexact=LINE_PUI_COLORATI)
        | Q(description__iexact=LINE_PUI_COLORATI_ASCII)
    )
    if flock_ids:
        qs = qs.filter(document__flock_id__in=flock_ids)

    rows = qs.values("document__flock_id").annotate(s=Sum("qty"))
    return {int(r["document__flock_id"]): int(r["s"] or 0) for r in rows}


def mortality_qty(*, flock: Flock, up_to: date | None = None) -> int:
    qs = MortalityEvent.objects.filter(flock=flock)
    if up_to:
        qs = qs.filter(date__lte=up_to)
    mort = qs.aggregate(s=Sum("count"))["s"] or 0
    return int(mort)


def available_birds(*, flock: Flock, at_date: date) -> int:
    """How many birds are available in a flock at a given date."""
    mort = mortality_qty(flock=flock, up_to=at_date)
    sold = sold_birds_qty(flock=flock, up_to=at_date)
    return max(int(flock.initial_count) - mort - sold, 0)


def sum_doc_qty(doc: Document, *, desc_keys: set[str]) -> Decimal:
    """Sum qty of document lines by normalized description.

    Assumes `doc.lines` is prefetched; otherwise, this will hit the DB.
    """
    total = Decimal("0")
    for ln in doc.lines.all():
        if norm_desc(ln.description) in desc_keys:
            total += ln.qty or Decimal("0")
    return total


@dataclass(frozen=True)
class SalesFilters:
    date_from: date | None = None
    date_to: date | None = None
    buyer_contains: str = ""
    flock_id: int | None = None
    only_debts: bool = False


def list_sales(*, filters: SalesFilters, limit: int = 100) -> list[Document]:
    qs = (
        Document.objects.filter(doc_type="sale")
        .select_related("flock", "flock__season", "flock__house", "partner")
        .prefetch_related("lines", "payments")
    )

    if filters.date_from:
        qs = qs.filter(date__gte=filters.date_from)
    if filters.date_to:
        qs = qs.filter(date__lte=filters.date_to)
    if filters.buyer_contains:
        qs = qs.filter(partner__name__icontains=filters.buyer_contains)
    if filters.flock_id:
        qs = qs.filter(flock_id=filters.flock_id)
    if filters.only_debts:
        qs = qs.filter(payments__status="due").distinct()

    docs = list(qs.order_by("-date", "-id")[:limit])

    # annotate on instances for UI convenience
    for d in docs:
        d.qty_pui_albi = int(sum_doc_qty(d, desc_keys=DESC_PUI_ALBI) or 0)
        d.qty_pui_colorati = int(sum_doc_qty(d, desc_keys=DESC_PUI_COLORATI) or 0)
        d.qty_furaj = (sum_doc_qty(d, desc_keys=DESC_FURAJ) or Decimal("0")).quantize(Decimal("0.001"))
        d.datorie = (
            sum((p.amount for p in d.payments.all() if p.status == "due"), Decimal("0.00"))
        ).quantize(Decimal("0.01"))

    return docs


def debts_by_buyer(*, limit: int = 30):
    return (
        Payment.objects.filter(status="due", document__doc_type="sale")
        .values("document__partner_id", "document__partner__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:limit]
    )


def due_payments(*, limit: int = 80):
    return (
        Payment.objects.filter(status="due", document__doc_type="sale")
        .select_related(
            "document",
            "document__partner",
            "document__flock",
            "document__flock__season",
            "document__flock__house",
        )
        .order_by("due_date", "id")[:limit]
    )


@dataclass(frozen=True)
class SalesReport:
    date_from: date
    date_to: date
    total_sales: Decimal
    total_debts: Decimal
    pui_total: int
    furaj_total: Decimal
    top_buyers: list[dict]
    top_debtors: list[dict]


def sales_report(*, date_from: date, date_to: date) -> SalesReport:
    docs = Document.objects.filter(doc_type="sale", date__gte=date_from, date__lte=date_to)

    total_sales = (docs.aggregate(s=Sum("total"))["s"] or Decimal("0.00")).quantize(Decimal("0.01"))
    total_debts = (
        Payment.objects.filter(status="due", document__in=docs).aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    ).quantize(Decimal("0.01"))

    pui_albi = (
        DocumentLine.objects.filter(document__in=docs, description__iexact=LINE_PUI_ALBI).aggregate(s=Sum("qty"))["s"]
        or Decimal("0")
    )
    pui_colorati = (
        DocumentLine.objects.filter(document__in=docs)
        .filter(Q(description__iexact=LINE_PUI_COLORATI) | Q(description__iexact=LINE_PUI_COLORATI_ASCII))
        .aggregate(s=Sum("qty"))["s"]
        or Decimal("0")
    )
    furaj = (
        DocumentLine.objects.filter(document__in=docs, description__iexact=LINE_FURAJ).aggregate(s=Sum("qty"))["s"]
        or Decimal("0")
    ).quantize(Decimal("0.001"))

    top_buyers = list(
        docs.values("partner__name").annotate(total=Sum("total")).order_by("-total")[:7]
    )
    top_debtors = list(
        Payment.objects.filter(
            status="due",
            document__doc_type="sale",
            document__date__gte=date_from,
            document__date__lte=date_to,
        )
        .values("document__partner__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:7]
    )

    return SalesReport(
        date_from=date_from,
        date_to=date_to,
        total_sales=total_sales,
        total_debts=total_debts,
        pui_total=int(pui_albi or 0) + int(pui_colorati or 0),
        furaj_total=furaj,
        top_buyers=top_buyers,
        top_debtors=top_debtors,
    )

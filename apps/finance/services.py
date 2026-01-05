from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import Flock

from .constants import (
    LINE_FURAJ,
    LINE_PUI_ALBI,
    LINE_PUI_COLORATI,
    UNIT_CAP,
    UNIT_KG,
)
from .models import Document, DocumentLine, Payment, Partner
from .selectors import available_birds


@dataclass(frozen=True)
class SaleInput:
    flock: Flock
    sale_date: date
    buyer_name: str

    pui_albi: int
    pret_pui_albi: Decimal

    pui_colorati: int
    pret_pui_colorati: Decimal

    furaj_kg: Decimal
    pret_furaj: Decimal

    datorie: Decimal


def calc_sale_total(data: SaleInput) -> Decimal:
    total = (
        (Decimal(data.pui_albi) * (data.pret_pui_albi or Decimal("0")))
        + (Decimal(data.pui_colorati) * (data.pret_pui_colorati or Decimal("0")))
        + ((data.furaj_kg or Decimal("0")) * (data.pret_furaj or Decimal("0")))
    ).quantize(Decimal("0.01"))
    return total


def validate_sale_input(data: SaleInput) -> None:
    buyer = (data.buyer_name or "").strip()
    if not buyer:
        raise ValidationError("Completează cumpărătorul.")

    if data.sale_date < data.flock.start_date:
        raise ValidationError("Data vânzării nu poate fi înainte de data populării lotului.")

    if data.pui_albi < 0 or data.pui_colorati < 0:
        raise ValidationError("Numărul de pui nu poate fi negativ.")

    if (data.furaj_kg or Decimal("0")) < 0:
        raise ValidationError("Furajul (kg) nu poate fi negativ.")

    if data.pui_albi == 0 and data.pui_colorati == 0 and (data.furaj_kg or Decimal("0")) == 0:
        raise ValidationError("Completează cel puțin un câmp: pui albi / pui colorați / furaj.")

    total = calc_sale_total(data)
    if total <= 0:
        raise ValidationError("Totalul vânzării este 0. Verifică cantitățile și prețurile.")

    datorie = (data.datorie or Decimal("0")).quantize(Decimal("0.01"))
    if datorie < 0:
        raise ValidationError("Datoria nu poate fi negativă.")
    if datorie > total:
        raise ValidationError(f"Datoria ({datorie} RON) nu poate depăși totalul ({total} RON).")

    # Stock validation (birds only)
    to_sell = int(data.pui_albi) + int(data.pui_colorati)
    if to_sell > 0:
        available = available_birds(flock=data.flock, at_date=data.sale_date)
        if to_sell > available:
            raise ValidationError(
                f"Stoc insuficient: în lot mai sunt ~{available} capete la {data.sale_date}. "
                f"Ai încercat să vinzi {to_sell} (albi+colorați)."
            )


@transaction.atomic
def create_sale(*, user, data: SaleInput) -> Document:
    """Create a sale Document + lines (+ optional due Payment).

    Notes:
    - The service re-validates stock and totals (do not rely only on UI validation).
    - Document is created with status=approved for quick entry.
    """
    # Defensive normalization
    data = SaleInput(
        flock=data.flock,
        sale_date=data.sale_date,
        buyer_name=(data.buyer_name or "").strip(),
        pui_albi=int(data.pui_albi or 0),
        pret_pui_albi=data.pret_pui_albi or Decimal("0"),
        pui_colorati=int(data.pui_colorati or 0),
        pret_pui_colorati=data.pret_pui_colorati or Decimal("0"),
        furaj_kg=data.furaj_kg or Decimal("0"),
        pret_furaj=data.pret_furaj or Decimal("0"),
        datorie=(data.datorie or Decimal("0")).quantize(Decimal("0.01")),
    )

    validate_sale_input(data)

    partner, _ = Partner.objects.get_or_create(
        name=data.buyer_name,
        defaults={"partner_type": "client"},
    )

    doc = Document.objects.create(
        doc_type="sale",
        status="approved",
        season=data.flock.season,
        flock=data.flock,
        partner=partner,
        date=data.sale_date,
        currency="RON",
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )

    if data.pui_albi > 0:
        DocumentLine.objects.create(
            document=doc,
            description=LINE_PUI_ALBI,
            qty=Decimal(data.pui_albi),
            unit=UNIT_CAP,
            unit_price=data.pret_pui_albi,
        )

    if data.pui_colorati > 0:
        DocumentLine.objects.create(
            document=doc,
            description=LINE_PUI_COLORATI,
            qty=Decimal(data.pui_colorati),
            unit=UNIT_CAP,
            unit_price=data.pret_pui_colorati,
        )

    if data.furaj_kg and data.furaj_kg > 0:
        DocumentLine.objects.create(
            document=doc,
            description=LINE_FURAJ,
            qty=data.furaj_kg,
            unit=UNIT_KG,
            unit_price=data.pret_furaj,
        )

    # Recalc totals (DocumentLine.save already does this, but keep defensive)
    doc.recalc_totals()
    doc.save(update_fields=["subtotal", "total"])

    if data.datorie and data.datorie > 0:
        Payment.objects.create(
            document=doc,
            due_date=data.sale_date,
            amount=data.datorie,
            method="other",
            status="due",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

    return doc


@transaction.atomic
def mark_payment_paid(*, payment: Payment, paid_date: date, method: str) -> Payment:
    if payment.status != "due":
        return payment

    payment.status = "paid"
    payment.paid_date = paid_date
    payment.method = method or "cash"
    payment.save(update_fields=["status", "paid_date", "method"])
    return payment

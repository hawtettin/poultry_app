from __future__ import annotations
from decimal import Decimal
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAdmin
from apps.finance.models import Document, DocumentLine

class SeasonReportView(APIView):
    permission_classes = [IsManagerOrAdmin]

    def get(self, request, season_id: int):
        sales = Document.objects.filter(season_id=season_id, doc_type="sale").aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        expenses = Document.objects.filter(season_id=season_id, doc_type="expense").aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        profit = (sales - expenses).quantize(Decimal("0.01"))

        top_exp = (
            DocumentLine.objects
            .filter(document__season_id=season_id, document__doc_type="expense")
            .values("category__name")
            .annotate(total=Sum("line_total"))
            .order_by("-total")[:10]
        )

        return Response({
            "season_id": season_id,
            "sales_total": str(sales),
            "expenses_total": str(expenses),
            "profit": str(profit),
            "top_expenses_by_category": list(top_exp),
        })

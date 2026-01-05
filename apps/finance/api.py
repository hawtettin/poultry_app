from __future__ import annotations
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsEmployeeOrAbove, IsManagerOrAdmin
from .models import Partner, Category, Document, DocumentLine, Payment

class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = ["id", "name", "partner_type", "tax_id", "phone", "email", "notes"]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "kind"]

class DocumentLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentLine
        fields = ["id", "category", "description", "qty", "unit", "unit_price", "line_total"]
        read_only_fields = ["line_total"]

class DocumentSerializer(serializers.ModelSerializer):
    lines = DocumentLineSerializer(many=True, required=False)

    class Meta:
        model = Document
        fields = [
            "id", "doc_type", "status",
            "season", "flock", "partner",
            "doc_no", "date", "currency",
            "subtotal", "vat", "total",
            "notes",
            "created_by", "created_at",
            "lines",
        ]
        read_only_fields = ["subtotal", "total", "created_by", "created_at"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        doc = Document.objects.create(**validated_data)
        for ln in lines_data:
            DocumentLine.objects.create(document=doc, **ln)
        doc.recalc_totals()
        doc.save(update_fields=["subtotal", "total"])
        return doc

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for ln in lines_data:
                DocumentLine.objects.create(document=instance, **ln)
            instance.recalc_totals()
            instance.save(update_fields=["subtotal", "total"])
        return instance

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "document", "due_date", "paid_date", "amount", "method", "status", "created_by"]
        read_only_fields = ["created_by"]

class PartnerViewSet(viewsets.ModelViewSet):
    queryset = Partner.objects.all().order_by("name")
    serializer_class = PartnerSerializer
    permission_classes = [IsManagerOrAdmin]

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsManagerOrAdmin]

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.select_related("season", "flock", "partner").prefetch_related("lines").all()
    serializer_class = DocumentSerializer
    permission_classes = [IsEmployeeOrAbove]

    def get_permissions(self):
        """Restrict editing/deleting SALES to MANAGER/ADMIN.

        Employees can still view sales and work with other docs as permitted.
        """
        if self.action in ("update", "partial_update", "destroy"):
            pk = self.kwargs.get("pk")
            if pk is not None:
                doc_type = Document.objects.filter(pk=pk).values_list("doc_type", flat=True).first()
                if doc_type == "sale":
                    return [IsManagerOrAdmin()]
        return [IsEmployeeOrAbove()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAdmin])
    def approve(self, request, pk=None):
        doc = self.get_object()
        if doc.status == "locked":
            return Response({"detail": "Document locked."}, status=400)
        doc.status = "approved"
        doc.save(update_fields=["status"])
        return Response({"detail": "Approved", "id": doc.id, "status": doc.status})

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("document").all()
    serializer_class = PaymentSerializer
    permission_classes = [IsEmployeeOrAbove]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

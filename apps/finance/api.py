from __future__ import annotations
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsEmployeeOrAbove, IsManagerOrAdmin, CanManagePayments
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
        fields = [
            "id",
            "house",
            "flock",
            "category",
            "description",
            "qty",
            "unit",
            "unit_price",
            "line_total",
        ]
        read_only_fields = ["line_total"]

class DocumentSerializer(serializers.ModelSerializer):
    lines = DocumentLineSerializer(many=True, required=False)

    class Meta:
        model = Document
        fields = [
            "id", "doc_type", "status",
            "season", "flock", "partner",
            "doc_no", "date", "currency",
            "vat_rate",
            "subtotal", "vat", "total",
            "notes",
            "created_by", "created_at",
            "lines",
        ]
        read_only_fields = ["subtotal", "vat", "total", "created_by", "created_at"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        doc = Document.objects.create(**validated_data)
        for ln in lines_data:
            DocumentLine.objects.create(document=doc, **ln)
        doc.recalc_totals()
        doc.save(update_fields=["subtotal", "vat", "total"])
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
            instance.save(update_fields=["subtotal", "vat", "total"])
        return instance

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "document",
            "due_date",
            "paid_date",
            "amount",
            "method",
            "status",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]

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
    permission_classes = [CanManagePayments]

    def get_queryset(self):
        qs = super().get_queryset().select_related("document", "document__partner", "created_by")
        u = self.request.user
        if not u.is_authenticated:
            return qs.none()
        if u.is_superuser or u.groups.filter(name__in=["ADMIN", "MANAGER"]).exists():
            return qs
        # EMPLOYEE: doar plățile lui
        return qs.filter(created_by=u)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

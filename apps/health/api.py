from __future__ import annotations
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.permissions import IsEmployeeOrAbove
from .models import MortalityEvent, Treatment

class MortalitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MortalityEvent
        fields = [
            "id", "flock", "date", "poultry_type", "count", "reason", "notes",
            "created_by", "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]

class TreatmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Treatment
        fields = [
            "id", "flock",
            "start_date", "end_date",
            "product_name", "active_substance",
            "dose", "method",
            "withdrawal_days", "withdrawal_end_date",
            "vet_name", "notes",
            "created_by", "created_at",
        ]
        read_only_fields = ["withdrawal_end_date", "created_by", "created_at"]

class MortalityViewSet(viewsets.ModelViewSet):
    queryset = MortalityEvent.objects.select_related("flock").all()
    serializer_class = MortalitySerializer
    permission_classes = [IsEmployeeOrAbove]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class TreatmentViewSet(viewsets.ModelViewSet):
    queryset = Treatment.objects.select_related("flock").all()
    serializer_class = TreatmentSerializer
    permission_classes = [IsEmployeeOrAbove]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class WithdrawalAlertsView(APIView):
    permission_classes = [IsEmployeeOrAbove]

    def get(self, request):
        today = timezone.localdate()
        qs = Treatment.objects.filter(withdrawal_end_date__gte=today).order_by("withdrawal_end_date")
        return Response({
            "today": str(today),
            "active_withdrawals": TreatmentSerializer(qs, many=True).data
        })

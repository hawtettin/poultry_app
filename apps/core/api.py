from __future__ import annotations
from rest_framework import serializers, viewsets

from apps.accounts.permissions import IsEmployeeOrAbove, IsManagerOrAdmin
from .models import House, Season, Flock

class HouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = House
        fields = ["id", "name", "code"]

class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ["id", "name", "start_date", "end_date", "is_active"]

class FlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flock
        fields = ["id", "season", "house", "start_date", "initial_count", "breed", "supplier", "notes"]

class HouseViewSet(viewsets.ModelViewSet):
    queryset = House.objects.all().order_by("name")
    serializer_class = HouseSerializer
    permission_classes = [IsManagerOrAdmin]

class SeasonViewSet(viewsets.ModelViewSet):
    queryset = Season.objects.all().order_by("-start_date")
    serializer_class = SeasonSerializer
    permission_classes = [IsManagerOrAdmin]

class FlockViewSet(viewsets.ModelViewSet):
    queryset = Flock.objects.select_related("season", "house").all().order_by("-start_date")
    serializer_class = FlockSerializer
    permission_classes = [IsEmployeeOrAbove]

from __future__ import annotations
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Flock

class MortalityEvent(models.Model):
    POULTRY_TYPES = [
        ("white", "Pui albi"),
        ("colored", "Pui colorați"),
    ]

    flock = models.ForeignKey(Flock, on_delete=models.CASCADE, related_name="mortality_events")
    date = models.DateField(default=timezone.localdate)
    poultry_type = models.CharField(max_length=10, choices=POULTRY_TYPES, default="white")
    count = models.PositiveIntegerField()
    reason = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

class Treatment(models.Model):
    METHOD_CHOICES = [
        ("water", "Apa"),
        ("feed", "Furaj"),
        ("injection", "Injectie"),
        ("other", "Altul"),
    ]

    flock = models.ForeignKey(Flock, on_delete=models.CASCADE, related_name="treatments")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(default=timezone.localdate)
    product_name = models.CharField(max_length=150)
    active_substance = models.CharField(max_length=150, blank=True, default="")
    dose = models.CharField(max_length=120, blank=True, default="")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="water")
    withdrawal_days = models.PositiveIntegerField(default=0)
    withdrawal_end_date = models.DateField(null=True, blank=True)

    vet_name = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]

    def save(self, *args, **kwargs):
        self.withdrawal_end_date = self.end_date + timedelta(days=int(self.withdrawal_days or 0))
        super().save(*args, **kwargs)

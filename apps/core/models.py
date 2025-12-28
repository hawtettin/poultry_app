from __future__ import annotations
from django.db import models

class House(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=50, blank=True, default="")

    def __str__(self) -> str:
        return self.name

class Season(models.Model):
    name = models.CharField(max_length=120, unique=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name

class Flock(models.Model):
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="flocks")
    house = models.ForeignKey(House, on_delete=models.PROTECT, related_name="flocks")
    start_date = models.DateField()
    initial_count = models.PositiveIntegerField()
    breed = models.CharField(max_length=120, blank=True, default="")
    supplier = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.season.name} / {self.house.name} ({self.start_date})"

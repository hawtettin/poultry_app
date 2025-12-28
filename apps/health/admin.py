from django.contrib import admin
from .models import MortalityEvent, Treatment

@admin.register(MortalityEvent)
class MortalityAdmin(admin.ModelAdmin):
    list_display = ("id", "flock", "date", "count", "reason", "created_by")
    list_filter = ("date", "flock")

@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ("id", "flock", "product_name", "start_date", "end_date", "withdrawal_days", "withdrawal_end_date", "method")
    list_filter = ("method", "start_date", "flock")

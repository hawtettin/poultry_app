from django.contrib import admin
from .models import AuditEvent, AccessLog

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "actor", "action", "model", "object_id", "message")
    list_filter = ("action", "model", "created_at")
    search_fields = ("message", "model", "object_id", "actor__username")

@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "actor", "event", "path", "ip_address")
    list_filter = ("event", "created_at")
    search_fields = ("actor__username", "path", "ip_address")

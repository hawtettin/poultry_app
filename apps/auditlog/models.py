from __future__ import annotations

from django.conf import settings
from django.db import models

class AuditEvent(models.Model):
    ACTIONS = [("CREATE","CREATE"),("UPDATE","UPDATE"),("DELETE","DELETE")]
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    action = models.CharField(max_length=10, choices=ACTIONS)
    model = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    message = models.CharField(max_length=300, blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    path = models.CharField(max_length=300, blank=True, default="")
    method = models.CharField(max_length=10, blank=True, default="")
    ip_address = models.CharField(max_length=45, blank=True, default="")
    user_agent = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["model", "created_at"]),
        ]

class AccessLog(models.Model):
    EVENTS = [("LOGIN","LOGIN"),("LOGOUT","LOGOUT")]
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="access_logs")
    event = models.CharField(max_length=10, choices=EVENTS)
    path = models.CharField(max_length=300, blank=True, default="")
    ip_address = models.CharField(max_length=45, blank=True, default="")
    user_agent = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["event", "created_at"]),
        ]

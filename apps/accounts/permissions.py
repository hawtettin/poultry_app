from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import BasePermission

def in_group(user, name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=name).exists()

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_superuser or in_group(u, "ADMIN"))

class IsManagerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER"))

class IsEmployeeOrAbove(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (
            u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER") or in_group(u, "EMPLOYEE")
        )


class CanManagePayments(BasePermission):
    """Reguli:
    - ADMIN / MANAGER (și superuser) pot edita/șterge orice plată
    - EMPLOYEE poate edita/șterge doar plățile create de el și doar în ziua curentă
    """

    def has_permission(self, request, view):
        # list/retrieve/create: employee or above
        u = request.user
        return u.is_authenticated and (
            u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER") or in_group(u, "EMPLOYEE")
        )

    def has_object_permission(self, request, view, obj):
        u = request.user

        # SAFE methods (GET/HEAD/OPTIONS) -> e ok pentru employee
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return self.has_permission(request, view)

        # superuser / admin / manager -> full access
        if u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER"):
            return True

        # employee: doar plățile lui + doar azi
        if not in_group(u, "EMPLOYEE"):
            return False

        if getattr(obj, "created_by_id", None) != u.id:
            return False

        today = timezone.localdate()
        created_at = getattr(obj, "created_at", None)
        if created_at is None:
            return False
        return timezone.localtime(created_at).date() == today

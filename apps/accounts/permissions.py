from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import BasePermission, SAFE_METHODS


def in_group(user, name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=name).exists()


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_superuser or in_group(u, "ADMIN"))


class IsManagerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (
            u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER")
        )


class IsEmployeeOrAbove(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (
            u.is_superuser
            or in_group(u, "ADMIN")
            or in_group(u, "MANAGER")
            or in_group(u, "EMPLOYEE")
        )


class CanManagePayments(BasePermission):
    """Permisiuni pentru Payment (API / DRF).

    Reguli:
      - ADMIN/MANAGER/superuser: pot vedea + edita/șterge orice plată.
      - EMPLOYEE: poate vedea doar plățile lui și poate edita/șterge doar plățile
        create de el, doar în ziua curentă (după created_at).

    Notă: pentru UI există o verificare similară în `apps/ui/views.py`.
    """

    def has_permission(self, request, view):
        # allow list/retrieve/create for any authenticated employee+; object-level restricts.
        return IsEmployeeOrAbove().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        u = request.user
        if not u.is_authenticated:
            return False

        # Admin/Manager/Superuser: full access
        if u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER"):
            return True

        # Employee: only own objects
        if not in_group(u, "EMPLOYEE"):
            return False

        if getattr(obj, "created_by_id", None) != u.id:
            return False

        # Read access for own payments
        if request.method in SAFE_METHODS:
            return True

        # Write access only on the same day the payment was created
        created_at = getattr(obj, "created_at", None)
        if not created_at:
            return False

        try:
            created_day = timezone.localtime(created_at).date()
        except Exception:
            created_day = created_at.date()
        return created_day == timezone.localdate()

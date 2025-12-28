from __future__ import annotations
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

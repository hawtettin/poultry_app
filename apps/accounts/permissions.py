from __future__ import annotations
from rest_framework.permissions import BasePermission

def in_group(user, name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=name).exists()

ROLE_EMPLOYEE = "EMPLOYEE"
ROLE_MANAGER = "MANAGER"
MANAGED_ROLE_NAMES = [ROLE_EMPLOYEE, ROLE_MANAGER]
ROLE_CHOICES = [
    (ROLE_EMPLOYEE, "Angajat"),
    (ROLE_MANAGER, "Manager fermă"),
]


def is_admin(user) -> bool:
    return user.is_authenticated and (user.is_superuser or in_group(user, "ADMIN"))


def is_manager(user) -> bool:
    return user.is_authenticated and (is_admin(user) or in_group(user, ROLE_MANAGER))


def get_current_role(user) -> str:
    """
    Returnează rolul principal pentru UI (EMPLOYEE/MANAGER).
    Adminii sunt gestionați separat (nu intră în flow-ul de assignment din UI).
    """
    if not getattr(user, "is_authenticated", False):
        return ROLE_EMPLOYEE
    if in_group(user, ROLE_MANAGER):
        return ROLE_MANAGER
    return ROLE_EMPLOYEE


def assign_role(user, role: str):
    """Aplică rolul principal, păstrând membership-ul de ADMIN/superuser neatins."""
    from django.contrib.auth.models import Group  # import local ca să evităm import circular

    valid_roles = {r[0] for r in ROLE_CHOICES}
    if role not in valid_roles:
        role = ROLE_EMPLOYEE

    # eliminăm rolurile gestionate, dar nu atingem ADMIN sau alte grupuri custom
    existing = list(Group.objects.filter(name__in=MANAGED_ROLE_NAMES))
    if existing:
        user.groups.remove(*existing)

    grp, _ = Group.objects.get_or_create(name=role)
    user.groups.add(grp)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return is_admin(u)

class IsManagerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (is_admin(u) or in_group(u, ROLE_MANAGER))

class IsEmployeeOrAbove(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (
            u.is_superuser
            or in_group(u, "ADMIN")
            or in_group(u, ROLE_MANAGER)
            or in_group(u, ROLE_EMPLOYEE)
        )

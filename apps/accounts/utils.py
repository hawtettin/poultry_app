from __future__ import annotations

from django.contrib.auth.models import Group

ROLE_ADMIN = "ADMIN"
ROLE_MANAGER = "MANAGER"
ROLE_EMPLOYEE = "EMPLOYEE"

ROLE_NAMES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE]


def in_group(user, group_name: str) -> bool:
    """Return True if the user is authenticated and belongs to the given group.

    Superusers are treated as belonging to all groups.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=group_name).exists()


def is_admin(user) -> bool:
    return in_group(user, ROLE_ADMIN)


def is_manager(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=[ROLE_ADMIN, ROLE_MANAGER]).exists()


def is_employee_or_above(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=ROLE_NAMES).exists()


def ensure_group(name: str) -> Group:
    """Get or create a role group in a safe, idempotent way."""
    group, _ = Group.objects.get_or_create(name=name)
    return group

from __future__ import annotations

from apps.health.models import MortalityEvent


WEEKDAYS_RO = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]


def is_manager(user) -> bool:
    """ADMIN / MANAGER / superuser."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=["ADMIN", "MANAGER"]).exists()


def can_modify_mortality(user, m: MortalityEvent) -> bool:
    """Managers can modify all; employees only their own records."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or is_manager(user):
        return True
    return (m.created_by_id is not None) and (m.created_by_id == user.id)

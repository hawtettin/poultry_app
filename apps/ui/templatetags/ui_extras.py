from __future__ import annotations

from django import template

register = template.Library()


def _is_authenticated(user) -> bool:
    return bool(getattr(user, "is_authenticated", False))


@register.filter
def in_group(user, group_name: str) -> bool:
    """Template filter: {{ user|in_group:'ADMIN' }}"""
    if not _is_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=group_name).exists()


@register.filter
def in_any_group(user, group_names: str) -> bool:
    """Template filter: {{ user|in_any_group:'ADMIN,MANAGER' }}"""
    if not _is_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    names = [n.strip() for n in (group_names or "").split(",") if n.strip()]
    if not names:
        return False
    return user.groups.filter(name__in=names).exists()

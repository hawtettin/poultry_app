from __future__ import annotations

from typing import Literal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from .utils import ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE, ensure_group

RoleName = Literal["ADMIN", "MANAGER", "EMPLOYEE"]


def validate_role(role: str) -> None:
    if role not in (ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE):
        raise ValidationError({"role": f"Rol invalid: {role}"})


@transaction.atomic
def create_user_with_role(
    *,
    username: str,
    password: str,
    role: RoleName,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    is_active: bool = True,
):
    """Create a Django user and assign them to a role group.

    This keeps user provisioning logic in apps.accounts (reusable from UI/API).
    """
    validate_role(role)

    User = get_user_model()

    username = (username or "").strip()
    if not username:
        raise ValidationError({"username": "Username este obligatoriu."})

    if User.objects.filter(username=username).exists():
        raise ValidationError({"username": "Există deja un utilizator cu acest username."})

    if not password or len(password) < 8:
        raise ValidationError({"password": "Parola trebuie să aibă minim 8 caractere."})

    user = User(
        username=username,
        first_name=(first_name or "").strip(),
        last_name=(last_name or "").strip(),
        email=(email or "").strip(),
        is_active=bool(is_active),
    )
    user.set_password(password)
    user.save()

    group = ensure_group(role)
    user.groups.add(group)
    return user

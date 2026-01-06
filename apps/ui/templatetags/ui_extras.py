from django import template

register = template.Library()

@register.filter
def in_groups(user, csv_names: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    names = [x.strip() for x in (csv_names or "").split(",") if x.strip()]
    if not names:
        return False
    return user.groups.filter(name__in=names).exists()

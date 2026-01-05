"""UI views.

This is the presentation layer (Django templates).
Keep heavy business logic out of views; push it into feature modules:
- `apps.<feature>.selectors` for read/query logic
- `apps.<feature>.services`  for write logic

Exports used by urls.py.
"""

from .dashboard import dashboard
from .series import create_series
from .mortality import mortality_edit, mortality_delete
from .history import history
from .sales import sales_export_csv, payment_mark_paid

__all__ = [
    "dashboard",
    "create_series",
    "mortality_edit",
    "mortality_delete",
    "history",
    "sales_export_csv",
    "payment_mark_paid",
]

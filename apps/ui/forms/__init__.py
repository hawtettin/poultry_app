"""UI forms (presentation layer).

Rule of thumb:
- Keep forms focused on input validation and UX.
- Any business rules that must be enforced server-side should live in
  `apps.<feature>.services` and be called from `form.save()`.

This module re-exports the public forms used by urls/views.
"""

from .auth import BootstrapAuthenticationForm
from .series import CreateSeriesForm
from .mortality import MortalityQuickAddForm, MortalityEditForm
from .sales import SaleQuickAddForm

__all__ = [
    "BootstrapAuthenticationForm",
    "CreateSeriesForm",
    "MortalityQuickAddForm",
    "MortalityEditForm",
    "SaleQuickAddForm",
]

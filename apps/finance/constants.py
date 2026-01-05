from __future__ import annotations

# Central place for "products" that are represented as DocumentLine.description.
#
# Why:
# - Avoid stringly-typed logic scattered across the codebase.
# - Keep backward compatibility with existing data (e.g., "Pui colorati" without diacritics).
#
# NOTE: In the future, you can replace this with a proper Product model or
# Category mapping. Until then, keep the constants here.

LINE_PUI_ALBI = "Pui albi"
LINE_PUI_COLORATI = "Pui colorați"
LINE_PUI_COLORATI_ASCII = "Pui colorati"  # legacy / data without diacritics
LINE_FURAJ = "Furaj"

UNIT_CAP = "cap"
UNIT_KG = "kg"


def norm_desc(value: str) -> str:
    return (value or "").strip().lower()


DESC_PUI_ALBI = {norm_desc(LINE_PUI_ALBI)}
DESC_PUI_COLORATI = {norm_desc(LINE_PUI_COLORATI), norm_desc(LINE_PUI_COLORATI_ASCII)}
DESC_FURAJ = {norm_desc(LINE_FURAJ)}

DESC_PUI_ALL = DESC_PUI_ALBI | DESC_PUI_COLORATI

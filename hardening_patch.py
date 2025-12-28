# hardening_patch.py
from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).resolve().parent

VIEWS = BASE / "apps" / "ui" / "views.py"
FORMS = BASE / "apps" / "ui" / "forms.py"

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write(p: Path, s: str) -> None:
    p.write_text(s.replace("\r\n", "\n"), encoding="utf-8")

def patch_forms_username_unique(text: str) -> str:
    # Asiguram importurile necesare (User deja exista; adaugam forms daca lipseste)
    # In forms.py exista deja "from django import forms" si "from django.contrib.auth.models import User"
    # Adaugam clean_username + fallback IntegrityError-proof.
    if "def clean_username" in text:
        return text

    # cautam clasa EmployeeCreateForm
    m = re.search(r"class EmployeeCreateForm\(UserCreationForm\):", text)
    if not m:
        return text

    # inseram metoda clean_username inainte de save_employee
    m2 = re.search(r"\n\s+def save_employee\(", text[m.start():])
    if not m2:
        return text

    insert_at = m.start() + m2.start()

    patch = """
    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            return username
        # case-insensitive unique
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Acest username există deja. Alege altul (ex: vasilica1).")
        return username
"""
    return text[:insert_at] + patch + text[insert_at:]

def patch_forms_mortality_edit_validation(text: str) -> str:
    # Adaugam validare la MortalityEditForm ca sa nu pui un count care duce sub 0.
    if "class MortalityEditForm" not in text:
        return text
    if "def clean(self):" in text and "Valoare prea mare" in text:
        return text  # deja e intarit

    # Inseram clean() in MortalityEditForm, inainte de Meta sau dupa Meta
    # gasim clasa
    m = re.search(r"class MortalityEditForm\(forms\.ModelForm\):", text)
    if not m:
        return text
    # gasim sfarsitul clasei (urmatoarea clasa) sau EOF
    start = m.start()
    # cautam prima aparitie a "class EmployeeCreateForm" dupa
    m_next = re.search(r"\nclass EmployeeCreateForm", text[start:])
    end = start + m_next.start() if m_next else len(text)

    block = text[start:end]
    if "def clean(self)" in block:
        return text  # are deja clean

    # injectam clean() dupa Meta (daca exista Meta)
    meta_pos = block.find("class Meta")
    if meta_pos == -1:
        return text

    # dupa incheierea dictionarului widgets, punem clean()
    # cautam ultima aparitie "}" din Meta widgets
    insert_rel = block.rfind("}")
    if insert_rel == -1:
        insert_rel = len(block)

    clean_code = """

    def clean(self):
        cleaned = super().clean()
        flock = cleaned.get("flock")
        count = cleaned.get("count")
        if flock and count:
            # total fara aceasta inregistrare
            other_total = (
                MortalityEvent.objects
                .filter(flock=flock)
                .exclude(pk=self.instance.pk)
                .aggregate(s=Sum("count"))["s"] or 0
            )
            current = int(flock.initial_count) - int(other_total)
            if int(count) > max(current, 0):
                raise forms.ValidationError(
                    f"Valoare prea mare. În lot mai sunt ~{max(current, 0)} capete (fără această înregistrare)."
                )
        return cleaned
"""
    # avem nevoie de MortalityEvent si Sum si forms in scope; ele exista deja in forms.py
    new_block = block[:insert_rel+1] + clean_code + block[insert_rel+1:]
    return text[:start] + new_block + text[end:]

def patch_views_imports_and_filters(text: str) -> str:
    # Fix: timezone.datetime(...) -> datetime.date(...) (timezone.datetime nu exista)
    # si adaugam import date/IntegrityError/transaction
    if "from datetime import date as _date" not in text:
        # inseram aproape de top
        text = text.replace(
            "from __future__ import annotations\n\n",
            "from __future__ import annotations\n\nfrom datetime import date as _date\n"
        )

    if "from django.db import IntegrityError, transaction" not in text:
        # daca exista deja importuri django.db.models, adaugam separat
        if "from django.db" in text:
            # nu amestecam
            text = text.replace(
                "from django.db.models import",
                "from django.db import IntegrityError, transaction\nfrom django.db.models import",
                1
            )
        else:
            text = text.replace(
                "from django.contrib import messages\n",
                "from django.contrib import messages\nfrom django.db import IntegrityError, transaction\n",
                1
            )

    # Inlocuim filtrele pe zi
    text = re.sub(
        r"qs = qs\.filter\(created_at__date=timezone\.datetime\(([^)]+)\)\.date\(\)\)",
        r"qs = qs.filter(created_at__date=_date(\1))",
        text
    )
    # daca avem varianta y,m,d separate in try: y,m,d = ...
    # atunci inlocuim explicit folosind _date(y,m,d)
    text = text.replace(
        "qs = qs.filter(created_at__date=timezone.datetime(y,m,d).date())",
        "qs = qs.filter(created_at__date=_date(y, m, d))"
    )
    text = text.replace(
        "qs = qs.filter(created_at__date=timezone.datetime(y, m, d).date())",
        "qs = qs.filter(created_at__date=_date(y, m, d))"
    )

    # Hardening: user_create sa nu mai pice cu IntegrityError
    if "except IntegrityError" in text:
        return text  # deja patch-uit

    # cautam functia user_create si injectam try/except in jurul save_employee
    # gasim linia cu "u = form.save_employee()"
    needle = "u = form.save_employee()"
    if needle in text:
        text = text.replace(
            needle,
            "try:\n            with transaction.atomic():\n                u = form.save_employee()\n        except IntegrityError:\n            form.add_error(\"username\", \"Acest username există deja. Alege altul (ex: vasilica1).\")\n            messages.error(request, \"Username duplicat.\")\n            return render(request, \"ui/user_create.html\", {\"form\": form})",
            1
        )
    return text

def main() -> None:
    # 1) Patch forms
    forms_txt = read(FORMS)
    forms_txt = patch_forms_username_unique(forms_txt)
    forms_txt = patch_forms_mortality_edit_validation(forms_txt)
    write(FORMS, forms_txt)

    # 2) Patch views
    views_txt = read(VIEWS)
    views_txt = patch_views_imports_and_filters(views_txt)
    write(VIEWS, views_txt)

    print("✅ Hardening patch aplicat:")
    print(" - username duplicat nu mai da 500 (mesaj in form)")
    print(" - filtrele pe zi (/history, /access) nu mai pica")
    print(" - edit mortalitate nu permite count prea mare")
    print("➡️ Repornește serverul: python manage.py runserver")

if __name__ == "__main__":
    main()

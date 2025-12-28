# fix_indent_user_create.py
from __future__ import annotations
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
VIEWS = BASE / "apps" / "ui" / "views.py"

NEW_FUNC = r'''
@login_required
def user_create(request):
    if not is_manager(request.user):
        messages.error(request, "Doar MANAGER/ADMIN pot crea angajați.")
        return redirect("ui:dashboard")

    if request.method == "POST":
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    u = form.save_employee()
            except IntegrityError:
                form.add_error("username", "Acest username există deja. Alege altul (ex: vasilica1).")
                messages.error(request, "Username duplicat.")
                return render(request, "ui/user_create.html", {"form": form})

            log_event(
                actor=request.user,
                action="CREATE",
                instance=u,
                message=f"CREATE angajat: {u.username}",
                after=snapshot(u),
                request=request,
            )
            messages.success(request, f"Angajat creat: {u.username}")
            return redirect("ui:users_list")
        messages.error(request, "Nu am putut crea angajatul.")
    else:
        form = EmployeeCreateForm()

    return render(request, "ui/user_create.html", {"form": form})
'''

def main():
    text = VIEWS.read_text(encoding="utf-8")

    # inlocuieste blocul def user_create ... pana la urmatoarea functie (@login_required def history) sau def history
    pattern = re.compile(r"@login_required\s+def user_create\(request\):.*?\n@login_required\s+def history\(", re.S)
    m = pattern.search(text)
    if not m:
        raise SystemExit("Nu am gasit blocul user_create->history in apps/ui/views.py")

    replacement = NEW_FUNC + "\n\n@login_required\ndef history("
    text2 = pattern.sub(replacement, text, count=1)

    VIEWS.write_text(text2, encoding="utf-8")
    print("✅ Fix aplicat: indentarea la user_create este corecta.")

if __name__ == "__main__":
    main()

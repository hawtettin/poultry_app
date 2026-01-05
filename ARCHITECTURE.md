# Arhitectură proiect

Acest proiect folosește o arhitectură **Modular Monolith (Django)**.

Ideea: rămânem cu un singur proiect Django (simplu de deploy), dar organizăm codul în **feature modules** (Django apps) astfel încât să fie ușor de:
- adăugat funcționalități noi fără să “umflăm” fișierele existente;
- șters funcționalități fără să rupem alte zone;
- lucrat de mai mulți oameni / AI în paralel.

## Principii

1) **Feature-first**: fiecare domeniu este o aplicație Django în `apps/<feature>/`.
2) **Separarea citire vs scriere**:
   - `selectors.py` = query/raportare (citiri, agregări). Fără efecte secundare.
   - `services.py` = operații care schimbă date (create/update/delete) + validări de business.
3) **UI subțire**: `apps/ui` (Django templates) nu conține logică de business grea.
   - UI apelează `apps.<feature>.selectors` / `apps.<feature>.services`.
4) **Cross-cutting separat**: audit log este în `apps/auditlog` și poate fi folosit din orice feature.

## Structura proiect

```
config/                 # settings/urls/wsgi
apps/
  accounts/             # roluri/permisiuni
  core/                 # hale/sezoane/loturi
  health/               # mortalitate/tratamente
  finance/              # documente/plăți + logica de vânzări
  reports/              # rapoarte agregate
  auditlog/             # audit trail
  ui/                   # interfața web (templates)
```

### Convenții în interiorul unui feature (`apps/<feature>/`)

Fișiere recomandate (nu toate sunt obligatorii):
- `models.py` – modelele Django
- `admin.py` – admin configuration
- `api.py` – DRF viewsets/serializers (dacă există API)
- `selectors.py` – citire/query/rapoarte
- `services.py` – operații de scriere + validări de business
- `constants.py` – constante folosite în mai multe locuri
- `migrations/` – migrații

> Regula simplă: dacă un view/form începe să aibă “multă logică”, mută logica în `services.py` / `selectors.py`.

## Reguli de dependențe între apps

- Este ok ca un feature să importe **modele** din alt feature, dar încearcă să eviți “spaghetti”.
- Preferat:
  - UI → `selectors/services` (din feature)
  - API → `selectors/services` (din feature)
  - `services` → modele (din feature) + strict minimul necesar din alte features
- Când o regulă de business afectează mai multe domenii, încearcă să alegi **un singur loc** unde este “owner”-ul:
  - Ex: calcul stoc pui la vânzare = `apps.finance.services` (pentru că vânzarea scade stocul).

## Cum adaugi un feature nou (rețetă)

1) Creează app-ul:

```bash
python manage.py startapp feature_name apps/feature_name
```

2) În `apps/feature_name/apps.py` setează `name = "apps.feature_name"`.

3) Adaugă app-ul în `config/settings.py` → `INSTALLED_APPS`.

4) Definește modelele în `apps/feature_name/models.py`.

5) Creează migrații:

```bash
python manage.py makemigrations feature_name
python manage.py migrate
```

6) Pune logica:
- citiri/rapoarte în `selectors.py`
- scrieri în `services.py`

7) Expune feature-ul:
- API (opțional): adaugă viewset în `apps/feature_name/api.py` și înregistrează router în `config/urls.py`.
- UI (opțional): adaugă view/template în `apps/ui` și un tab/link în `apps/ui/templates/ui/base.html` / `dashboard.html`.

## Cum ștergi un feature (curat)

1) Elimină URL-urile:
- din `config/urls.py` (API)
- din `apps/ui/urls.py` (UI)

2) Scoate app-ul din `INSTALLED_APPS`.

3) Șterge codul `apps/feature_name/`.

4) Dacă feature-ul avea tabele în DB:
- în mod ideal, creezi migrații de ștergere (mai ales în producție)
- sau, dacă e un proiect “fresh”, poți reseta DB.

## Exemplu concret: Vânzări

- Vânzarea este modelată ca:
  - `Document (doc_type="sale")`
  - `DocumentLine` (linii cu `description`: "Pui albi", "Pui colorați", "Furaj")
  - `Payment (status="due")` pentru datorii

- Regulile critice (stoc, total, datorie) sunt în:
  - `apps.finance.services` (write)
  - `apps.finance.selectors` (read/raportare)

UI-ul (`apps/ui`) doar validează input-ul și apelează service-ul.

## Checklist rapid (pentru modificări)

- [ ] Am pus business logic în `services.py` / `selectors.py`, nu în template/view?
- [ ] Am evitat string-uri “magice”? (dacă apar, mută-le în `constants.py`)
- [ ] Am actualizat `ARCHITECTURE.md` dacă am schimbat regulile?
- [ ] Am păstrat interfețe simple pentru UI/API?

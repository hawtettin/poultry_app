# Poultry App (Django + DRF)

Aplicație de management pentru fermă avicolă (serii/loturi, mortalități, tratamente, financiar, rapoarte) + UI web simplu.

## Arhitectură (scalabilă)

Proiectul este împărțit pe aplicații Django ("apps"), ca să poți extinde ușor fiecare zonă:

- `apps/accounts` – roluri/permisiuni (ADMIN / MANAGER / EMPLOYEE) + utilitare/servicii pentru provisioning utilizatori
- `apps/core` – hale, sezoane, loturi
- `apps/health` – mortalități, tratamente
- `apps/finance` – parteneri, categorii, documente (cheltuieli / vânzări), plăți
- `apps/reports` – rapoarte (ex. profit pe sezon)
- `apps/auditlog` – audit log generic (create/update/delete)
- `apps/ui` – interfață web (dashboard, mortalități, vânzări, users provisioning)

Logica de roluri este centralizată în `apps/accounts/utils.py` (UI) și `apps/accounts/permissions.py` (DRF), astfel încât poți refolosi verificările în viitor (API/UI).

## Funcționalități cerute (implementate)

1. **Meniu "Utilizatori" (doar ADMIN)**
   - adminul poate crea conturi pentru **Angajați (EMPLOYEE)** și **Manageri de fermă (MANAGER)** din UI.

2. **Editare / ștergere vânzări (ADMIN + MANAGER)**
   - UI: listă vânzări + creare/editare/ștergere pentru `Document` cu `doc_type="sale"`.
   - API: modificare/ștergere vânzări este restricționată la **MANAGER/ADMIN**.

## Instalare & rulare

1. Copiază `.env.example` în `.env` (opțional)
2. Creează venv și instalează dependențe:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # sau: .venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```
3. Pornește baza de date Postgres:
   ```bash
   docker compose up -d
   ```
4. Migrează:
   ```bash
   python manage.py migrate
   ```
5. Creează grupurile de roluri:
   ```bash
   python manage.py init_roles
   ```
6. Creează superuser:
   ```bash
   python manage.py createsuperuser
   ```
7. Rulează serverul:
   ```bash
   python manage.py runserver
   ```

UI:
- http://127.0.0.1:8000/ (dashboard)
- http://127.0.0.1:8000/sales/ (vânzări)
- http://127.0.0.1:8000/users/ (utilizatori – doar ADMIN)
- http://127.0.0.1:8000/history/ (audit)

## Note

- Pentru ca un utilizator să fie considerat **ADMIN**, trebuie să fie superuser **sau** să fie în grupul Django `ADMIN`.
- Documentele cu status `locked` nu pot fi editate/șterse (UI + API).

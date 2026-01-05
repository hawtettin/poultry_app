# Poultry App

Aplicație Django (UI + API) pentru gestionarea unei ferme avicole:
- serii/loturi (hale, sezoane)
- mortalitate / tratamente
- finanțe (documente, plăți) + vânzări (UI quick-add)
- audit log (cine a făcut ce)

## Rulare local (rapid)

### 1) Configurează mediul

```bash
cp .env.example .env
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
# source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Pornește Postgres (opțional, recomandat)

```bash
docker compose up -d
```

Dacă nu pornești Postgres, proiectul va folosi SQLite implicit.

### 3) Migrații + cont admin

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py init_roles
python manage.py createsuperuser
```

### 4) Pornește serverul

```bash
python manage.py runserver
```

- UI: `http://127.0.0.1:8000/`
- Admin: `http://127.0.0.1:8000/admin/`
- API: `http://127.0.0.1:8000/api/`

## Deploy (Render)

În producție, rulează tipic:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application
```

Setează variabilele de mediu pe Render:
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=0`
- `DATABASE_URL` (Render Postgres)
- `DJANGO_ALLOWED_HOSTS` (și/sau `RENDER_EXTERNAL_HOSTNAME` este detectat automat)

## Arhitectură

Vezi `ARCHITECTURE.md` pentru reguli de organizare (cum adaugi/ștergi feature-uri, unde pune logică, etc.).

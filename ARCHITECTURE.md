## Poultry App architecture

This project is a Django 5 + Django REST Framework application organized by business domains. The goal is to keep concerns isolated so features can be added or removed without touching unrelated modules.

### Layout at a glance
- `config/` — Django settings, URL routing, WSGI entrypoint. Keeps framework wiring and environment configuration.
- `apps/accounts/` — Permission helpers and auth-related behaviors (roles/groups).
- `apps/core/` — Core domain entities (houses, seasons, flocks) and their API layer.
- `apps/health/` — Health tracking (mortality events, treatments) plus corresponding APIs.
- `apps/finance/` — Partners, categories, documents, lines, and payments with DRF serializers/viewsets.
- `apps/reports/` — Read-only reporting endpoints (e.g., season profitability).
- `apps/auditlog/` — Audit event model and utilities for structured change logging.
- `apps/ui/` — Server-rendered views, forms, and templates that sit on top of the domain models/APIs.
- `manage.py`, `docker-compose.yml`, `requirements.txt`, `build.sh` — operational entrypoints and deployment helpers.

### Architectural principles
1. **Domain isolation**: Each `apps/<domain>/` package owns its models, serializers, and views. Cross-domain calls should go through well-defined interfaces (e.g., serializers/viewsets), not reach into internals.
2. **Explicit boundaries**: Permissions live in `apps/accounts.permissions` and are reused across APIs/UI. Auditing is centralized in `apps/auditlog.utils`.
3. **Thin frameworks, rich models**: Business rules should sit in models/forms/serializers, keeping views slim (e.g., `DocumentLine.save` recalculates totals; forms validate stock and mortality limits).
4. **Read-only reporting**: Reporting endpoints (`apps/reports.api`) do not mutate state, keeping analytics separate from write paths.
5. **Idempotent operations**: Helpers like `log_event` and `snapshot` are safe to call repeatedly and are used consistently around create/update/delete flows.

### Adding a feature (recommended workflow)
1. **Choose the domain**: Create or extend an app under `apps/<domain>/`. If it spans multiple concerns, consider a new app to keep boundaries clean.
2. **Define data**: Add/modify models and migrations inside that app.
3. **Expose APIs**: Add DRF serializers/viewsets in the same app and register them in `config/urls.py` via the router.
4. **Permissions**: Reuse or extend `apps.accounts.permissions` so access is role-driven.
5. **UI**: Add forms/views/templates under `apps/ui/` that consume the serializers or models (keep UI logic thin; reuse validation from forms/serializers).
6. **Auditing**: Wrap mutating actions with `apps.auditlog.utils.log_event` and use `snapshot` for before/after payloads.
7. **Testing & checks**: Run migrations, unit tests, and any linters you add. Keep build scripts (`build.sh`) in sync if new steps are required.

### Removing or deprecating a feature
1. Remove UI entrypoints (urls/templates/views) first, then DRF routes, then models/migrations.
2. Clean up audit hooks and permissions specific to that feature.
3. Keep data migrations to preserve history where needed; avoid silent data loss.

### Extending for scalability
- Keep new dependencies minimal; configure them centrally in `requirements.txt` and settings.
- Prefer query annotations/aggregates close to the data layer (see `apps/ui/views.dashboard` for aggregation patterns).
- For heavier workloads, consider moving long-running jobs into Celery or background tasks, but keep orchestration code in the owning app.

### Notes on removed bootstrap scripts
Scaffolding and one-off patch scripts were deleted to reduce noise. All active logic lives in the `apps/` packages and Django configuration above; future automation should live alongside the features they support (e.g., management commands inside each app).

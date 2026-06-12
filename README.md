# Dragon Den Compendium

Dragon Den Compendium is an open source D&D DM helper app (roughly 70% AI + vibe-coded) for Desktop, Laptop, and iPad.  
It is built with Django + HTMX for a local-first workflow, with optional Docker deployment.

## What It Does

Dragon Den is an all-in-one DM workspace:

- Global compendium of monsters, spells, items, classes, races, feats, and backgrounds
- Game + Encounter workflow with reusable Game Players
- Turn tracker with initiative, HP, status effects, monster quick-view modal, and player card popup
- Scratchpad notes with autosave
- Dice roller
- Random compendium picker
- Fight Club XML import (upload per user or server-wide XML path)
- OpenAI-powered magic item generation (optional)

Regular users own their games, tracker entries, notes, and the custom compendium objects they create. Staff users (managed through the Django admin at `/admin/`) can additionally edit shared imported/official compendium content.

## Visuals

The project is optimized for Desktop/Laptop workflows and supports iPad-sized responsive layouts for tracker and compendium usage.

Light Mode is currently incomplete and still being tuned.

## Screenshots

Home / Dashboard (Image #1):

![Image #1 - Home Dashboard](docs/images/Home%20Page.png)

Compendium (Image #2):

![Image #2 - Compendium](docs/images/Compendium%20page.png)

## Tech Stack

- Python `3.14.x`
- Django `5.2.x` (LTS)
- SQLite (WAL mode, busy timeout, immediate transactions)
- Django templates + HTMX + SortableJS (self-hosted under `static/vendor/`)
- defusedxml for safe compendium XML parsing
- OpenAI Python SDK (optional feature)
- Gunicorn + WhiteNoise (Docker runtime)
- Optional Caddy reverse proxy for TLS and host routing

## Core Architecture

Apps:

- `core`: auth/signup, settings modal, XML import flows, health endpoint
- `compendium`: object/tag/favorite models, search/filter, rich preview/rules extraction
- `games`: campaign records + per-game object instances
- `tracker`: turn order/status effects + modals + drag reorder
- `notes`: private per-user scratchpad
- `utilities`: magic item generator, dice tool, random item picker

Settings split:

- `dragon_den/settings/base.py` — hardened defaults; WSGI/ASGI and Docker use this
- `dragon_den/settings/local.py` — development (`DEBUG=True`); `manage.py` defaults to this

Non-debug deployments refuse to start with a placeholder `SECRET_KEY` unless
you explicitly set `REQUIRE_STRONG_SECRET_KEY=0`.

## Local Development

### 1. Create virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create `.env` (or export env vars directly). Use `.env.example` as the template.

Important variables:

- `SECRET_KEY` (generate: `python -c "import secrets; print(secrets.token_urlsafe(50))"`)
- `REQUIRE_STRONG_SECRET_KEY` (defaults to `1` whenever `DEBUG` is false; placeholder keys abort startup)
- `FIELD_ENCRYPTION_KEY` (optional dedicated key for encrypting stored user API keys; lets you rotate `SECRET_KEY` without losing them)
- `DEBUG` (`false` by default)
- `ALLOWED_HOSTS` (comma-separated)
- `CSRF_TRUSTED_ORIGINS` (comma-separated full origins)
- `SQLITE_PATH` (optional custom DB path)
- `WEB_PORT_BIND` (default `127.0.0.1:8000:8000`)
- `TRUST_PROXY_SSL_HEADER` (set `1` only when behind a reverse proxy that sets `X-Forwarded-Proto`)
- `OPENAI_API_KEY` (optional, needed for magic item generation)
- `OPENAI_DEFAULT_MODEL` (default: `gpt-5-mini`)
- `SERVER_COMPENDIUM_XML_PATH` (optional server-side XML path)
- `SERVER_COMPENDIUM_SYSTEM` (default: `dnd5e`)
- `COMPENDIUM_IMPORT_ASYNC` (default `1`; run imports in a background thread)
- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
- `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`
- `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`

### 3. Run

```powershell
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver
```

Open: `http://127.0.0.1:8000`

## XML Import

### CLI import

```powershell
.\.venv\Scripts\python manage.py import_fightclub_xml --file dnd.xml --system dnd5e
```

Import characteristics:

- Upsert-style and idempotent, runs in a single transaction with bulk reads/writes
- XML is parsed with `defusedxml` (entity-expansion attacks rejected)
- Tries external id first; a database unique constraint on
  `(system, object_type, external_id)` guarantees no duplicates
- Falls back to deterministic hash id when external id is missing
- Secondary match by `(system, object_type, name)` preserves stable ids for
  earlier imports, but never overwrites custom or official objects

### In-app import

Use top-right `Settings`:

- Upload your own XML file
- Or enable server-wide XML toggle (when `SERVER_COMPENDIUM_XML_PATH` is set)
- Remove your imported XML-linked data

## Docker (Full Runtime)

### Quick start

```bash
docker compose up --build
```

Startup behavior:

- `migrate` (toggle with `DJANGO_MIGRATE`)
- `collectstatic` (toggle with `DJANGO_COLLECTSTATIC`)
- startup `perf_guard` in warning mode against a throwaway scratch database,
  never the live one (toggle with `PERF_GUARD_ON_STARTUP`)

Container runtime:

- Gunicorn app server
- Health check endpoint: `/healthz/`
- SQLite volume at `/app/data`
- Optional XML mount: `./compendium_xml -> /app/compendium_xml`
- Multi-stage image build with dependency builder stage
- Runtime process drops privileges to non-root `app` user before Django/Gunicorn startup

### Easy OpenAI + server-wide XML config

1. Copy env template:

```bash
cp .env.example .env
```

2. OpenAI:

- Set `OPENAI_API_KEY=...`
- Optional: change `OPENAI_DEFAULT_MODEL`

3. Server-wide XML:

- Place file at: `./compendium_xml/server-compendium.xml`
- Keep:
  - `SERVER_COMPENDIUM_XML_PATH=/app/compendium_xml/server-compendium.xml`
  - `SERVER_COMPENDIUM_SYSTEM=dnd5e`

Startup warnings:

- If OpenAI key is missing: generation stays disabled, container still starts
- If XML path is set but file missing: warning only, container still starts

## Reverse Proxy (Optional Caddy)

For local/proxied mode:

```bash
docker compose --profile proxy up --build
```

Set in `.env`:

- `CADDY_SITE_ADDRESS`
  - local: `localhost`
  - production: `dnd.example.com`
- `CADDY_EMAIL` (recommended for production cert management)

When using domain routing, set Django hosts/origins accordingly:

- `ALLOWED_HOSTS=dnd.example.com`
- `CSRF_TRUSTED_ORIGINS=https://dnd.example.com`

## Production Overlay

Use production overlay defaults:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This overlay:

- forces `DEBUG=false`
- enables Caddy by default
- keeps migrate/collectstatic/perf-startup hooks on (configurable by env)
- increases default gunicorn workers
- sets restart policy to `always`
- sets secure-cookie/HTTPS settings via env defaults in production (including HSTS and `TRUST_PROXY_SSL_HEADER=1`)
- binds app port to loopback by default (`127.0.0.1:8000:8000`)
- applies container hardening (`no-new-privileges`, `cap_drop: ALL` plus only the
  `CHOWN`/`SETUID`/`SETGID` capabilities the privilege-dropping entrypoint needs,
  tmpfs `/tmp` for web)

## Internet Deployment Security

If you expose the app outside your local network, use this minimum checklist.

Login and signup are rate-limited per IP out of the box.

### Required

- Set a strong random `SECRET_KEY` (placeholder values abort startup by default)
- Set `DEBUG=false`
- Set exact `ALLOWED_HOSTS` (domain only, no wildcard unless intentional)
- Set exact `CSRF_TRUSTED_ORIGINS` (full `https://...` origins)
- Run behind Caddy with TLS (`docker compose --profile proxy ...`)
- Set `WEB_PORT_BIND=127.0.0.1:8000:8000` so Gunicorn is not publicly exposed

### Recommended hardened values

Add to `.env`:

```dotenv
REQUIRE_STRONG_SECRET_KEY=1
WEB_PORT_BIND=127.0.0.1:8000:8000
SECURE_SSL_REDIRECT=1
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
SECURE_CONTENT_TYPE_NOSNIFF=1
SECURE_REFERRER_POLICY=same-origin
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=1
SECURE_HSTS_PRELOAD=0
```

Notes:

- Enable HSTS only after HTTPS is working correctly for your domain.
- Keep `SECURE_HSTS_PRELOAD=0` unless you intentionally submit your domain to the preload list.
- If you run without a reverse proxy/TLS, do **not** enable strict HTTPS redirects until TLS is in place.

## Performance Guard

Local strict check:

```bash
python scripts/perf_guard.py
```

Startup warning mode (used by Docker entrypoint):

```bash
python scripts/perf_guard.py --warn-only --iterations 2
```

Measured routes:

- `compendium_detail`
- `tracker_dashboard`
- `tracker_quick_update`

If thresholds exceed:

- strict mode exits non-zero
- warn-only logs warnings and continues startup

## Docker CI Smoke Test

Run local smoke check (set `USE_PROD_OVERLAY=1` to exercise the hardened overlay):

```bash
scripts/docker_smoke_test.sh
USE_PROD_OVERLAY=1 scripts/docker_smoke_test.sh
```

What it validates:

- compose build for `web`
- container startup + healthcheck
- `GET /healthz/` readiness

CI (GitHub Actions):

- `.github/workflows/tests.yml` — Django system checks + full test suite
- `.github/workflows/docker-smoke.yml` — smoke test for both the base compose and the production overlay
- `.github/workflows/perf-guard.yml` — query-count and payload-size budgets (wall-clock thresholds are skipped on shared runners)
- `.github/dependabot.yml` — weekly dependency updates (pip, actions, docker)

## Testing

Run full test suite:

```powershell
.\.venv\Scripts\python manage.py test
```

## License

MIT — see [LICENSE](LICENSE).

## Project Status

This is an active open source D&D DM helper with a strong local-first workflow and optional full Docker deployment path.  
The current UI is optimized for Desktop/Laptop and works on iPad-sized layouts (responsive templates + modal-driven interactions).

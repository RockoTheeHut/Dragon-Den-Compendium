# Dragon Den Compendium

Open source D&D DM helper app (roughly 70% AI vibe-coded) for Desktop, Laptop, and iPad.  
Built with Django + HTMX for a local-first workflow with optional Docker deployment.

## What It Does

Dragon Den is an all-in-one DM workspace:

- Global compendium of monsters, spells, items, classes, races, feats, and backgrounds
- Per-game object instances (copy from global, customize per campaign)
- Turn tracker with initiative, HP, status effects, and monster quick-view modal
- Scratchpad notes with autosave
- Dice roller
- Random compendium picker
- Fight Club XML import (upload per user or server-wide XML path)
- OpenAI-powered magic item generation (optional)

All authenticated users are regular users. There is no Django admin/staff role workflow in this project.

## Visuals

The project is optimized for Desktop/Laptop workflows and supports iPad-sized responsive layouts for tracker and compendium usage.

[Image #1]

## Tech Stack

- Python `3.14.x`
- Django `5.2.8`
- SQLite
- Django templates + HTMX + SortableJS
- OpenAI Python SDK `2.17.0` (optional feature)
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

- `dragon_den/settings/base.py`
- `dragon_den/settings/local.py`

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

- `SECRET_KEY`
- `DEBUG` (`false` by default)
- `ALLOWED_HOSTS` (comma-separated)
- `CSRF_TRUSTED_ORIGINS` (comma-separated full origins)
- `SQLITE_PATH` (optional custom DB path)
- `WEB_PORT_BIND` (default `8000:8000`, set `127.0.0.1:8000:8000` when behind Caddy)
- `OPENAI_API_KEY` (optional, needed for magic item generation)
- `OPENAI_DEFAULT_MODEL` (default: `gpt-5-mini`)
- `SERVER_COMPENDIUM_XML_PATH` (optional server-side XML path)
- `SERVER_COMPENDIUM_SYSTEM` (default: `dnd5e`)
- `REQUIRE_STRONG_SECRET_KEY` (`1` recommended in production)
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

- Upsert-style and idempotent
- Tries external id first
- Falls back to deterministic hash id when external id is missing
- Secondary match by `(system, object_type, name)` preserves stable ids

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
- startup `perf_guard` in warning mode (toggle with `PERF_GUARD_ON_STARTUP`)

Container runtime:

- Gunicorn app server
- Health check endpoint: `/healthz/`
- SQLite volume at `/app/data`
- Optional XML mount: `./compendium_xml -> /app/compendium_xml`

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
- sets secure-cookie/HTTPS settings via env defaults in production

## Internet Deployment Security

If you expose the app outside your local network, use this minimum checklist.

### Required

- Set a strong random `SECRET_KEY`
- Set `REQUIRE_STRONG_SECRET_KEY=1`
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

## Testing

Run full test suite:

```powershell
.\.venv\Scripts\python manage.py test
```

## Project Status

This is an active open source D&D DM helper with a strong local-first workflow and optional full Docker deployment path.  
The current UI is optimized for Desktop/Laptop and works on iPad-sized layouts (responsive templates + modal-driven interactions).

# Dragon Den Compendium

Open Source Local-first Django web app for Dungeon Masters with a global compendium, per-game object copies, turn tracking, shared notes, dice rolling, Fight Club XML import, and OpenAI text-based magic item generation.

## Tech Stack

- Python 3.14.2
- Django 5.2.8
- SQLite (default)
- Django templates + HTMX
- OpenAI Responses API (text only)

## Setup (venv + requirements.txt)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file (or set env vars in shell) with:

- `SECRET_KEY`
- `DEBUG` (optional; default `false`)
- `ALLOWED_HOSTS` (optional; comma-separated)
- `SQLITE_PATH` (optional; path to sqlite database file)
- `CSRF_TRUSTED_ORIGINS` (optional; comma-separated full origins)
- `OPENAI_API_KEY`
- `OPENAI_DEFAULT_MODEL`
- `SERVER_COMPENDIUM_XML_PATH` (optional; absolute path in container/host)
- `SERVER_COMPENDIUM_SYSTEM` (optional; defaults to `dnd5e`)

Example values are in `.env.example`.

## Run

```powershell
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver
```

Open `http://127.0.0.1:8000`.

## Docker (Full App Runtime)

Build and run:

```bash
docker compose up --build
```

The container startup script runs migrations and `collectstatic` automatically.

Default container URL:

- `http://127.0.0.1:8000`

Container details:

- App server: `gunicorn`
- Health endpoint: `/healthz/`
- SQLite persistence volume mounted at `/app/data` (configured by `SQLITE_PATH=/app/data/db.sqlite3`)

## Auth

- Self-signup is available at `/accounts/signup/`.
- Django admin is available at `/admin/`.

Create an admin user if needed:

```powershell
.\.venv\Scripts\python manage.py createsuperuser
```

## Fight Club XML Import

```powershell
.\.venv\Scripts\python manage.py import_fightclub_xml --file dnd.xml --system dnd5e
```

Import behavior:

- Imports monsters, spells, and items.
- Idempotent upsert.
- Matches by external id when present.
- Falls back to deterministic generated external id.
- Secondary match by `(system, object_type, name)` preserves stable external ids.

### In-App Import (Per User)

- Open top-right `Settings`.
- `Import Your XML`: upload a Fight Club `.xml` file and import into the shared compendium.
- `Use server-wide XML`: toggle this option to import from `SERVER_COMPENDIUM_XML_PATH` for Docker/server-wide workflows.
- `Remove My Imported XML`: removes imported objects linked to your account.

## Tests

```powershell
.\.venv\Scripts\python manage.py test
```

## Notes

- The app is configured with split settings: `dragon_den/settings/base.py` and `dragon_den/settings/local.py`.
- OpenAI SDK version is pinned to `2.17.0`.

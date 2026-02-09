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
- `OPENAI_API_KEY`
- `OPENAI_DEFAULT_MODEL`

Example values are in `.env.example`.

## Run

```powershell
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver
```

Open `http://127.0.0.1:8000`.

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

## Tests

```powershell
.\.venv\Scripts\python manage.py test
```

## Notes

- The app is configured with split settings: `dragon_den/settings/base.py` and `dragon_den/settings/local.py`.
- OpenAI SDK version is pinned to `2.17.0`.

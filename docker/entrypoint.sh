#!/bin/sh
set -e

if [ "$(id -u)" = "0" ] && [ "${DDC_PRIV_DROPPED:-0}" != "1" ]; then
  mkdir -p /app/data /app/staticfiles
  chown -R app:app /app/data /app/staticfiles
  export DDC_PRIV_DROPPED=1
  exec gosu app:app "$0" "$@"
fi

echo "Starting Dragon Den Compendium..."

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "WARNING: OPENAI_API_KEY is empty. Magic item generation will be disabled until configured."
fi

if [ -n "${SERVER_COMPENDIUM_XML_PATH:-}" ]; then
  if [ ! -f "${SERVER_COMPENDIUM_XML_PATH}" ]; then
    echo "WARNING: SERVER_COMPENDIUM_XML_PATH is set but file does not exist: ${SERVER_COMPENDIUM_XML_PATH}"
  else
    echo "Server compendium XML detected at: ${SERVER_COMPENDIUM_XML_PATH}"
  fi
else
  echo "INFO: SERVER_COMPENDIUM_XML_PATH is not set. Server-wide XML import toggle will be unavailable."
fi

if [ "${DJANGO_MIGRATE:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

if [ "${PERF_GUARD_ON_STARTUP:-1}" = "1" ]; then
  echo "Running perf guard in startup warning mode (scratch database)..."
  PERF_GUARD_DB="${PERF_GUARD_SQLITE_PATH:-/tmp/perf-guard.sqlite3}"
  rm -f "${PERF_GUARD_DB}" "${PERF_GUARD_DB}-wal" "${PERF_GUARD_DB}-shm"
  {
    SQLITE_PATH="${PERF_GUARD_DB}" python manage.py migrate --noinput --verbosity 0 \
      && SQLITE_PATH="${PERF_GUARD_DB}" python scripts/perf_guard.py --warn-only --iterations "${PERF_GUARD_STARTUP_ITERATIONS:-2}"
  } || echo "WARNING: perf guard run failed; continuing startup."
  rm -f "${PERF_GUARD_DB}" "${PERF_GUARD_DB}-wal" "${PERF_GUARD_DB}-shm"
fi

exec gunicorn dragon_den.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"

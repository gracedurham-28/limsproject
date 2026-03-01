#!/usr/bin/env bash
# Export Postgres database and globals using connection info from .env (or env vars).
# Usage: ./scripts/db_export.sh /path/to/output_dir
# Outputs: app_db.dump (pg_dump custom format) and db_globals.sql

set -euo pipefail
OUTDIR=${1:-./db_dumps}
mkdir -p "$OUTDIR"

# Load .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

: ${POSTGRES_HOST:=localhost}
: ${POSTGRES_PORT:=5432}
: ${POSTGRES_USER:=postgres}
: ${POSTGRES_PASSWORD:=}
: ${POSTGRES_DB:=lims_app}

if [ -z "$POSTGRES_PASSWORD" ]; then
  echo "Warning: POSTGRES_PASSWORD not set in environment; pg_dump may prompt for password or fail."
fi

export PGPASSWORD="$POSTGRES_PASSWORD"
DUMP_PATH="$OUTDIR/app_db.dump"
GLOBALS_PATH="$OUTDIR/db_globals.sql"

echo "Creating DB dump to $DUMP_PATH"
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -Fc -f "$DUMP_PATH" "$POSTGRES_DB"

echo "Exporting DB globals to $GLOBALS_PATH"
pg_dumpall -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" --globals-only > "$GLOBALS_PATH"

echo "Done. Files created:"
echo "  $DUMP_PATH"
echo "  $GLOBALS_PATH"

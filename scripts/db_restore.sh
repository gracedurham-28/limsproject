#!/usr/bin/env bash
# Restore Postgres database dump and globals exported by db_export.sh
# Usage: ./scripts/db_restore.sh /path/to/dumpdir

set -euo pipefail
DUMP_DIR=${1:-./db_dumps}
DUMP_PATH="$DUMP_DIR/app_db.dump"
GLOBALS_PATH="$DUMP_DIR/db_globals.sql"

if [ ! -f "$DUMP_PATH" ]; then
  echo "Dump file not found: $DUMP_PATH"
  exit 1
fi

# Load .env for DB connection info
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

: ${POSTGRES_HOST:=localhost}
: ${POSTGRES_PORT:=5432}
: ${POSTGRES_USER:=postgres}
: ${POSTGRES_PASSWORD:=}

export PGPASSWORD="$POSTGRES_PASSWORD"

if [ -f "$GLOBALS_PATH" ]; then
  echo "Restoring DB globals (roles)..."
  psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -f "$GLOBALS_PATH"
fi

# Use pg_restore -C to create DB if dump contains it; otherwise create DB first
echo "Restoring DB from $DUMP_PATH"
pg_restore -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres --clean --create "$DUMP_PATH"

echo "Restore complete."

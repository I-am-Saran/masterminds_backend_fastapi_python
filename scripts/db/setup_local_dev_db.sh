#!/usr/bin/env bash
# Create local PostgreSQL role/database for Kaizen dev (matches .env defaults).
# Run after restoring a backup SQL dump, or on a fresh local Postgres install.
set -euo pipefail

DB_USER="${DB_USER:-praveena}"
DB_PASS="${DB_PASS:-lllfff}"
DB_NAME="${DB_NAME:-kaizen_dev}"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
# Superuser for admin commands (peer auth on Linux often works as: sudo -u postgres ...)
PG_SUPERUSER="${PG_SUPERUSER:-postgres}"

psql_admin() {
  if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 "$@"
  else
    psql -U "$PG_SUPERUSER" -h "$PG_HOST" -p "$PG_PORT" -v ON_ERROR_STOP=1 "$@"
  fi
}

echo "Checking PostgreSQL on ${PG_HOST}:${PG_PORT}..."
if ! psql_admin -d postgres -c "SELECT 1" >/dev/null 2>&1; then
  echo "PostgreSQL is not reachable. Start it first, e.g.:"
  echo "  sudo systemctl start postgresql"
  exit 1
fi

echo "Creating role ${DB_USER} (if missing)..."
psql_admin -d postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 \
  || psql_admin -d postgres -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"

echo "Creating database ${DB_NAME} (if missing)..."
psql_admin -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || psql_admin -d postgres -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

psql_admin -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

echo "Done. Test with:"
echo "  PGPASSWORD='${DB_PASS}' psql -h ${PG_HOST} -p ${PG_PORT} -U ${DB_USER} -d ${DB_NAME} -c 'SELECT 1'"

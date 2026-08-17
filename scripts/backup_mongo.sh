#!/usr/bin/env bash
# Per-tenant MongoDB backup and restore (docs/ENVIRONMENTS.md §4, DEPLOYMENT_PLAN
# Phase C).
#
# Database-per-tenant makes this genuinely simple: each company IS a database, so
# one company can be dumped or restored without touching any other. That is the
# property that lets you fix one customer's mistake without a maintenance window.
#
#   ./scripts/backup_mongo.sh backup                  # control plane + every tenant
#   ./scripts/backup_mongo.sh list                    # what is on disk
#   ./scripts/backup_mongo.sh restore <dir> <db>      # restore ONE database
#
# Runs mongodump/mongorestore INSIDE the mongo container, so the host needs no
# MongoDB tooling and the database stays unpublished.
#
# Credentials come from .env.production (never passed on the command line, where
# they would be visible in `ps`).

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"
SERVICE="mongo"
BACKUP_ROOT="${BACKUP_ROOT:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [[ ! -f .env.production ]]; then
  echo "missing .env.production — cannot read database credentials" >&2
  exit 1
fi
# shellcheck disable=SC1091
set -a; source .env.production; set +a

: "${MONGO_ROOT_USER:?MONGO_ROOT_USER must be set in .env.production}"
: "${MONGO_ROOT_PASSWORD:?MONGO_ROOT_PASSWORD must be set in .env.production}"

# Auth flags reused by every invocation. --quiet keeps cron mail readable.
mongo_exec() {
  $COMPOSE exec -T "$SERVICE" "$@"
}

cmd_backup() {
  local stamp dest
  stamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
  dest="$BACKUP_ROOT/$stamp"
  mkdir -p "$dest"

  echo "backing up to $dest"

  # One archive per database. Per-database (not a single cluster dump) is the
  # whole point: restoring one tenant must never require touching another.
  local dbs
  dbs="$(mongo_exec mongosh --quiet \
    -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
    --eval 'db.adminCommand({listDatabases:1,nameOnly:true}).databases
              .map(d => d.name)
              .filter(n => !["admin","local","config"].includes(n))
              .join("\n")')"

  if [[ -z "$dbs" ]]; then
    echo "no application databases found — nothing to back up" >&2
    exit 1
  fi

  # Read the list into an array FIRST. Looping with `while read` over a here-string
  # while calling `docker compose exec` inside the body silently drops every
  # database after the first: exec inherits the loop's stdin and consumes it. The
  # symptom is a backup that reports success having dumped only one database —
  # which you would discover at restore time, i.e. the worst possible moment.
  local -a db_list=()
  while IFS= read -r db; do
    [[ -n "$db" ]] && db_list+=("$db")
  done <<< "$dbs"

  local count=0
  for db in "${db_list[@]}"; do
    echo "  dumping $db"
    # --archive to stdout, gzipped, captured on the host: no shared volume needed
    # and nothing is left inside the container. </dev/null is belt-and-braces so
    # exec can never reach for the caller's stdin.
    mongo_exec mongodump \
      -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
      --db "$db" --archive --gzip < /dev/null > "$dest/$db.archive.gz"
    count=$((count + 1))
  done

  echo "$count database(s) dumped"
  if (( count != ${#db_list[@]} )); then
    echo "WARNING: expected ${#db_list[@]} database(s) but dumped $count" >&2
    exit 1
  fi

  # Retention. Deliberately prunes only inside BACKUP_ROOT and only directories
  # matching the timestamp shape this script creates.
  if [[ -d "$BACKUP_ROOT" ]]; then
    find "$BACKUP_ROOT" -maxdepth 1 -type d -name '20*T*Z' -mtime "+$RETENTION_DAYS" \
      -exec rm -rf {} + 2>/dev/null || true
  fi

  echo
  echo "REMINDER: this backup is on the same disk as the database it protects."
  echo "Copy $dest off-box, or it will not survive the failure it exists for."
}

cmd_list() {
  if [[ ! -d "$BACKUP_ROOT" ]]; then
    echo "no backups yet ($BACKUP_ROOT does not exist)"
    return
  fi
  local dir
  for dir in "$BACKUP_ROOT"/*/; do
    [[ -d "$dir" ]] || continue
    echo "$dir"
    ls -lh "$dir" | awk 'NR>1 {printf "    %-40s %s\n", $9, $5}'
  done
}

cmd_restore() {
  local dir="${1:-}" db="${2:-}"
  if [[ -z "$dir" || -z "$db" ]]; then
    echo "usage: $0 restore <backup-dir> <database>" >&2
    echo "   e.g. $0 restore backups/2026-08-17T12-00-00Z erp_tenant_acme" >&2
    exit 2
  fi
  local archive="$dir/$db.archive.gz"
  [[ -f "$archive" ]] || { echo "no such archive: $archive" >&2; exit 1; }

  echo "About to restore '$db' from $archive."
  echo "--drop is used: the CURRENT contents of '$db' will be replaced."
  read -r -p "Type the database name again to confirm: " confirm
  [[ "$confirm" == "$db" ]] || { echo "aborted"; exit 1; }

  mongo_exec mongorestore \
    -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
    --archive --gzip --drop --nsInclude "$db.*" < "$archive"

  echo "restored $db"
}

case "${1:-}" in
  backup)  cmd_backup ;;
  list)    cmd_list ;;
  restore) shift; cmd_restore "$@" ;;
  *)
    echo "usage: $0 {backup|list|restore <dir> <db>}" >&2
    exit 2
    ;;
esac

#!/bin/sh
# CodeMap container entrypoint: restore -> verify -> replicate + serve.
#
# Replication is OFF unless LITESTREAM_ENABLED=true, so `docker run` on a laptop
# just works. When ON, the order matters and every step fails CLOSED:
#
#   1. If there is no local DB (an ephemeral host always starts this way),
#      restore the newest copy from the replica.
#   2. Verify the file with SQLite's own integrity check. If it is damaged,
#      set it aside and fall back to older points in time.
#   3. If a backup EXISTS but cannot be restored cleanly, REFUSE TO START.
#      Booting empty would make Litestream replicate an empty database over the
#      good history, turning a recoverable problem into permanent data loss.
#   4. Only then start Litestream, which in turn runs the web server (-exec),
#      forwards stop signals to it, and does a final sync on shutdown.
set -eu
umask 077   # every file we create (DB, -wal, -shm, restore output) is owner-only

HOME_DIR="${CODEMAP_HOME:-/srv/codemap}"
DB="${CODEMAP_DB_PATH:-/data/codemap.db}"
PY="${PYTHON:-python}"
CONFIG="${LITESTREAM_CONFIG:-$HOME_DIR/docker/litestream.yml}"
export CODEMAP_DB_PATH="$DB"

log() { printf '[entrypoint] %s\n' "$*"; }
die() { printf '[entrypoint] FATAL: %s\n' "$*" >&2; exit 1; }

# Behind the platform's proxy every request comes from the proxy's address;
# uvicorn only trusts X-Forwarded-For from addresses listed here, and without
# it the per-client rate limits would see ALL visitors as one client. '*' is
# only acceptable when the container is reachable solely through that proxy.
export FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"

# Defaults so the ${VAR} expansion in litestream.yml never hits an unset name.
export LITESTREAM_PATH="${LITESTREAM_PATH:-codemap}"
export LITESTREAM_ENDPOINT="${LITESTREAM_ENDPOINT:-}"
export LITESTREAM_REGION="${LITESTREAM_REGION:-}"
export LITESTREAM_FORCE_PATH_STYLE="${LITESTREAM_FORCE_PATH_STYLE:-false}"

mkdir -p "$(dirname "$DB")"
cd "$HOME_DIR/app"   # modules import as top-level names (analyzer, services, ...)

APP_CMD="uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"

if [ "${LITESTREAM_ENABLED:-false}" != "true" ]; then
  log "WARNING: replication is OFF (LITESTREAM_ENABLED is not 'true'). Data lives only on this container's disk."
  exec $APP_CMD
fi

command -v litestream >/dev/null 2>&1 || die "litestream binary not found on PATH"
[ -f "$CONFIG" ] || die "litestream config not found: $CONFIG"

case "$CONFIG" in
  *file.yml) [ -n "${LITESTREAM_FILE_REPLICA_PATH:-}" ] || die "LITESTREAM_FILE_REPLICA_PATH is not set" ;;
  *) for v in LITESTREAM_BUCKET LITESTREAM_ACCESS_KEY_ID LITESTREAM_SECRET_ACCESS_KEY; do
       eval "val=\${$v:-}"
       [ -n "$val" ] || die "$v is not set (needed when LITESTREAM_ENABLED=true)"
     done ;;
esac

# Litestream retries an unreachable replica silently and with no deadline, so a
# bad endpoint or credentials would hang the deploy forever with no message.
# Bound it, and restore into a side file: a restore killed half-way must never
# leave a partial database at the real path.
RESTORE_TIMEOUT="${LITESTREAM_RESTORE_TIMEOUT:-120}"

restore_to() {
  out="$1"; shift
  rm -f "$out" "$out-wal" "$out-shm"
  if timeout "$RESTORE_TIMEOUT" litestream restore -config "$CONFIG" -if-replica-exists "$@" -o "$out" "$DB"; then
    return 0
  else
    rc=$?
    if [ "$rc" -eq 124 ]; then log "restore timed out after ${RESTORE_TIMEOUT}s"; fi
    rm -f "$out" "$out-wal" "$out-shm"
    return "$rc"
  fi
}

healthy() {
  if out=$("$PY" "$HOME_DIR/docker/check_db.py" "$DB"); then rc=0; else rc=$?; fi
  log "check: $out"
  return "$rc"
}

quarantine() {
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  for f in "$DB" "$DB-wal" "$DB-shm"; do
    if [ -e "$f" ]; then mv "$f" "$f.corrupt-$ts"; fi
  done
  log "damaged files set aside as *.corrupt-$ts"
  return 0
}

if [ -e "$DB" ]; then
  log "local database present (persistent volume, or a warm restart)"
  if ! healthy; then quarantine; fi
fi

if [ ! -e "$DB" ]; then
  log "no local database: restoring newest copy from the replica"
  restore_to "$DB.restoring" \
    || die "could not read the replica. NOT starting: an empty database would be replicated over the existing backup history. Fix connectivity/credentials and redeploy."
  if [ -e "$DB.restoring" ]; then mv "$DB.restoring" "$DB"; fi

  if [ -e "$DB" ]; then
    if healthy; then
      log "restore OK"
    else
      quarantine
      recovered=false
      for ago in "1 hour" "6 hours" "24 hours"; do
        ts=$(date -u -d "$ago ago" +%Y-%m-%dT%H:%M:%SZ)
        log "newest copy is damaged; trying point-in-time restore at $ts"
        if restore_to "$DB.restoring" -timestamp "$ts" && [ -e "$DB.restoring" ] && mv "$DB.restoring" "$DB" && healthy; then
          recovered=true
          log "recovered from an older copy ($ago ago): changes newer than that are lost"
          break
        fi
        if [ -e "$DB" ]; then quarantine; fi
      done
      [ "$recovered" = "true" ] || die "replica exists but no usable copy found. NOT starting (would overwrite history). Restore manually: litestream restore -timestamp <T> ..."
    fi
  else
    log "replica is empty: first boot, starting a fresh database"
  fi
fi

log "starting replication + server"
exec litestream replicate -config "$CONFIG" -exec "$APP_CMD"

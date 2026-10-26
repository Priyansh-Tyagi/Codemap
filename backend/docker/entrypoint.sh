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
#   3. If a backup EXISTS but cannot be restored cleanly (provider refusing
#      requests, unreachable, timed out, or no usable copy), run DEGRADED: start
#      the app with replication OFF and leave the bucket untouched. The safety
#      property is "never replicate a fresh database over existing history", NOT
#      "never start": a second timeline written to the same path displaces the
#      old one (measured), so replicating from an empty start could bury the
#      backup. Degraded mode ends at the next cold start, which retries the
#      restore on its own. The state is published for the UI (see write_status).
#   4. Otherwise start Litestream, which in turn runs the web server (-exec),
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

# Where the app reads the storage state the UI shows (GET /api/status). Rewritten
# on EVERY start, so a stale file from an earlier run can never be believed.
export CODEMAP_STORAGE_STATUS_FILE="${CODEMAP_STORAGE_STATUS_FILE:-/tmp/codemap-storage.json}"

# write_status <state> [reason]. Only fixed words go in (no provider text), so
# nothing attacker-influenced ever reaches the page.
write_status() {
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if [ -n "${2:-}" ]; then
    body="{\"state\":\"$1\",\"reason\":\"$2\",\"since\":\"$ts\"}"
  else
    body="{\"state\":\"$1\",\"since\":\"$ts\"}"
  fi
  { printf '%s\n' "$body" > "$CODEMAP_STORAGE_STATUS_FILE.tmp" && mv "$CODEMAP_STORAGE_STATUS_FILE.tmp" "$CODEMAP_STORAGE_STATUS_FILE"; } \
    || log "could not write $CODEMAP_STORAGE_STATUS_FILE (the UI will not show the storage state)"
  return 0
}

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
  write_status disabled
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
  rlog="$out.log"
  if timeout "$RESTORE_TIMEOUT" litestream restore -config "$CONFIG" -if-replica-exists "$@" -o "$out" "$DB" >"$rlog" 2>&1; then
    cat "$rlog"; rm -f "$rlog"
    return 0
  else
    rc=$?
    cat "$rlog"
    FAIL_REASON=unreachable
    if [ "$rc" -eq 124 ]; then FAIL_REASON=timeout; log "restore timed out after ${RESTORE_TIMEOUT}s"; fi
    # A provider that answers 403 / "cap exceeded" is NOT a bad key or a bad bucket
    # when earlier deploys worked: it is usually a free-tier daily request cap.
    if grep -qiE 'cap exceeded|AccessDenied|status code: 403|StatusCode: 403' "$rlog"; then
      FAIL_REASON=provider_refused
      log "HINT: the storage provider refused the request (403). If this worked before, a daily request cap is the likely cause."
      log "HINT: Backblaze B2: Account > Caps & Alerts, check Class C (list) transactions; the counter resets at midnight UTC. Raise the cap or wait; the app keeps running without backups meanwhile."
    fi
    rm -f "$out" "$out-wal" "$out-shm" "$rlog"
    return "$rc"
  fi
}

# Backup storage cannot be used right now. Start the app anyway, but WITHOUT
# replication, and leave the bucket untouched. No `litestream replicate` may ever
# appear in this function (a test pins that): replicating from an empty start is
# the one thing that could destroy the existing history.
#
# The app runs on its OWN file ($DB.degraded), never on $DB. On a host with a
# persistent volume, a fresh database left at $DB would look "healthy and local" to
# the next start, which would then replicate it over the real history: the same
# timeline-displacement mistake, one restart later. With a separate file, $DB stays
# absent and the next start restores from the backup as it should.
degrade() {  # degrade <reason code> <what happened>
  write_status degraded "$1"
  log "DEGRADED ($1): $2"
  rm -f "$DB.degraded" "$DB.degraded-wal" "$DB.degraded-shm"
  export CODEMAP_DB_PATH="$DB.degraded"
  log "starting the app WITHOUT replication, on $DB.degraded; the existing backup is untouched."
  log "projects saved during this run will not survive a restart; the next cold start retries the restore."
  exec $APP_CMD
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
    || degrade "${FAIL_REASON:-unreachable}" "could not read the backup"
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
      [ "$recovered" = "true" ] || degrade corrupt "a backup exists but no usable copy was found (restore manually: litestream restore -timestamp <T> ...)"
    fi
  else
    log "replica is empty: first boot, starting a fresh database"
  fi
fi

log "starting replication + server"
write_status ok
exec litestream replicate -config "$CONFIG" -exec "$APP_CMD"

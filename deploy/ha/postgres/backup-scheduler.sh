#!/bin/bash
# Backup schedule of one database node, run beside it (the same data directory and socket).
#
# Every minute it asks its node whether it is the primary; only the primary backs up, so after
# a failover the schedule follows the new primary with no change. On the primary it creates the
# stanza once, takes a first full backup when the repository has none (a new standby restores
# from it), then a full backup each week (NEXUS_FULL_BACKUP_WEEKDAY, 7 = Sunday) and a
# differential each other day, after NEXUS_BACKUP_HOUR_UTC. pgBackRest expires old backups by
# its retention settings (PGBACKREST_REPO1_RETENTION_FULL). The write-ahead log is archived
# continuously by the node itself (archive_command), independent of this schedule.
set -uo pipefail

STANZA="${PGBACKREST_STANZA:-nexus}"
HOUR="${NEXUS_BACKUP_HOUR_UTC:-1}"
FULL_DAY="${NEXUS_FULL_BACKUP_WEEKDAY:-7}"
STATE=/var/lib/postgresql/data/.nexus-backup-last

log() { printf '{"event":"%s","node":"%s","detail":"%s"}\n' "$1" "${NEXUS_NODE_NAME:-node}" "${2:-}"; }

is_primary() {
    [ "$(psql -h /var/run/postgresql -U "${POSTGRES_USER:-postgres}" -d postgres -tAc \
        'SELECT NOT pg_is_in_recovery()' 2>/dev/null)" = "t" ]
}

# Stop at once on SIGTERM (docker stop, a failover): a shell waiting in `sleep` would otherwise
# ignore it until the stop timeout, which delayed every failover by that timeout.
trap 'log scheduler.stopped; exit 0' TERM INT

while true; do
    if is_primary; then
        if ! pgbackrest --stanza="$STANZA" check >/dev/null 2>&1; then
            pgbackrest --stanza="$STANZA" stanza-create && log stanza.ready
        fi
        if ! pgbackrest --stanza="$STANZA" info --output=json 2>/dev/null | grep -q '"label"'; then
            log backup.start "first full"
            pgbackrest --stanza="$STANZA" --type=full backup && log backup.done full \
                || log backup.failed full
        fi
        today="$(date -u +%F)"
        if [ "$(date -u +%H)" -ge "$HOUR" ] && [ "$(cat "$STATE" 2>/dev/null)" != "$today" ]; then
            type=diff
            [ "$(date -u +%u)" = "$FULL_DAY" ] && type=full
            log backup.start "$type"
            if pgbackrest --stanza="$STANZA" --type="$type" backup; then
                echo "$today" > "$STATE"
                log backup.done "$type"
            else
                log backup.failed "$type"
            fi
        fi
    fi
    sleep "${NEXUS_BACKUP_POLL_SECONDS:-60}" &
    wait $!
done

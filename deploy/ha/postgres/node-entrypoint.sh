#!/bin/bash
# Entry point of a database node (primary or hot standby) with pgBackRest.
#
# An empty data directory is initialised by role:
#   NEXUS_NODE_ROLE=primary  the official initdb path (then 10-replication.sh);
#   NEXUS_NODE_ROLE=standby  waits for the first backup in the repository, then
#                            `pgbackrest restore --type=standby` and streams from NEXUS_PEER_HOST.
# A data directory that exists starts as it is: a standby has standby.signal, a primary not.
# That is what makes a failover stick: after `promote.sh` the promoted node has no
# standby.signal, and the fenced old primary has one.
set -euo pipefail

PGDATA="${PGDATA:-/var/lib/postgresql/data}"
ROLE="${NEXUS_NODE_ROLE:-primary}"
STANZA="${PGBACKREST_STANZA:-nexus}"
PEER="${NEXUS_PEER_HOST:-}"
# The node's private tmpfs (deploy/ha/compose.yaml): the root filesystem is read-only, and the
# data directory and the socket directory are shared with the backup sidecar, which must not
# read the replication password.
SECRETS_DIR="${NEXUS_SECRETS_DIR:-/run/nexus}"
PASSFILE="${SECRETS_DIR}/replication.pgpass"

if [ "$(id -u)" = "0" ]; then
    install -d -o postgres -g postgres -m 0700 "$PGDATA"
    install -d -o postgres -g postgres -m 0775 /var/run/postgresql
    install -d -o postgres -g postgres -m 0700 "$SECRETS_DIR"
    exec gosu postgres "$0" "$@"
fi

# The replication password for primary_conninfo is kept in a passfile, not in the config.
if [ -n "${NEXUS_REPLICATION_PASSWORD:-}" ]; then
    umask 077
    printf '*:*:*:replicator:%s\n' "$NEXUS_REPLICATION_PASSWORD" > "$PASSFILE"
fi
CONNINFO="host=${PEER} port=5432 user=replicator passfile=${PASSFILE} application_name=${HOSTNAME}"

if [ "$ROLE" = "standby" ] && [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "node-entrypoint: empty standby; waiting for a backup of stanza ${STANZA}"
    for _ in $(seq 1 720); do
        if pgbackrest --stanza="$STANZA" info --output=json 2>/dev/null \
            | grep -q '"label"'; then
            break
        fi
        sleep 5
    done
    pgbackrest --stanza="$STANZA" --type=standby --delta \
        --recovery-option="primary_conninfo=${CONNINFO}" \
        --recovery-option="recovery_target_timeline=latest" \
        restore
fi

# Settings every node needs whichever role it has now. archive_mode=on archives only on the
# primary; restore_command lets a standby (or a recovering node) read the archive.
# NEXUS_ARCHIVE_MODE=off is for a copy restored elsewhere (a drill, a point-in-time recovery
# to inspect): it must never push its own write-ahead log into the production repository.
set -- "$@" \
    -c listen_addresses='*' \
    -c wal_level=replica \
    -c max_wal_senders=10 \
    -c wal_keep_size=1GB \
    -c hot_standby=on \
    -c hot_standby_feedback=on \
    -c archive_mode="${NEXUS_ARCHIVE_MODE:-on}" \
    -c archive_timeout="${NEXUS_ARCHIVE_TIMEOUT_SECONDS:-60}" \
    -c "archive_command=pgbackrest --stanza=${STANZA} archive-push %p" \
    -c "restore_command=pgbackrest --stanza=${STANZA} archive-get %f \"%p\"" \
    -c recovery_target_timeline=latest

if [ -f "$PGDATA/standby.signal" ] && [ -n "$PEER" ]; then
    set -- "$@" -c "primary_conninfo=${CONNINFO}"
fi

exec docker-entrypoint.sh "$@"

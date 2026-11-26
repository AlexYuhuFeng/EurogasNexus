#!/usr/bin/env bash
# Rebuild a failed or fenced node as the hot standby of the current primary.
#
#   deploy/ha/rejoin.sh <node>          e.g.  pg-node1   (after failover.sh pg-node1 pg-node2)
#
# A delta restore from the backup repository (only changed files are copied) of the latest
# backup as a standby, then the node starts, replays the archive and streams from its peer
# (NEXUS_PEER_HOST in compose.yaml). Whatever the node wrote after its last archived WAL is
# discarded: that is the point, it was never seen by the new primary.
set -euo pipefail

NODE="${1:?usage: rejoin.sh <node>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="${COMPOSE:-docker compose}"
ARGS="${COMPOSE_ARGS:--f $HERE/compose.yaml}"
dc() { $COMPOSE $ARGS "$@"; }
say() { printf '{"event":"%s","at":"%s","detail":"%s"}\n' "$1" "$(date -u +%FT%T.%3NZ)" "${2:-}"; }

say rejoin.start "$NODE"
dc stop -t 10 "$NODE" "${NODE}-backup" >/dev/null 2>&1 || true
dc run --rm --no-deps -T -u postgres --entrypoint sh "$NODE" -c '
    set -e
    printf "*:*:*:replicator:%s\n" "$NEXUS_REPLICATION_PASSWORD" > /var/lib/postgresql/.pgpass
    chmod 600 /var/lib/postgresql/.pgpass
    pgbackrest --stanza="${PGBACKREST_STANZA:-nexus}" --type=standby --delta \
        --recovery-option="primary_conninfo=host=$NEXUS_PEER_HOST port=5432 user=replicator passfile=/var/lib/postgresql/.pgpass application_name=$HOSTNAME" \
        --recovery-option=recovery_target_timeline=latest restore'
say rejoin.restored "$NODE"
dc up -d "$NODE" "${NODE}-backup" >/dev/null
say rejoin.done "$NODE starts as a standby; check: SELECT * FROM pg_stat_replication on the primary"

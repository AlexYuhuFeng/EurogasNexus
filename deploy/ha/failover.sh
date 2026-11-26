#!/usr/bin/env bash
# One-command failover of the database tier (deploy/ha/compose.yaml).
#
#   deploy/ha/failover.sh <failed-node> <standby-node>      e.g.  pg-node1 pg-node2
#
# In this order, because the order is what prevents two primaries ("split brain"):
#   1. stop the failed primary and its backup scheduler (if it still runs at all);
#   2. fence it: put standby.signal in its data directory, so that if anything starts it again
#      (a reboot, `restart: unless-stopped`, a well-meant `docker compose up`) it comes up
#      read-only, and the application, which only uses a node that is not in recovery, ignores it;
#   3. promote the standby (pg_promote) and wait until it accepts writes;
#   4. start a full backup on the new primary in the background (a new timeline starts here).
#
# The application needs no change when it lists both nodes (RUNTIME_STORE_DATABASE_URL on one,
# EUROGAS_NEXUS_DB_FAILOVER_HOSTS the other): its next connection finds the new primary.
# Afterwards rebuild the failed node as the new standby with deploy/ha/rejoin.sh.
#
# Environment: COMPOSE (default "docker compose"), COMPOSE_FILE / COMPOSE_PROJECT_NAME /
# --env-file as for any compose command (pass extra compose flags in COMPOSE_ARGS).
set -euo pipefail

FAILED="${1:?usage: failover.sh <failed-node> <standby-node>}"
STANDBY="${2:?usage: failover.sh <failed-node> <standby-node>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="${COMPOSE:-docker compose}"
ARGS="${COMPOSE_ARGS:--f $HERE/compose.yaml}"
dc() { $COMPOSE $ARGS "$@"; }
say() { printf '{"event":"%s","at":"%s","detail":"%s"}\n' "$1" "$(date -u +%FT%T.%3NZ)" "${2:-}"; }

say failover.start "$FAILED -> $STANDBY"
dc stop -t 10 "$FAILED" "${FAILED}-backup" >/dev/null 2>&1 || true
say failover.stopped "$FAILED"

dc run --rm --no-deps -T --entrypoint sh "$FAILED" -c \
    'touch /var/lib/postgresql/data/standby.signal && chown postgres:postgres /var/lib/postgresql/data/standby.signal' \
    >/dev/null
say failover.fenced "$FAILED"

dc exec -T -u postgres "$STANDBY" promote.sh
say failover.promoted "$STANDBY"

dc exec -T -d -u postgres "${STANDBY}-backup" pgbackrest --type=full backup || \
    say failover.backup_not_started "run: $COMPOSE $ARGS exec -u postgres ${STANDBY}-backup pgbackrest --type=full backup"
say failover.done "$STANDBY is the primary; rebuild $FAILED with rejoin.sh"

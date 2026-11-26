#!/bin/bash
# Runs once, when the first node initialises an empty data directory (the official image's
# docker-entrypoint-initdb.d hook). Creates the replication login the standby uses and allows
# it in pg_hba.conf. The password comes from the environment, never from this file.
set -euo pipefail
: "${NEXUS_REPLICATION_PASSWORD:?NEXUS_REPLICATION_PASSWORD must be set}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    --set=pw="$NEXUS_REPLICATION_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD %L', :'pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'replicator') \gexec
SQL
echo "host replication replicator all scram-sha-256" >> "$PGDATA/pg_hba.conf"

#!/bin/bash
# Promote this node (a hot standby) to primary. Run inside the standby's container:
#   docker compose exec -u postgres pg-node2 promote.sh
# The caller fences the old primary first (deploy/ha/failover.sh does both, in order).
set -euo pipefail
if [ "$(psql -h /var/run/postgresql -U "${POSTGRES_USER:-postgres}" -d postgres -tAc 'SELECT pg_is_in_recovery()')" != "t" ]; then
    echo "promote: this node is already a primary" >&2
    exit 0
fi
psql -h /var/run/postgresql -U "${POSTGRES_USER:-postgres}" -d postgres -v ON_ERROR_STOP=1 \
    -tAc 'SELECT pg_promote(wait => true, wait_seconds => 60)'
echo "promote: done; timeline $(psql -h /var/run/postgresql -U "${POSTGRES_USER:-postgres}" -d postgres -tAc 'SELECT timeline_id FROM pg_control_checkpoint()')"

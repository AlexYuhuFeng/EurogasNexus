# PostgreSQL 16 with pgBackRest (MIT), for the primary-and-standby pair of the pilot set
# (decision record 2026-11-26). One image serves both nodes and their backup schedulers; the
# role of a node is decided by its data directory (standby.signal), not by the image.
#
# Build:  docker build -t eurogas-nexus-postgres-ha:16 deploy/ha/postgres
FROM postgres:16

# pgBackRest from the PostgreSQL project's own apt repository (already configured in the
# official image). The version is recorded in the build log and `pgbackrest version`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends pgbackrest ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -o postgres -g postgres -m 0750 /var/log/pgbackrest /var/spool/pgbackrest \
    && pgbackrest version

COPY node-entrypoint.sh backup-scheduler.sh promote.sh /usr/local/bin/
COPY initdb/ /docker-entrypoint-initdb.d/
RUN chmod 0755 /usr/local/bin/node-entrypoint.sh /usr/local/bin/backup-scheduler.sh \
        /usr/local/bin/promote.sh

ENTRYPOINT ["/usr/local/bin/node-entrypoint.sh"]
CMD ["postgres"]

"""The supported database topology stays what the decision record says (2026-11-26).

A CI check on the deployment templates: a primary and a hot standby, continuous WAL archiving
and scheduled backups by pgBackRest to S3-compatible object storage with encryption, a failover
that fences before it promotes, and no AGPL object store anywhere in the delivery path.
The drills themselves (scripts/ops/ha_drill.py) need Docker and run outside CI.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HA = ROOT / "deploy" / "ha"


def _compose() -> dict:
    return yaml.safe_load((HA / "compose.yaml").read_text(encoding="utf-8"))


def test_primary_and_standby_each_with_a_backup_scheduler() -> None:
    services = _compose()["services"]
    for node, role, peer in (("pg-node1", "primary", "pg-node2"),
                             ("pg-node2", "standby", "pg-node1")):
        environment = services[node]["environment"]
        assert environment["NEXUS_NODE_ROLE"] == role
        assert environment["NEXUS_PEER_HOST"] == peer
        assert environment["PGBACKREST_REPO1_TYPE"] == "s3"
        assert environment["PGBACKREST_REPO1_CIPHER_TYPE"] == "aes-256-cbc"
        backup = services[f"{node}-backup"]
        assert backup["entrypoint"] == ["/usr/local/bin/backup-scheduler.sh"]
        # The scheduler sees its node's data directory and socket (it backs up only when
        # its node is the primary, so the schedule follows a failover).
        assert set(backup["volumes"][:2]) == set(services[node]["volumes"][:2])
        assert "PGBACKREST_REPO1_RETENTION_FULL" in backup["environment"]


def test_every_node_archives_wal_with_pgbackrest_and_can_restore_from_it() -> None:
    entrypoint = (HA / "postgres" / "node-entrypoint.sh").read_text(encoding="utf-8")
    assert "archive_command=pgbackrest --stanza=${STANZA} archive-push %p" in entrypoint
    assert "restore_command=pgbackrest --stanza=${STANZA} archive-get" in entrypoint
    assert "archive_timeout=" in entrypoint
    assert "--type=standby" in entrypoint
    dockerfile = (HA / "postgres" / "Dockerfile").read_text(encoding="utf-8")
    assert "pgbackrest" in dockerfile and "FROM postgres:16" in dockerfile


def test_failover_fences_the_old_primary_before_it_promotes() -> None:
    script = (HA / "failover.sh").read_text(encoding="utf-8")
    stop = script.index('dc stop -t 10 "$FAILED"')
    fence = script.index("touch /var/lib/postgresql/data/standby.signal")
    promote = script.index('"$STANDBY" promote.sh')
    assert stop < fence < promote


def test_the_test_object_store_is_test_only_and_not_agpl() -> None:
    services = _compose()["services"]
    assert services["objectstore"]["profiles"] == ["test-objectstore"]
    for name, service in services.items():
        image = str(service.get("image", "")).lower()
        assert "minio" not in image, name
        if name != "objectstore":
            assert "profiles" not in service, f"{name} must run in every deployment"
    for path in (ROOT / "deploy").rglob("*"):
        if path.is_file() and path.suffix in {".yaml", ".yml", ".sh", ".example"}:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            assert "minio/minio" not in text and "quay.io/minio" not in text, path


def test_the_env_template_carries_no_secret() -> None:
    secret_names = {
        "POSTGRES_PASSWORD",
        "NEXUS_REPLICATION_PASSWORD",
        "BACKUP_S3_ACCESS_KEY_ID",
        "BACKUP_S3_SECRET_ACCESS_KEY",
        "BACKUP_CIPHER_PASSPHRASE",
    }
    for line in (HA / "env.ha.example").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() in secret_names:
            assert value.strip() == "", name


def test_the_runtime_stack_can_follow_a_failover() -> None:
    runtime = yaml.safe_load((ROOT / "deploy/runtime/compose.yaml").read_text(encoding="utf-8"))
    # Every service that connects follows a failover (the anchors merge into each other).
    for anchor in ("x-db-environment", "x-runtime-environment", "x-migrate-environment"):
        assert "EUROGAS_NEXUS_DB_FAILOVER_HOSTS" in runtime[anchor], anchor
    assert "EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS" in runtime["x-runtime-environment"]
    # The object-store key goes only to the services that archive or read offloaded pages
    # (security review H3/M8: each service receives only the secrets it needs); not the API.
    services = runtime["services"]
    for name in ("public-ingestion-worker", "public-ingestion"):
        assert "EUROGAS_NEXUS_OBJECT_STORE_SECRET_ACCESS_KEY" in services[name]["environment"]
    for name in ("api", "config-check", "migrate", "market-events-worker"):
        assert "EUROGAS_NEXUS_OBJECT_STORE_SECRET_ACCESS_KEY" not in services[name]["environment"]


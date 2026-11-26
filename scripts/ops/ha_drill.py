"""Recovery drills for the primary-and-standby database tier (deploy/ha), rerunnable.

Two drills, each measured and written to a JSON report:

``pitr``      point-in-time recovery. Fill the store to a realistic size, take a full base
              backup, write more, record a time T, write more, then restore to T on a fresh
              instance and verify row counts, an order-independent checksum, the schema and the
              API's readiness (``backup_restore_drill.verify_restored_database``, shared with the
              logical-dump drill).
``failover``  stop the primary, fence it, promote the standby (``deploy/ha/failover.sh``), and
              show the application reaching the new primary with no configuration change and no
              loss of committed, replicated writes; then that the fenced old primary, started
              again, is ignored; then rebuild it as the new standby (``deploy/ha/rejoin.sh``).

On a drill machine (no firm object store) the stack's test double runs (SeaweedFS, Apache-2.0,
in memory); against the firm's store, pass ``--env-file`` with its settings instead of
``prepare``. Every container, volume and network is named after ``--project`` and removed by
``down``.

    python scripts/ops/ha_drill.py prepare --workdir /tmp/nexus-drill
    python scripts/ops/ha_drill.py up --workdir /tmp/nexus-drill
    python scripts/ops/ha_drill.py pitr --workdir /tmp/nexus-drill --target-gb 5 --free-source
    python scripts/ops/ha_drill.py down --workdir /tmp/nexus-drill
    python scripts/ops/ha_drill.py prepare/up ... then failover --workdir /tmp/nexus-drill

The plan's exit criterion is a restore to a chosen minute on a store of at least 50 GB: run
``pitr --target-gb 50`` on the pilot database servers; a development machine proves the
procedure and gives a lower-bound rate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT / "src", ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

COMPOSE_FILE = ROOT / "deploy" / "ha" / "compose.yaml"
HA_DIR = ROOT / "deploy" / "ha"
GIB = 1024**3
# The drill's engines are command engines (db/session.py): the 5 s connect bound, no statement
# limit and no socket read limit (keepalives find a dead peer), so bulk loads and checksums over
# gigabytes run as long as they need. Before the socket-timeout fix they passed a one-hour
# "connect" timeout to get past pg8000 cutting every statement off at 5 s.


def log(event: str, **fields) -> None:
    print(json.dumps({"event": event, "at": _now().isoformat(), **fields}, default=str),
          flush=True)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# --- configuration -------------------------------------------------------------------------


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            values[name.strip()] = value.strip()
    return values


def _write_certificates(directory: Path) -> None:
    """A private CA and a server certificate for the test object store (never a real one)."""

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    directory.mkdir(parents=True, exist_ok=True)
    now = _now()
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "nexus drill test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "objectstore")]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=7))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("objectstore"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=True, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
        )
        .sign(ca_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    (directory / "ca.crt").write_bytes(ca.public_bytes(pem))
    (directory / "tls.crt").write_bytes(cert.public_bytes(pem))
    (directory / "tls.key").write_bytes(
        key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    # SeaweedFS runs as its own user inside the container and must read the key.
    os.chmod(directory / "tls.key", 0o644)


def prepare(workdir: Path, *, image: str) -> Path:
    """Throwaway secrets, certificates and an env file for a drill stack."""

    workdir.mkdir(parents=True, exist_ok=True)
    store = workdir / "objectstore"
    _write_certificates(store / "certs")
    access, secret = "drill" + secrets.token_hex(6), secrets.token_urlsafe(24)
    (store / "s3.json").write_text(
        json.dumps(
            {
                "identities": [
                    {
                        "name": "nexus-drill",
                        "credentials": [{"accessKey": access, "secretKey": secret}],
                        "actions": ["Admin", "Read", "Write", "List", "Tagging"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    os.chmod(store / "s3.json", 0o644)
    values = {
        "POSTGRES_DB": "drill_nexus",
        "POSTGRES_USER": "nexus_owner",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(18),
        "NEXUS_REPLICATION_PASSWORD": secrets.token_urlsafe(18),
        "PG_NODE1_PORT": str(_free_port()),
        "PG_NODE2_PORT": str(_free_port()),
        "BACKUP_S3_ENDPOINT": "objectstore",
        "BACKUP_S3_PORT": "8333",
        "BACKUP_S3_REGION": "us-east-1",
        "BACKUP_S3_URI_STYLE": "path",
        "BACKUP_S3_BUCKET": "nexus-backups",
        "BACKUP_S3_ACCESS_KEY_ID": access,
        "BACKUP_S3_SECRET_ACCESS_KEY": secret,
        "BACKUP_S3_CA_FILE": str(store / "certs" / "ca.crt"),
        "BACKUP_CIPHER_PASSPHRASE": secrets.token_urlsafe(24),
        "NEXUS_ARCHIVE_TIMEOUT_SECONDS": "30",
        "NEXUS_POSTGRES_IMAGE": image,
        "NEXUS_TEST_OBJECTSTORE_CONFIG": str(store),
        "NEXUS_TEST_OBJECTSTORE_PORT": str(_free_port()),
        "NEXUS_TEST_OBJECTSTORE_TMPFS": "4g",
    }
    env_file = workdir / "drill.env"
    env_file.write_text(
        "# Throwaway drill settings written by scripts/ops/ha_drill.py; delete with `down`.\n"
        + "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    os.chmod(env_file, 0o600)
    log("drill.prepared", workdir=str(workdir))
    return env_file


class Stack:
    """The compose stack of one drill (project name, env file)."""

    def __init__(self, project: str, env_file: Path, *, test_objectstore: bool = True):
        self.project = project
        self.env_file = env_file
        self.env = read_env(env_file)
        self.test_objectstore = test_objectstore

    @property
    def compose_args(self) -> list[str]:
        args = ["-f", str(COMPOSE_FILE), "-p", self.project, "--env-file", str(self.env_file)]
        if self.test_objectstore:
            args += ["--profile", "test-objectstore"]
        return args

    def compose(self, *args: str, check: bool = True, capture: bool = False,
                timeout: float = 3600) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "compose", *self.compose_args, *args],
            check=check,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )

    def script(self, name: str, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, COMPOSE_ARGS=" ".join(self.compose_args))
        return subprocess.run(
            ["bash", str(HA_DIR / name), *args], env=env, check=True, capture_output=True,
            text=True, timeout=1800,
        )

    def psql(self, service: str, sql: str, *, check: bool = True) -> str:
        result = self.compose(
            "exec", "-T", "-u", "postgres", service, "psql", "-h", "/var/run/postgresql",
            "-U", self.env["POSTGRES_USER"], "-d", self.env["POSTGRES_DB"], "-tAc", sql,
            check=check, capture=True, timeout=600,
        )
        return result.stdout.strip()

    def url(self, node: int, *, database: str | None = None, host: str = "127.0.0.1") -> str:
        port = self.env[f"PG_NODE{node}_PORT"]
        return (
            f"postgresql+pg8000://{self.env['POSTGRES_USER']}:{self.env['POSTGRES_PASSWORD']}"
            f"@{host}:{port}/{database or self.env['POSTGRES_DB']}"
        )

    @property
    def network(self) -> str:
        return f"{self.project}_default"

    def pgbackrest_env(self) -> dict[str, str]:
        env = self.env
        return {
            "PGBACKREST_STANZA": "nexus",
            "PGBACKREST_PG1_PATH": "/var/lib/postgresql/data",
            "PGBACKREST_REPO1_TYPE": "s3",
            "PGBACKREST_REPO1_PATH": "/pgbackrest",
            "PGBACKREST_REPO1_S3_BUCKET": env["BACKUP_S3_BUCKET"],
            "PGBACKREST_REPO1_S3_ENDPOINT": env["BACKUP_S3_ENDPOINT"],
            "PGBACKREST_REPO1_STORAGE_PORT": env["BACKUP_S3_PORT"],
            "PGBACKREST_REPO1_S3_REGION": env["BACKUP_S3_REGION"],
            "PGBACKREST_REPO1_S3_URI_STYLE": env["BACKUP_S3_URI_STYLE"],
            "PGBACKREST_REPO1_S3_KEY": env["BACKUP_S3_ACCESS_KEY_ID"],
            "PGBACKREST_REPO1_S3_KEY_SECRET": env["BACKUP_S3_SECRET_ACCESS_KEY"],
            "PGBACKREST_REPO1_STORAGE_CA_FILE": "/etc/nexus/objectstore-ca.crt",
            "PGBACKREST_REPO1_CIPHER_TYPE": "aes-256-cbc",
            "PGBACKREST_REPO1_CIPHER_PASS": env["BACKUP_CIPHER_PASSPHRASE"],
            "PGBACKREST_PROCESS_MAX": "2",
            "PGBACKREST_LOG_LEVEL_CONSOLE": "info",
            "PGBACKREST_LOG_LEVEL_FILE": "off",
            "PGBACKREST_DELTA": "y",
        }


def wait_until(check, *, timeout: float, interval: float = 2.0, what: str) -> float:
    started = time.monotonic()
    while True:
        try:
            if check():
                return round(time.monotonic() - started, 2)
        except Exception:  # noqa: BLE001 - not there yet
            pass
        if time.monotonic() - started > timeout:
            raise TimeoutError(f"timed out after {timeout:.0f}s waiting for {what}")
        time.sleep(interval)


def backups(stack: Stack, service: str = "pg-node1-backup") -> list[dict]:
    result = stack.compose("exec", "-T", "-u", "postgres", service, "pgbackrest", "info",
                           "--output=json", capture=True, check=False, timeout=300)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    info = json.loads(result.stdout)
    return info[0].get("backup", []) if info else []


def tmpfs_volume(name: str, *, project: str, size_gb: float, compose_volume: str | None) -> None:
    """A Docker volume held in memory (a drill machine whose shared disk is too small).

    Labelled as the compose project's own volume so ``docker compose`` adopts and removes it.
    Memory is faster than the pilot's NVMe disks, so times measured this way are lower bounds.
    """

    subprocess.run(["docker", "volume", "rm", name], capture_output=True)
    labels = []
    if compose_volume:
        labels = ["--label", f"com.docker.compose.project={project}",
                  "--label", f"com.docker.compose.volume={compose_volume}"]
    subprocess.run(
        ["docker", "volume", "create", "--driver", "local", "--opt", "type=tmpfs",
         "--opt", "device=tmpfs", "--opt", f"o=size={int(size_gb * 1024)}m", *labels, name],
        check=True, capture_output=True,
    )


def up(stack: Stack, *, standby: bool = True, tmpfs_gb: float = 0.0) -> dict:
    """Object store (test double), node 1 and its first backup, then the standby."""

    timings = {}
    started = time.monotonic()
    if tmpfs_gb:
        for node in ("pg-node1", "pg-node2"):
            tmpfs_volume(f"{stack.project}_{node}-data", project=stack.project,
                         size_gb=tmpfs_gb, compose_volume=f"{node}-data")
    if stack.test_objectstore:
        stack.compose("up", "-d", "objectstore")
        from eurogas_nexus.runtime_store.object_store import S3ObjectStore

        store = S3ObjectStore(
            bucket=stack.env["BACKUP_S3_BUCKET"],
            endpoint=f"https://127.0.0.1:{stack.env['NEXUS_TEST_OBJECTSTORE_PORT']}",
            region=stack.env["BACKUP_S3_REGION"],
            access_key=stack.env["BACKUP_S3_ACCESS_KEY_ID"],
            secret_key=stack.env["BACKUP_S3_SECRET_ACCESS_KEY"],
            ca_file=stack.env["BACKUP_S3_CA_FILE"],
        )
        wait_until(lambda: store.ensure_bucket() in {True, False}, timeout=120,
                   what="the test object store")
        # The bucket for the product's own archive (retention) beside the backup bucket.
        S3ObjectStore(
            bucket="nexus-archive", endpoint=store.scheme + "://" + store.endpoint_host,
            region=store.region, access_key=stack.env["BACKUP_S3_ACCESS_KEY_ID"],
            secret_key=stack.env["BACKUP_S3_SECRET_ACCESS_KEY"],
            ca_file=stack.env["BACKUP_S3_CA_FILE"],
        ).ensure_bucket()
    stack.compose("up", "-d", "--wait", "pg-node1")
    stack.compose("up", "-d", "pg-node1-backup")
    timings["first_backup_seconds"] = wait_until(
        lambda: backups(stack), timeout=1800, interval=5, what="the first full backup"
    )
    if not standby:
        timings["total_seconds"] = round(time.monotonic() - started, 1)
        log("drill.up", standby=False, **timings)
        return timings
    stack.compose("up", "-d", "pg-node2", "pg-node2-backup")
    timings["standby_streaming_seconds"] = wait_until(
        lambda: stack.psql("pg-node1", "SELECT count(*) FROM pg_stat_replication "
                           "WHERE state = 'streaming'") == "1",
        timeout=1800, interval=3, what="the standby to stream",
    )
    timings["total_seconds"] = round(time.monotonic() - started, 1)
    log("drill.up", **timings)
    return timings


def migrate(url: str) -> float:
    started = time.monotonic()
    env = {k: v for k, v in os.environ.items()
           if k not in {"RUNTIME_STORE_DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"}}
    env["DATABASE_URL"] = url
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env,
                   check=True, capture_output=True, text=True, timeout=1800)
    return round(time.monotonic() - started, 1)


@contextmanager
def app_database(url: str, failover_hosts: str | None = None):
    """Point this process's application at ``url`` (and failover hosts) for a block."""

    from eurogas_nexus.db.session import DB_URL_ENV_VARS, dispose_cached_engines

    names = (*DB_URL_ENV_VARS, "EUROGAS_NEXUS_DB_FAILOVER_HOSTS")
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ.pop(name, None)
    os.environ["DATABASE_URL"] = url
    if failover_hosts:
        os.environ["EUROGAS_NEXUS_DB_FAILOVER_HOSTS"] = failover_hosts
    try:
        yield
    finally:
        dispose_cached_engines()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# --- point-in-time recovery drill ---------------------------------------------------------------


def pitr(stack: Stack, args) -> dict:
    from eurogas_nexus.db.session import get_engine
    from scripts.ops import generate_drill_store as gen
    from scripts.ops.backup_restore_drill import verify_restored_database

    report: dict = {"drill": "pitr", "project": stack.project, "started_at": _now().isoformat()}
    source_url = stack.url(1)
    report["migrate_seconds"] = migrate(source_url)
    engine = get_engine(source_url, statement_timeout=None)
    try:
        gen.require_drill_database(engine)
        load = gen.generate(
            engine,
            target_bytes=int(args.target_gb * GIB),
            rows_per_batch=args.rows_per_batch,
            min_free_bytes=int(args.min_free_gb * GIB),
            free_space_path=args.free_space_path,
        )
        report["load"] = load
        log("drill.loaded", **load)

        started = time.monotonic()
        stack.compose("exec", "-T", "-u", "postgres", "pg-node1-backup", "pgbackrest",
                      "--type=full", "backup", capture=True)
        report["base_backup_seconds"] = round(time.monotonic() - started, 1)
        latest = backups(stack)[-1]
        report["base_backup"] = {
            "label": latest["label"],
            "database_bytes": latest["info"]["size"],
            "repository_bytes": latest["info"]["repository"]["delta"],
        }
        log("drill.base_backup", seconds=report["base_backup_seconds"], **report["base_backup"])

        gen.write_marked_batch(engine, label="before", rows=args.marker_rows,
                               batch=load["next_batch"])
        expected = gen.fingerprint(engine)
        with engine.connect() as connection:
            from sqlalchemy import text

            target = connection.execute(text("SELECT clock_timestamp()")).scalar()
        report["target_time"] = target.isoformat()
        report["expected"] = expected
        time.sleep(2)
        gen.write_marked_batch(engine, label="after", rows=args.marker_rows,
                               batch=load["next_batch"] + 1)
        after = gen.fingerprint(engine)
        report["source_after_target"] = after
        with engine.connect() as connection:
            report["source_database_bytes"] = gen.database_bytes(connection)
    finally:
        engine.dispose()
    # Every WAL segment up to and past T is in the repository before the source goes away.
    started = time.monotonic()
    stack.compose("exec", "-T", "-u", "postgres", "pg-node1-backup", "pgbackrest", "check",
                  capture=True)
    report["wal_archive_check_seconds"] = round(time.monotonic() - started, 1)

    if args.free_source:
        stack.compose("stop", "-t", "20", "pg-node2-backup", "pg-node2", "pg-node1-backup",
                      "pg-node1")
        stack.compose("rm", "-f", "pg-node2-backup", "pg-node2", "pg-node1-backup", "pg-node1")
        for volume in ("pg-node1-data", "pg-node2-data"):
            subprocess.run(["docker", "volume", "rm", f"{stack.project}_{volume}"], check=False,
                           capture_output=True)
        report["source_removed_before_restore"] = True
        log("drill.source_removed")

    restored = restore_to_time(stack, report["target_time"], tmpfs_gb=args.tmpfs_gb)
    report["restore"] = restored
    target_url = (
        f"postgresql+pg8000://{stack.env['POSTGRES_USER']}:{stack.env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{restored['port']}/{stack.env['POSTGRES_DB']}"
    )
    target_engine = get_engine(target_url, statement_timeout=None)
    try:
        actual = gen.fingerprint(target_engine)
    finally:
        target_engine.dispose()
    report["restored"] = actual
    report["counts_and_checksums_match"] = actual == expected
    report["rows_after_target_absent"] = all(
        actual[table]["rows"] == expected[table]["rows"] < after[table]["rows"]
        for table in expected
    )
    report["verification"] = verify_restored_database(target_url)
    report["ok"] = bool(
        report["counts_and_checksums_match"]
        and report["rows_after_target_absent"]
        and report["verification"].get("ok")
    )
    report["finished_at"] = _now().isoformat()
    return report


def restore_to_time(stack: Stack, target_time: str, *, tmpfs_gb: float = 0.0) -> dict:
    """pgBackRest restore to ``target_time`` into a new volume, then start and wait for the
    promotion. The restored instance never archives (NEXUS_ARCHIVE_MODE=off)."""

    # pgBackRest's form: milliseconds and an explicit UTC offset. Truncating to the
    # millisecond moves the target at most 1 ms earlier, after every commit before T.
    moment = dt.datetime.fromisoformat(target_time).astimezone(dt.UTC)
    target = moment.strftime("%Y-%m-%d %H:%M:%S.") + f"{moment.microsecond // 1000:03d}+00"
    volume = f"{stack.project}_restored-data"
    name = f"{stack.project}-restored"
    image = stack.env["NEXUS_POSTGRES_IMAGE"]
    ca = stack.env["BACKUP_S3_CA_FILE"]
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
    if tmpfs_gb:
        tmpfs_volume(volume, project=stack.project, size_gb=tmpfs_gb, compose_volume=None)
    else:
        subprocess.run(["docker", "volume", "create", volume], check=True, capture_output=True)
    common = ["--network", stack.network, "-v", f"{volume}:/var/lib/postgresql/data",
              "-v", f"{ca}:/etc/nexus/objectstore-ca.crt:ro"]
    env_args = [arg for name, value in stack.pgbackrest_env().items()
                for arg in ("-e", f"{name}={value}")]
    subprocess.run(["docker", "run", "--rm", *common, "--entrypoint", "sh", image, "-c",
                    "chown postgres:postgres /var/lib/postgresql/data && "
                    "chmod 700 /var/lib/postgresql/data"], check=True, capture_output=True)
    started = time.monotonic()
    subprocess.run(
        ["docker", "run", "--rm", *common, *env_args, "-u", "postgres", "--entrypoint",
         "pgbackrest", image, "--type=time", f"--target={target}",
         "--target-action=promote", "restore"],
        check=True, capture_output=True, text=True, timeout=7200,
    )
    restore_seconds = round(time.monotonic() - started, 1)
    log("drill.restore.files", seconds=restore_seconds)
    port = _free_port()
    started = time.monotonic()
    subprocess.run(
        ["docker", "run", "-d", "--name", name, *common, *env_args,
         "-e", f"POSTGRES_USER={stack.env['POSTGRES_USER']}",
         "-e", f"POSTGRES_PASSWORD={stack.env['POSTGRES_PASSWORD']}",
         "-e", "NEXUS_ARCHIVE_MODE=off", "-p", f"127.0.0.1:{port}:5432", image],
        check=True, capture_output=True,
    )

    def promoted() -> bool:
        out = subprocess.run(
            ["docker", "exec", "-u", "postgres", name, "psql", "-h", "/var/run/postgresql",
             "-U", stack.env["POSTGRES_USER"], "-d", "postgres", "-tAc",
             "SELECT NOT pg_is_in_recovery()"],
            capture_output=True, text=True,
        )
        return out.stdout.strip() == "t"

    recovery_seconds = wait_until(promoted, timeout=7200, interval=1, what="recovery to T")
    total = round(time.monotonic() - started + restore_seconds, 1)
    log("drill.restore.promoted", recovery_seconds=recovery_seconds, total_seconds=total)
    return {
        "container": name,
        "port": port,
        "restore_files_seconds": restore_seconds,
        "wal_replay_and_promote_seconds": recovery_seconds,
        "total_restore_seconds": total,
    }


# --- failover drill ----------------------------------------------------------------------------


def failover(stack: Stack, args) -> dict:
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from eurogas_nexus.api.app import create_app
    from eurogas_nexus.db.session import get_engine, get_session_factory

    report: dict = {"drill": "failover", "project": stack.project,
                    "started_at": _now().isoformat()}
    node1 = stack.url(1)
    report["migrate_seconds"] = migrate(node1)
    if args.target_gb:
        from scripts.ops import generate_drill_store as gen

        engine = get_engine(node1, statement_timeout=None)
        try:
            gen.require_drill_database(engine)
            report["load"] = gen.generate(
                engine, target_bytes=int(args.target_gb * GIB),
                min_free_bytes=int(args.min_free_gb * GIB),
                free_space_path=args.free_space_path,
            )
        finally:
            engine.dispose()
    failover_hosts = f"127.0.0.1:{stack.env['PG_NODE2_PORT']}"

    def write(session_factory, event_id: str) -> None:
        with session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO audit_events (event_id, event_type, severity, principal,"
                    " action, resource, outcome, detail, event_ts_utc, source_system,"
                    " human_review_required) VALUES (:id, 'drill', 'info', 'drill',"
                    " 'drill.failover', 'drill', 'recorded', '', clock_timestamp(), 'drill',"
                    " false)"
                ),
                {"id": event_id},
            )
            session.commit()

    with app_database(node1, failover_hosts):
        client = TestClient(create_app())
        factory = get_session_factory()
        assert client.get("/api/health/ready").status_code == 200, "app not ready before drill"
        marker = f"drill-failover-{secrets.token_hex(4)}"
        write(factory, marker)
        # Committed on the primary and replayed on the standby: what failover must not lose.
        lsn = stack.psql("pg-node1", "SELECT pg_current_wal_lsn()")
        report["standby_caught_up_seconds"] = wait_until(
            lambda: stack.psql(
                "pg-node2", f"SELECT pg_last_wal_replay_lsn() >= '{lsn}'::pg_lsn"
            ) == "t",
            timeout=300, interval=0.5, what="the standby to replay the marker",
        )

        crash = time.monotonic()
        stack.compose("kill", "-s", "SIGKILL", "pg-node1")
        report["primary_killed_at"] = _now().isoformat()
        outage = client.get("/api/health/ready")
        report["readiness_during_outage"] = {
            "status": outage.status_code,
            "code": (outage.json().get("detail") or {}).get("code"),
        }
        started = time.monotonic()
        result = stack.script("failover.sh", "pg-node1", "pg-node2")
        report["failover_script_seconds"] = round(time.monotonic() - started, 1)
        events = [json.loads(line) for line in result.stdout.splitlines()
                  if line.startswith("{")]
        first = dt.datetime.fromisoformat(events[0]["at"].replace("Z", "+00:00"))
        report["failover_script_events"] = [
            {
                "event": item["event"],
                "seconds_from_start": round(
                    (dt.datetime.fromisoformat(item["at"].replace("Z", "+00:00")) - first)
                    .total_seconds(),
                    2,
                ),
            }
            for item in events
        ]
        report["app_ready_after_seconds_from_crash"] = None
        wait_until(lambda: client.get("/api/health/ready").status_code == 200, timeout=120,
                   interval=0.5, what="the application to reach the new primary")
        report["app_ready_after_seconds_from_crash"] = round(time.monotonic() - crash, 1)
        write(factory, marker + "-after")
        with factory() as session:
            present = session.execute(
                text("SELECT count(*) FROM audit_events WHERE event_id IN (:a, :b)"),
                {"a": marker, "b": marker + "-after"},
            ).scalar()
            on_primary = session.execute(text("SELECT NOT pg_is_in_recovery()")).scalar()
        report["committed_before_and_after_present"] = present == 2
        report["app_on_writable_primary"] = bool(on_primary)

        # Fencing: the old primary started again comes up read-only and is skipped.
        stack.compose("up", "-d", "--no-deps", "pg-node1")
        wait_until(lambda: stack.psql("pg-node1", "SELECT 1") == "1", timeout=300,
                   what="the fenced node to start")
        report["old_primary_in_recovery_after_restart"] = (
            stack.psql("pg-node1", "SELECT pg_is_in_recovery()") == "t"
        )
        from eurogas_nexus.db.session import dispose_cached_engines

        dispose_cached_engines()
        factory = get_session_factory()
        write(factory, marker + "-fenced")
        with factory() as session:
            report["app_still_writes_to_new_primary"] = bool(
                session.execute(text("SELECT NOT pg_is_in_recovery()")).scalar()
            )
        report["readiness_after_fenced_restart"] = client.get("/api/health/ready").status_code

    if args.rejoin:
        started = time.monotonic()
        stack.script("rejoin.sh", "pg-node1")
        wait_until(
            lambda: stack.psql("pg-node2", "SELECT count(*) FROM pg_stat_replication "
                               "WHERE state = 'streaming'") == "1",
            timeout=1800, interval=3, what="the old primary to stream as the new standby",
        )
        report["rejoin_seconds"] = round(time.monotonic() - started, 1)
    report["ok"] = bool(
        report["readiness_during_outage"]["status"] == 503
        and report["committed_before_and_after_present"]
        and report["app_on_writable_primary"]
        and report["old_primary_in_recovery_after_restart"]
        and report["app_still_writes_to_new_primary"]
        and report["readiness_after_fenced_restart"] == 200
    )
    report["finished_at"] = _now().isoformat()
    return report


def down(stack: Stack, workdir: Path, *, keep_workdir: bool = False) -> None:
    subprocess.run(["docker", "rm", "-f", f"{stack.project}-restored"], capture_output=True)
    subprocess.run(["docker", "volume", "rm", f"{stack.project}_restored-data"],
                   capture_output=True)
    stack.compose("down", "-v", "--remove-orphans", check=False)
    if not keep_workdir:
        shutil.rmtree(workdir / "objectstore", ignore_errors=True)
        (workdir / "drill.env").unlink(missing_ok=True)
    log("drill.down", project=stack.project)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", choices=["prepare", "up", "pitr", "failover", "down"])
    parser.add_argument("--workdir", type=Path, required=True,
                        help="Scratch directory for the drill's secrets, certificates, reports.")
    parser.add_argument("--project", default="nexus-drill")
    parser.add_argument("--env-file", type=Path,
                        help="Use this env file (the firm's object store) instead of prepare's.")
    parser.add_argument("--image", default="eurogas-nexus-postgres-ha:16")
    parser.add_argument("--target-gb", type=float, default=0.0)
    parser.add_argument("--rows-per-batch", type=int, default=250_000)
    parser.add_argument("--marker-rows", type=int, default=20_000)
    parser.add_argument("--min-free-gb", type=float, default=1.5)
    parser.add_argument("--free-space-path", default="/var/lib/docker")
    parser.add_argument("--free-source", action="store_true",
                        help="Remove the source nodes' volumes before restoring (small disks).")
    parser.add_argument("--no-standby", action="store_true",
                        help="up: start the primary only (a PITR drill needs no standby).")
    parser.add_argument("--tmpfs-gb", type=float, default=0.0,
                        help="Keep the drill's database volumes in memory, this size each "
                        "(a machine whose disk is too small; times become lower bounds).")
    parser.add_argument("--rejoin", action="store_true",
                        help="After the failover drill, rebuild the old primary as standby.")
    args = parser.parse_args(argv)

    workdir = args.workdir.resolve()
    if args.command == "prepare":
        prepare(workdir, image=args.image)
        return 0
    env_file = (args.env_file or workdir / "drill.env").resolve()
    stack = Stack(args.project, env_file, test_objectstore=args.env_file is None)
    if args.command == "down":
        down(stack, workdir)
        return 0
    if args.command == "up":
        up(stack, standby=not args.no_standby, tmpfs_gb=args.tmpfs_gb)
        return 0
    drill = pitr if args.command == "pitr" else failover
    try:
        report = drill(stack, args)
    except subprocess.CalledProcessError as exc:
        def tail(value) -> str:
            if isinstance(value, bytes):
                value = value.decode("utf-8", "replace")
            return (value or "")[-1500:]

        # pgBackRest reports its errors on standard output.
        report = {"drill": args.command, "ok": False, "error": "command_failed",
                  "command": " ".join(map(str, exc.cmd[:6])) + " ... " + str(exc.cmd[-1]),
                  "stderr": tail(exc.stderr), "stdout": tail(exc.stdout)}
    path = workdir / f"{args.command}-report-{_now():%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

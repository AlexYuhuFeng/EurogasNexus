"""Small-desk rehearsal against real containers: install, status, backup, restore, update,
undo-update (both ways back), an update that fails and undoes itself, and diagnostics.

It drives the `nexus` command exactly as the helpdesk would, from release folders built by
``scripts/release/package_small_desk_bundle.py``. Runs only when asked, because it needs a
Docker daemon and the customer image built from this tree (several minutes)::

    docker build -f deploy/runtime/Dockerfile.api -t eurogas-nexus-api:rehearsal .
    (cd clients/web && npm ci && npm run build)
    NEXUS_REHEARSAL_IMAGE=eurogas-nexus-api:rehearsal \\
        python -m pytest -q -p no:cacheprovider tests/integration/test_small_desk_rehearsal.py

Two disks are required by `nexus install`: the database goes under ``NEXUS_REHEARSAL_DATA``
(default: pytest's temporary folder) and the backups under ``NEXUS_REHEARSAL_BACKUP``
(default ``/dev/shm``, a different file system on Linux). The later versions are the same
image with one extra migration: reversible (``0097_sd_reversible``), irreversible
(``0097_sd_irreversible``), and one whose application never becomes ready (the update must
undo itself). Timings are written to ``NEXUS_REHEARSAL_REPORT`` when set.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE_IMAGE = os.environ.get("NEXUS_REHEARSAL_IMAGE", "")
WEB_DIST = Path(os.environ.get("NEXUS_REHEARSAL_WEB_DIST", ROOT / "clients/web/dist"))

pytestmark = pytest.mark.skipif(
    not BASE_IMAGE or shutil.which("docker") is None,
    reason="needs Docker and NEXUS_REHEARSAL_IMAGE (the customer image built from this tree)",
)

SITE = "/usr/local/lib/python3.11/site-packages/eurogas_nexus/release/constants.py"
MIGRATION = '''"""Small-desk rehearsal: a {kind} change (test image only)."""
import sqlalchemy as sa
from alembic import op

revision = "{revision}"
down_revision = "0096_retention_by_class"
branch_labels = None
depends_on = None
reversibility = "{kind}"
{note}


def upgrade() -> None:
    op.create_table("sd_rehearsal_marker", sa.Column("id", sa.Integer, primary_key=True))


def downgrade() -> None:
    {downgrade}
'''


def build_variant(tag: str, revision: str, kind: str, *, ready: bool = True) -> None:
    """The base image plus one migration; ``ready=False`` leaves the required revision as it
    was, so the API reports "schema not current" and never becomes ready."""

    context = Path(os.environ.get("NEXUS_REHEARSAL_TMP", "/tmp")) / f"sd-variant-{tag}"
    shutil.rmtree(context, ignore_errors=True)
    context.mkdir(parents=True)
    note = (
        'reversibility_note = "rehearsal: going back restores the backup"'
        if kind == "irreversible"
        else ""
    )
    down = (
        'raise RuntimeError("irreversible")'
        if kind == "irreversible"
        else 'op.drop_table("sd_rehearsal_marker")'
    )
    (context / "migration.py").write_text(
        MIGRATION.format(kind=kind, revision=revision, note=note, downgrade=down)
    )
    bump = (
        f"RUN sed -i 's/^DB_SCHEMA_REVISION = .*/DB_SCHEMA_REVISION = \"{revision}\"/' {SITE}\n"
        if ready
        else ""
    )
    (context / "Dockerfile").write_text(
        f"FROM {BASE_IMAGE}\nUSER root\n"
        f"COPY migration.py /app/alembic/versions/{revision}.py\n{bump}USER eurogas\n"
    )
    subprocess.run(["docker", "build", "-q", "-t", tag, str(context)], check=True)


def bundle(out: Path, version: str, image: str) -> Path:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/release/package_small_desk_bundle.py"),
            "--version", version, "--api-image", image,
            "--web-dist", str(WEB_DIST), "--out", str(out),
        ],
        check=True, capture_output=True, text=True,
    )
    return Path(result.stdout.strip().splitlines()[-1])


class Desk:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.timings: dict[str, float] = {}

    def nexus(self, *args: str, tool: Path | None = None, expect: int | None = 0) -> str:
        command = [str(tool or self.root / "tool" / "nexus"), "--root", str(self.root), *args]
        started = time.monotonic()
        done = subprocess.run(command, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        label = " ".join(args[:2]) if args[0] == "restore" else args[0]
        count = sum(1 for key in self.timings if key.split(" #")[0] == label)
        self.timings[f"{label} #{count + 1}"] = round(time.monotonic() - started, 1)
        output = done.stdout + done.stderr
        if expect is not None:
            assert done.returncode == expect, (
                f"nexus {' '.join(args)} -> {done.returncode}\n{output}"
            )
        return output

    def compose(self, *args: str, input_text: str | None = None) -> str:
        state = json.loads((self.root / "state.json").read_text())
        version = state["current"]["version"]
        release = json.loads((self.root / "releases" / version / "release.json").read_text())
        conf = dict(
            line.split("=", 1)
            for line in (self.root / "nexus.conf").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        env = dict(
            os.environ,
            EUROGAS_NEXUS_API_IMAGE=release["api_image"],
            EUROGAS_NEXUS_VERSION=version,
            NEXUS_WEB_DIR=str(self.root / "releases" / version / "web"),
            NEXUS_DATA_DIR=conf["NEXUS_DATA_DIR"],
            NEXUS_SITE_ADDRESSES="https://localhost:443",
            NEXUS_HTTPS_PORT=conf["NEXUS_HTTPS_PORT"],
        )
        done = subprocess.run(
            [
                "docker", "compose", "-p", "eurogas-nexus",
                "-f", str(self.root / "releases" / version / "compose.yaml"),
                "--env-file", str(self.root / "stack.env"), *args,
            ],
            env=env, capture_output=True, text=True, input=input_text,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    def sql(self, statement: str) -> str:
        return self.compose(
            "exec", "-T", "postgres", "psql", "-U", "nexus_superuser", "-d", "eurogas",
            "-tAc", statement,
        ).strip()

    def revision(self) -> str:
        return self.sql("SELECT version_num FROM alembic_version")

    def users(self) -> set[str]:
        return set(self.sql("SELECT name FROM identity_principals").split())

    def add_user(self, name: str) -> None:
        self.compose(
            "exec", "-T", "api", "python", "-m", "eurogas_nexus.cli.accounts", "create",
            "--username", name,
        )

    def teardown(self) -> None:
        subprocess.run(
            ["docker", "compose", "-p", "eurogas-nexus", "down", "--volumes", "--remove-orphans"],
            capture_output=True,
        )


def test_install_backup_restore_update_undo_diagnostics(tmp_path) -> None:
    data = Path(os.environ.get("NEXUS_REHEARSAL_DATA", tmp_path / "ssd"))
    backup_disk = Path(os.environ.get("NEXUS_REHEARSAL_BACKUP", "/dev/shm")) / (
        "nexus-rehearsal-" + tmp_path.name
    )
    backup_disk.mkdir(parents=True)
    root = tmp_path / "opt"
    desk = Desk(root)
    bundles = tmp_path / "bundles"
    build_variant("eurogas-nexus-api:sd-reversible", "0097_sd_reversible", "reversible")
    build_variant("eurogas-nexus-api:sd-irreversible", "0097_sd_irreversible", "irreversible")
    build_variant(
        "eurogas-nexus-api:sd-broken", "0097_sd_broken", "reversible", ready=False
    )
    first = bundle(bundles, "1.0.0-sd.1", BASE_IMAGE)
    try:
        # -- install: the checks, the gated upgrade, the roles, the administrator
        output = desk.nexus(
            "install", "--data-dir", str(data), "--backup-dir", str(backup_disk),
            "--copy-dir", str(tmp_path / "office-copy"),
            "--server-name", "localhost", "--https-port", "18443",
            "--systemd-dir", str(tmp_path / "systemd"), "--bin-dir", str(tmp_path / "bin"),
            "--data-min-gb", "1", "--backup-min-gb", "1",
            tool=first / "nexus",
        )
        assert "The database and the backups are on different disks." in output
        assert "one-time password (shown once)" in output
        assert "No copy made" in output  # the office share is not connected yet: a warning
        assert "Installed" in output
        secrets = (root / "stack.env").read_text()
        for line in secrets.splitlines():
            if "PASSWORD=" in line or "SECRET_KEY=" in line or "TOKEN=" in line:
                assert line.split("=", 1)[1] not in output  # never printed
        assert oct((root / "stack.env").stat().st_mode)[-3:] == "600"
        assert (tmp_path / "systemd" / "eurogas-nexus.service").is_file()
        required = desk.revision()

        # -- status: every part in plain words (this test machine's disk may be nearly full,
        # so the overall verdict is not asserted)
        output = desk.nexus("status", expect=None)
        for part in ("Database: running.", "Application: running.", "Data scheduler: running.",
                     "Live re-evaluation: running.", "Web address (HTTPS): running.",
                     "The web address answers", "The database is at the right version.",
                     "Last good backup"):
            assert part in output, output
        facts = json.loads(desk.nexus("status", "--json", expect=None))["facts"]
        assert facts["probe"]["database"]["revision"] == required

        # -- backup, then a change, then restore: the change is gone
        (tmp_path / "office-copy").mkdir()  # the office share is connected from now on
        output = desk.nexus("backup")
        assert "Backup written and verified" in output
        assert "Copy written and checked" in output
        copies = list((tmp_path / "office-copy" / "nexus-backups").glob("nexus-*-manual.dump"))
        assert copies and not (tmp_path / "office-copy" / "nexus-backups" / "recovery-key.env"
                               ).exists()  # the key stays off the office copy by default
        desk.add_user("after_backup")
        assert "after_backup" in desk.users()
        listing = desk.nexus("restore")
        assert "manual" in listing
        output = desk.nexus("restore", "latest", "--yes")
        assert "Restored." in output
        assert "after_backup" not in desk.users()
        desk.add_user("written_after_restore")  # the application role can still write

        # -- update to a version with a reversible migration, then undo it (downgrade)
        reversible = bundle(bundles, "1.0.0-sd.2", "eurogas-nexus-api:sd-reversible")
        output = desk.nexus("update", str(reversible), "--yes", tool=reversible / "nexus")
        assert "Updated to 1.0.0-sd.2" in output
        assert desk.revision() == "0097_sd_reversible"
        desk.add_user("entered_after_update")
        output = desk.nexus("undo-update", "--yes")
        assert "can be undone" in output and "runs version 1.0.0-sd.1 again" in output
        assert desk.revision() == required
        assert "entered_after_update" in desk.users()  # a downgrade keeps the data

        # -- update to a version with an irreversible migration, then undo it (restore)
        irreversible = bundle(bundles, "1.0.0-sd.3", "eurogas-nexus-api:sd-irreversible")
        output = desk.nexus("update", str(irreversible), "--yes", tool=irreversible / "nexus")
        assert "Updated to 1.0.0-sd.3" in output
        assert desk.revision() == "0097_sd_irreversible"
        desk.add_user("lost_by_restore")
        output = desk.nexus("undo-update", "--yes")
        assert "cannot be undone" in output
        assert "Restored the backup taken before the update" in output
        assert desk.revision() == required
        assert "lost_by_restore" not in desk.users()
        assert "before-undo" in desk.nexus("restore")  # the lost data is kept in a file

        # -- an update whose new version never becomes ready undoes itself
        broken = bundle(bundles, "1.0.0-sd.4", "eurogas-nexus-api:sd-broken")
        output = desk.nexus("update", str(broken), "--yes", tool=broken / "nexus", expect=1)
        assert "Going back to 1.0.0-sd.1 automatically" in output
        assert "failed and was undone" in output
        assert desk.revision() == required
        state = json.loads((root / "state.json").read_text())
        assert state["current"]["version"] == "1.0.0-sd.1"
        assert state["update"]["status"] == "rolled back"

        # -- diagnostics: one archive, summary first, no secret anywhere in it
        output = desk.nexus("diagnostics", "--out", str(tmp_path / "diag"))
        archive = next((tmp_path / "diag").glob("nexus-diagnostics-*.zip"))
        with zipfile.ZipFile(archive) as opened:
            names = opened.namelist()
            assert names[0] == "SUMMARY.txt"
            assert {"status.txt", "status.json", "versions.txt", "recent-errors.txt"} <= set(names)
            assert any(name.startswith("logs/api") for name in names)
            text = "\n".join(opened.read(name).decode("utf-8", "replace") for name in names)
        for line in secrets.splitlines():
            name, _, value = line.partition("=")
            if value and any(word in name for word in ("PASSWORD", "SECRET", "TOKEN")):
                assert value not in text, f"{name} leaked into the diagnostics"
        recovery = (backup_disk / "nexus-backups" / "recovery-key.env").read_text()
        assert recovery.split("EUROGAS_NEXUS_SECRET_KEY=", 1)[1].split()[0] not in text
        assert "postgresql+pg8000://eurogas_app:<removed>@" in text or "pg8000" not in text
    finally:
        report = os.environ.get("NEXUS_REHEARSAL_REPORT")
        if report:
            Path(report).write_text(json.dumps(desk.timings, indent=2))
        desk.teardown()
        shutil.rmtree(backup_disk, ignore_errors=True)

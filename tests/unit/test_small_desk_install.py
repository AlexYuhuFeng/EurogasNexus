"""`nexus install` can be run again after any failure, and `nexus uninstall` keeps the data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "small-desk"))

from nexusctl import cli, operations  # noqa: E402
from nexusctl.settings import Settings, read_env  # noqa: E402
from nexusctl.stack import Result  # noqa: E402
from nexusctl.ui import Out  # noqa: E402

STEPS = [name for name, _ in operations.INSTALL_STEPS]
RELEASE = {"version": "1.0", "api_image": "img:1.0", "web_archive": "web.tar.gz"}


class Quiet(Out):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def _emit(self, text: str) -> None:
        self.lines.append(text)


class FakeStack:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def stop(self, services=()):
        self.calls.append("stop")
        return Result(0)

    def compose(self, args, **kwargs):
        self.calls.append(" ".join(args))
        return Result(0)


@pytest.fixture()
def machine(tmp_path, monkeypatch):
    """A PC on which every step is recorded instead of run."""

    ran: list[str] = []
    failing: dict[str, str] = {}
    stack = FakeStack()

    def make_step(name):
        def step(job):
            ran.append(name)
            if failing.get("at") == name:
                raise operations.Stop(f"{name} broke.", "Check the thing.")
        return step

    for name in STEPS:
        if name != "secrets":
            monkeypatch.setattr(operations.InstallJob, "step_" + name.replace("-", "_"),
                                make_step(name))
    real_secrets = operations.InstallJob.step_secrets

    def secrets(job):
        ran.append("secrets")
        real_secrets(job)
        if failing.get("at") == "secrets":
            raise operations.Stop("secrets broke.")

    monkeypatch.setattr(operations.InstallJob, "step_secrets", secrets)
    monkeypatch.setattr(operations.release, "read_release", lambda bundle: dict(RELEASE))
    monkeypatch.setattr(operations, "prerequisite_checks", lambda *a, **k: [])
    monkeypatch.setattr(operations, "export_certificate", lambda settings: None)
    monkeypatch.setattr(operations.Context, "stack_for", lambda self, version: stack)
    monkeypatch.setattr(operations.Context, "stack", lambda self: stack)

    def install(**overrides):
        settings = Settings(root=tmp_path / "opt", data_dir=tmp_path / "ssd",
                            backup_dir=tmp_path / "hdd", server_names=["desk"])
        for key, value in overrides.items():
            setattr(settings, key, value)
        out = Quiet()
        try:
            code = operations.install(
                bundle=tmp_path / "bundle", settings=settings, runner=None, out=out,
                admin_user="admin", allow_same_disk=False, systemd_dir=None, bin_dir=None,
                recovery_key=None, restore_from=None,
            )
        except operations.Stop as stop:
            return stop, out
        return code, out

    def state():
        return json.loads((tmp_path / "opt" / "state.json").read_text())

    return install, ran, failing, state, tmp_path


@pytest.mark.parametrize("failed", [s for s in STEPS if s != "restore"])
def test_a_failed_step_is_continued_by_running_install_again(machine, failed) -> None:
    install, ran, failing, state, tmp_path = machine
    failing["at"] = failed
    stop, out = install()
    assert isinstance(stop, operations.Stop)
    assert f"stopped at step '{failed}'" in str(stop)
    assert "run the same install command again" in stop.todo
    record = state()["install"]
    assert record["status"] == "in progress" and record["failed_step"] == failed
    expected_before = [s for s in STEPS[: STEPS.index(failed)] if s != "restore"]
    assert record["done"] == [s for s in STEPS[: STEPS.index(failed)]]
    assert ran == [*expected_before, failed]
    secrets_before = read_env(tmp_path / "opt" / "stack.env")

    failing.clear()
    ran.clear()
    code, out = install()
    assert code == 0, out.lines
    # Only the failed step and those after it run again (and the database is started);
    # nothing else before it is repeated.
    again = [s for s in STEPS[STEPS.index(failed):] if s != "restore"]
    if STEPS.index(failed) > STEPS.index("database"):
        again = ["database", *again]
    assert ran == again
    assert any("Continuing the installation that stopped at step" in line for line in out.lines)
    assert state()["install"]["status"] == "complete"
    if secrets_before:
        # The database was created with the first attempt's secrets: they are kept.
        assert read_env(tmp_path / "opt" / "stack.env") == secrets_before


def test_install_again_over_a_finished_installation_is_refused_plainly(machine) -> None:
    install, ran, failing, state, _ = machine
    assert install()[0] == 0
    before = state()
    ran.clear()
    stop, _ = install()
    assert isinstance(stop, operations.Stop)
    assert "already installed" in str(stop) and "Nothing was changed" in str(stop)
    assert "sudo nexus status" in stop.todo and "sudo nexus uninstall" in stop.todo
    assert ran == [] and state() == before


def test_install_never_takes_over_a_database_it_did_not_create(machine) -> None:
    install, ran, _, _, tmp_path = machine
    (tmp_path / "ssd" / "postgres").mkdir(parents=True)
    (tmp_path / "ssd" / "postgres" / "PG_VERSION").write_text("16")
    stop, _ = install()
    assert isinstance(stop, operations.Stop) and "did not create" in str(stop)
    assert ran == [] and not (tmp_path / "opt" / "state.json").exists()


def test_a_continued_install_must_use_the_same_folders(machine) -> None:
    install, _, failing, _, tmp_path = machine
    failing["at"] = "schema"
    install()
    failing.clear()
    stop, _ = install(data_dir=tmp_path / "elsewhere")
    assert isinstance(stop, operations.Stop) and "database folder" in str(stop)


def test_uninstall_keeps_data_and_a_new_install_takes_it_back(machine, monkeypatch) -> None:
    install, ran, _, state, tmp_path = machine
    assert install()[0] == 0
    for folder in (tmp_path / "ssd" / "postgres", tmp_path / "hdd" / "nexus-backups"):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "data").write_text("desk data")
    monkeypatch.setattr(operations, "take_backup", lambda *a, **k: None)
    ctx = operations.load_context(tmp_path / "opt", runner=None, out=Quiet())
    assert operations.uninstall(ctx, delete_data=False, confirmation=None, assume_yes=True) == 0
    assert (tmp_path / "ssd" / "postgres" / "data").read_text() == "desk data"
    assert (tmp_path / "hdd" / "nexus-backups" / "data").exists()
    assert (tmp_path / "opt" / "stack.env").exists()  # the secrets that open the database
    assert state()["install"]["status"] == "removed"

    ran.clear()
    code, out = install()
    assert code == 0, out.lines
    assert "secrets" not in ran and "roles" not in ran and "administrator" not in ran
    assert "database" in ran
    assert "schema" in ran  # brought to this version's schema (backup first: step_schema)
    assert any("over the data kept" in line for line in out.lines)


def test_uninstall_deletes_data_only_with_the_typed_words(machine) -> None:
    install, _, _, _, tmp_path = machine
    assert install()[0] == 0
    (tmp_path / "ssd" / "postgres").mkdir(parents=True, exist_ok=True)
    ctx = operations.load_context(tmp_path / "opt", runner=None, out=Quiet())
    assert operations.uninstall(ctx, delete_data=True, confirmation="yes", assume_yes=True) == 1
    assert (tmp_path / "ssd").exists() and (tmp_path / "opt" / "stack.env").exists()
    assert operations.uninstall(
        ctx, delete_data=True, confirmation=operations.DELETE_WORDS, assume_yes=False
    ) == 0
    assert not (tmp_path / "ssd").exists() and not (tmp_path / "opt").exists()


def test_commands_after_uninstall_say_how_to_come_back(machine, monkeypatch) -> None:
    install, _, _, state, tmp_path = machine
    assert install()[0] == 0
    monkeypatch.setattr(operations, "take_backup", lambda *a, **k: None)
    ctx = operations.load_context(tmp_path / "opt", runner=None, out=Quiet())
    operations.uninstall(ctx, delete_data=False, confirmation=None, assume_yes=True)
    out = Quiet()
    assert cli.main(["--root", str(tmp_path / "opt"), "status"], runner=None, out=out) == 1
    assert any("was removed from this PC" in line for line in out.lines)

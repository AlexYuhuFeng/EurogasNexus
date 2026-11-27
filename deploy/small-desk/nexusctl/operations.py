"""What each `nexus` command does, step by step. Decisions live in the modules it calls."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from nexusctl import backup as backups
from nexusctl import checks, release, status, systemd
from nexusctl.checks import FAIL, OK, WARN
from nexusctl.settings import (
    FIXED_STACK_VALUES,
    Settings,
    generate_secrets,
    load_state,
    read_env,
    save_state,
    write_env,
)
from nexusctl.stack import Runner, Stack
from nexusctl.ui import Out, human_bytes

UPGRADE = ["python", "scripts/ops/upgrade_database.py"]
SEND_DIAGNOSTICS = status.SEND_DIAGNOSTICS


class Stop(RuntimeError):
    """A command cannot go on; the message says why and what to do. Exit code 1."""

    def __init__(self, message: str, todo: str | None = None) -> None:
        super().__init__(message)
        self.todo = todo


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Context:
    settings: Settings
    runner: Runner
    out: Out
    state: dict

    def stack_for(self, version: str) -> Stack:
        directory, data = release.load_installed(self.settings.releases_dir, version)
        return Stack(self.settings, directory, data, self.runner)

    @property
    def version(self) -> str:
        return (self.state.get("current") or {}).get("version", "unknown")

    def stack(self) -> Stack:
        return self.stack_for(self.version)

    def save(self) -> None:
        save_state(self.settings, self.state)


def load_context(root: Path, runner: Runner, out: Out | None = None) -> Context:
    try:
        settings = Settings.load(root)
    except FileNotFoundError as exc:
        raise Stop(
            f"Eurogas Nexus is not installed in {root}.",
            "Install it first: `sudo ./nexus install` from the release folder.",
        ) from exc
    out = out or Out(log_path=settings.log_path)
    out.log_path = settings.log_path
    return Context(settings, runner, out, load_state(settings))


# ====================================================================== database helpers
def db_value(stack: Stack, sql: str, database: str | None = None) -> str | None:
    result = stack.psql(sql, database=database or stack.secrets()["POSTGRES_DB"], timeout=60)
    if not result.ok:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines[0].strip() if lines else None


def db_revision(stack: Stack, database: str | None = None) -> str | None:
    return db_value(stack, "SELECT version_num FROM alembic_version LIMIT 1;", database)


def migrate_plan(stack: Stack) -> dict | None:
    result = stack.run_once("migrate", [*UPGRADE, "plan", "--json"], timeout=600)
    if not result.ok:
        return None
    for line in reversed(result.stdout.strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


def run_upgrade(ctx: Context, stack: Stack, operator: str, reason: str | None = None) -> int:
    argv = [*UPGRADE, "upgrade", "--operator", operator, "--yes"]
    if reason:
        argv += ["--without-backup", reason]
    result = stack.run_once("migrate", argv, timeout=7200)
    for line in (result.stdout or "").splitlines():
        if line.startswith(("upgraded to", "REFUSED", "FAILED", "pending revisions")):
            ctx.out.info(line.strip())
    return result.returncode


def probe(stack: Stack) -> dict | None:
    found, _error = status.probe_fact(stack)
    return found


def bring_up(ctx: Context, stack: Stack, *, quiet: bool = False) -> tuple[bool, str]:
    """Start every part and wait until healthy. (healthy, reason)."""

    started = stack.up()
    ready, _states, failed = stack.wait_ready(ctx.settings.health_timeout_seconds)
    if not started.ok and not failed:
        tail = (started.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        return False, f"the start stopped: {tail[0][:200]}"
    found = probe(stack) if ready else None
    healthy, reason = release.update_outcome(
        upgrade_returncode=0, ready=ready, failed_parts=failed, probe=found
    )
    if healthy and not quiet:
        ctx.out.ok("Every part is running.")
    return healthy, reason


# ====================================================================== install
def prerequisite_checks(
    settings: Settings,
    runner: Runner,
    *,
    allow_same_disk: bool,
    data_min_gb: int = checks.DATA_DISK_MIN_GB,
    backup_min_gb: int = checks.BACKUP_DISK_MIN_GB,
) -> list:
    server = runner.run(["docker", "version", "--format", "{{.Server.Version}}"], timeout=30)
    compose = runner.run(["docker", "compose", "version", "--short"], timeout=30)
    found = [
        checks.Check("root", OK, "Running with administrator rights.")
        if os.geteuid() == 0
        else checks.Check(
            "root", FAIL, "This needs administrator rights.", "Run it again with sudo in front."
        )
    ]
    found += checks.judge_docker(
        server.stdout.strip() if server.ok else None, compose.stdout.strip() if compose.ok else None
    )
    found.append(
        checks.judge_memory(
            checks.parse_meminfo_gb(checks.read_text("/proc/meminfo")), os.cpu_count()
        )
    )
    free, total = checks.disk_usage(settings.data_dir)
    found.append(checks.judge_disk_space("database disk", free, total, data_min_gb))
    found.append(
        checks.judge_two_disks(
            settings.data_dir,
            settings.backup_dir,
            device_of=checks.device_of,
            exists=lambda path: Path(path).is_dir(),
            allow_same_disk=allow_same_disk,
        )
    )
    if Path(settings.backup_dir).is_dir():
        free, total = checks.disk_usage(settings.backup_dir)
        found.append(
            checks.judge_disk_space("backup disk", free, total, backup_min_gb)
        )
    clock = status.clock_facts(runner)
    found.append(checks.judge_clock(clock["synchronized"], clock["offset"]))
    found.append(
        checks.judge_port(
            settings.https_port, checks.port_in_use(settings.https_port, settings.bind_address)
        )
    )
    return found


def default_server_names() -> list[str]:
    names = [socket.gethostname()]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe_socket:
            probe_socket.connect(("192.0.2.1", 9))  # no packet is sent (UDP connect)
            address = probe_socket.getsockname()[0]
        if address and not address.startswith("127."):
            names.append(address)
    except OSError:
        pass
    return names


def _image_user(runner: Runner, image: str) -> tuple[int, int] | None:
    result = runner.run(
        ["docker", "run", "--rm", "--entrypoint", "id", image], timeout=120
    )
    match = re.search(r"uid=(\d+).*?gid=(\d+)", result.stdout or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def copy_tool(bundle: Path, settings: Settings, bin_dir: Path | None) -> Path:
    target = settings.root / "tool"
    staging = settings.root / "tool.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copy2(bundle / "nexus", staging / "nexus")
    shutil.copytree(
        bundle / "nexusctl", staging / "nexusctl", ignore=shutil.ignore_patterns("__pycache__")
    )
    (staging / "nexus").chmod(0o755)
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)
    if bin_dir is not None:
        link = bin_dir / "nexus"
        bin_dir.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target / "nexus")
    return target / "nexus"


def roles_sql(values: dict[str, str], roles_file: Path) -> str:
    """deploy/runtime/database_roles.sql with its variables set (passwords are hex only)."""

    for name in (
        "EUROGAS_NEXUS_OWNER_DB_PASSWORD",
        "EUROGAS_NEXUS_APP_DB_PASSWORD",
        "NEXUS_READER_DB_PASSWORD",
    ):
        if not re.fullmatch(r"[A-Za-z0-9]+", values[name]):
            raise ValueError(f"{name} must be letters and digits only")
    head = "\n".join(
        [
            f"\\set owner_password '''{values['EUROGAS_NEXUS_OWNER_DB_PASSWORD']}'''",
            f"\\set app_password '''{values['EUROGAS_NEXUS_APP_DB_PASSWORD']}'''",
            f"\\set reader_password '''{values['NEXUS_READER_DB_PASSWORD']}'''",
            f"\\set db {values['POSTGRES_DB']}",
        ]
    )
    return head + "\n" + roles_file.read_text(encoding="utf-8")


def install(
    *,
    bundle: Path,
    settings: Settings,
    runner: Runner,
    out: Out,
    admin_user: str,
    allow_same_disk: bool,
    systemd_dir: Path | None,
    bin_dir: Path | None,
    recovery_key: Path | None,
    restore_from: Path | None,
    ignore_checks: bool = False,
    data_min_gb: int = checks.DATA_DISK_MIN_GB,
    backup_min_gb: int = checks.BACKUP_DISK_MIN_GB,
) -> int:
    out.title("Installing Eurogas Nexus on this PC")
    rel = release.read_release(bundle)
    out.ok(f"Release folder: version {rel['version']}.")
    if settings.state_path.is_file():
        raise Stop(
            f"Eurogas Nexus is already installed in {settings.root}.",
            "To see how it is: `sudo nexus status`. To install a new version: "
            "`sudo nexus update <release folder>`.",
        )

    out.line("\nChecking this PC")
    found = prerequisite_checks(
        settings,
        runner,
        allow_same_disk=allow_same_disk,
        data_min_gb=data_min_gb,
        backup_min_gb=backup_min_gb,
    )
    for item in found:
        {OK: out.ok, WARN: out.warn, FAIL: out.problem}[item.status](
            *([item.message] if item.status == OK else [item.message, item.todo])
        )
    if any(item.failed for item in found) and not ignore_checks:
        raise Stop("This PC is not ready. Nothing was changed.", "Fix the problems above, then "
                   "run the same command again.")

    out.line("\nInstalling")
    settings.root.mkdir(parents=True, exist_ok=True)
    out.log_path = settings.log_path
    out.step("putting the release in place (this can take a few minutes the first time)")
    release_dir = release.install_release(bundle, rel, settings.releases_dir, runner)
    shutil.copyfile(bundle / "deploy" / "database_roles.sql", release_dir / "database_roles.sql")

    out.step("creating the secrets (kept on this PC, readable only by the administrator)")
    values = dict(FIXED_STACK_VALUES)
    values.update(generate_secrets())
    if recovery_key is not None:
        kept = read_env(recovery_key)
        if not kept.get("EUROGAS_NEXUS_SECRET_KEY"):
            raise Stop(f"{recovery_key} holds no recovery key.", "Give the recovery-key.env file "
                       "from the old PC's backup disk.")
        values.update({name: value for name, value in kept.items() if name.startswith("EUROGAS")})
    write_env(settings.env_path, values, header="Eurogas Nexus secrets. Never share this file.")
    settings.save()

    for sub in ("postgres", "artifacts", "gateway"):
        (settings.data_dir / sub).mkdir(parents=True, exist_ok=True)
    owner = _image_user(runner, rel["api_image"])
    if owner:
        os.chown(settings.data_dir / "artifacts", *owner)
    settings.backups.mkdir(parents=True, exist_ok=True)
    os.chmod(settings.backups, 0o700)

    ctx = Context(
        settings,
        runner,
        out,
        {
            "current": {"version": rel["version"], "api_image": rel["api_image"],
                        "installed_at_utc": iso(now_utc())},
            "previous": None,
            "update": None,
            "history": [{"at_utc": iso(now_utc()), "event": "installed",
                         "version": rel["version"]}],
        },
    )
    ctx.save()
    nexus = copy_tool(bundle, settings, bin_dir)
    stack = ctx.stack()

    out.step("starting the database")
    stack.up(["postgres"])
    if not stack.wait_database():
        raise Stop("The database did not start.", SEND_DIAGNOSTICS)

    superuser_url = (
        f"postgresql+pg8000://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@postgres:5432/{values['POSTGRES_DB']}"
    )
    out.step("creating the database tables (the gated database upgrade)")
    result = stack.run_once(
        "migrate",
        [*UPGRADE, "upgrade", "--operator", "nexus install", "--yes"],
        pass_env={"RUNTIME_STORE_DATABASE_URL": superuser_url},
        timeout=3600,
    )
    if not result.ok:
        raise Stop("The database tables could not be created.", SEND_DIAGNOSTICS)
    out.ok("Database tables created.")

    out.step("separating the database roles (schema owner, application, reader)")
    applied = stack.psql(roles_sql(values, release_dir / "database_roles.sql"),
                         database=values["POSTGRES_DB"])
    if not applied.ok:
        raise Stop("The database roles could not be set up.", SEND_DIAGNOSTICS)
    out.ok("Database roles set up.")

    if restore_from is not None:
        out.step(f"restoring the desk's data from {restore_from}")
        restore(ctx, str(restore_from), assume_yes=True, safety_backup=False, start=False)

    out.step("starting every part (a few minutes)")
    healthy, reason = bring_up(ctx, stack)
    if not healthy:
        raise Stop(f"The product did not start: {reason}.", SEND_DIAGNOSTICS)

    if restore_from is None:
        out.step(f"creating the first administrator, {admin_user!r}")
        out.line(
            "\n  >>> Write down the one-time password printed below. It is shown only once. <<<\n"
        )
        created = stack.run_once(
            "api",
            [
                "python", "-m", "eurogas_nexus.cli.accounts", "create",
                "--username", admin_user, "--display-name", "Administrator",
                "--admin", "--scope", "BOOKS:*",
            ],
            passthrough=True,
            timeout=300,
        )
        out.line("")
        if not created.ok:
            out.problem("The administrator could not be created.", SEND_DIAGNOSTICS)

    out.step("taking the first backup")
    take_backup(ctx, "manual")

    out.step("starting on boot and backing up every night")
    enable_boot(ctx, nexus, systemd_dir)

    certificate = export_certificate(settings)
    out.title("Installed")
    out.line(f"Open this address in a browser on the traders' PCs:  {settings.browser_address()}")
    for name in settings.server_names[1:]:
        port = "" if settings.https_port == 443 else f":{settings.https_port}"
        out.line(f"  (or https://{name}{port})")
    if certificate:
        out.line(
            f"The browsers must trust this server's certificate once: install {certificate} on "
            "each trader's PC as a trusted root certificate (install guide, step 6)."
        )
    if restore_from is None:
        out.line(
            f"Sign in as {admin_user!r} with the one-time password above; you will choose your "
            "own password and set up an authenticator app (second factor)."
        )
    out.line(
        f"Keep a copy of {settings.backups / 'recovery-key.env'} in the firm's password safe: a "
        "replacement PC needs it to read the restored data (helpdesk card)."
    )
    out.line("Check the desk server at any time with:  sudo nexus status")
    return 0


def export_certificate(settings: Settings) -> Path | None:
    source = settings.gateway_root_certificate
    if settings.tls != "internal" or not source.is_file():
        return None
    target = settings.root / "desk-server-certificate.crt"
    shutil.copyfile(source, target)
    target.chmod(0o644)
    return target


def enable_boot(ctx: Context, nexus: Path, systemd_dir: Path | None) -> None:
    if systemd_dir is None:
        ctx.out.warn(
            "Start on boot and the nightly backup were not set up (asked not to).",
            "Run `sudo nexus install` without --no-systemd on the real server.",
        )
        return
    systemd.write_units(systemd_dir, nexus, ctx.settings.backup_time)
    if shutil.which("systemctl") is None or not Path("/run/systemd/system").is_dir():
        ctx.out.warn(
            f"The start-on-boot and nightly-backup units were written to {systemd_dir}, but "
            "this PC does not run systemd, so they are not active.",
            "Ask IT to start `nexus start` at boot and `nexus backup --scheduled` nightly.",
        )
        return
    for argv in systemd.enable_commands():
        result = ctx.runner.run(argv, timeout=60)
        if not result.ok:
            ctx.out.problem(f"`{' '.join(argv)}` failed.", SEND_DIAGNOSTICS)
            return
    ctx.out.ok(
        f"Starts by itself after a restart or power cut; backs up every night at "
        f"{ctx.settings.backup_time}."
    )


# ====================================================================== start, stop
def start(ctx: Context, *, quiet: bool = False) -> int:
    if not quiet:
        ctx.out.title(f"Starting Eurogas Nexus {ctx.version}")
    healthy, reason = bring_up(ctx, ctx.stack(), quiet=quiet)
    if not healthy:
        ctx.out.problem(f"It did not start properly: {reason}.", SEND_DIAGNOSTICS)
        return 1
    if not quiet:
        ctx.out.line(f"Open {ctx.settings.browser_address()} in a browser.")
    return 0


def stop(ctx: Context, *, quiet: bool = False) -> int:
    if not quiet:
        ctx.out.title("Stopping Eurogas Nexus")
    result = ctx.stack().stop()
    if not result.ok:
        ctx.out.problem("Some parts did not stop cleanly.", SEND_DIAGNOSTICS)
        return 1
    if not quiet:
        ctx.out.ok("Stopped. Start it again with: sudo nexus start")
    return 0


def show_status(ctx: Context, *, as_json: bool = False) -> int:
    facts = status.collect(ctx.settings, ctx.stack(), ctx.runner, version=ctx.version)
    findings = status.evaluate(facts, now_utc())
    if as_json:
        print(json.dumps({"facts": facts, "findings": [f.__dict__ for f in findings]},
                         indent=2, default=str))
    else:
        status.render(findings, ctx.out, version=ctx.version)
    return 1 if status.overall(findings) == "PROBLEMS" else 0


# ====================================================================== backup
def protected_backups(state: dict) -> frozenset[str]:
    update = state.get("update") or {}
    name = Path(update.get("pre_update_backup") or "").name
    return frozenset({name} if name and state.get("previous") else set())


def take_backup(ctx: Context, label: str, *, stack: Stack | None = None) -> backups.BackupInfo:
    """Dump, verify, record, copy, thin. Raises Stop when the backup is not good."""

    settings, out = ctx.settings, ctx.out
    stack = stack or ctx.stack()
    directory = settings.backups
    directory.mkdir(parents=True, exist_ok=True)
    moment = now_utc()
    path = directory / backups.backup_name(moment, label)
    partial = path.with_name(path.name + ".partial")
    values = stack.secrets()

    def fail(reason: str) -> Stop:
        if partial.exists():
            partial.unlink()
        backups.record_attempt(
            directory, {"at_utc": iso(now_utc()), "error": reason, "label": label}, success=False
        )
        return Stop(f"The backup failed: {reason}.", "Run `sudo nexus status`; " + SEND_DIAGNOSTICS)

    with partial.open("wb") as handle:
        dumped = stack.exec(
            "postgres",
            ["pg_dump", "--format=custom", "--username", values["POSTGRES_USER"],
             values["POSTGRES_DB"]],
            stdout_file=handle,
            timeout=7200,
        )
        handle.flush()
        os.fsync(handle.fileno())
    if not dumped.ok:
        detail = (dumped.stderr or "").strip()[-160:]
        raise fail(f"the database could not be copied ({detail})")
    digest = backups.sha256_of(partial)
    with partial.open("rb") as handle:
        listing = stack.exec("postgres", ["pg_restore", "--list"], stdin_file=handle, timeout=900)
    if not listing.ok or not backups.toc_is_complete(listing.stdout):
        raise fail("the backup file could not be read back (verification failed)")
    os.chmod(partial, 0o600)  # password hashes and the audit trail are in it
    os.replace(partial, path)
    info = backups.BackupInfo(
        path=path,
        created=moment,
        label=label,
        verified=True,
        sha256=digest,
        size=path.stat().st_size,
        version=ctx.version,
        db_revision=db_revision(stack),
    )
    backups.write_note(info)
    out.ok(f"Backup written and verified: {path} ({human_bytes(info.size)}).")

    recorded = stack.run_once(
        "migrate",
        [*UPGRADE, "record-backup", "--operator", "nexus backup", "--kind", "pg_dump",
         "--reference", f"{path.name} sha256:{digest[:16]}"],
        timeout=300,
    )
    if not recorded.ok:
        out.warn("The backup could not be noted in the audit trail (an update will ask for one).")
    backups.write_recovery_key(settings, directory)

    copies = []
    if settings.copy_dir is not None:
        if not settings.copy_dir.is_dir():
            copies.append({"dest": str(settings.copy_dir), "ok": False,
                           "detail": "the office share or removable disk is not connected"})
            out.warn(
                f"No copy made: {settings.copy_dir} is not connected.",
                "Connect the office share or removable disk; the next backup copies again.",
            )
        else:
            ok, detail = backups.copy_to(info, settings.copy_dir)
            if ok and settings.copy_keys:
                shutil.copyfile(directory / "recovery-key.env",
                                settings.copy_dir / "nexus-backups" / "recovery-key.env")
            copies.append({"dest": str(settings.copy_dir), "ok": ok, "detail": detail})
            if ok:
                out.ok(f"Copy written and checked: {detail}.")
                thin(ctx, settings.copy_dir / "nexus-backups", quiet=True)
            else:
                out.warn(f"The copy failed: {detail}.", "Check the office share or removable disk.")
    thin(ctx, directory)
    backups.record_attempt(
        directory,
        {**info.note(), "finished_at_utc": iso(now_utc()), "copies": copies},
        success=True,
    )
    return info


def thin(ctx: Context, directory: Path, *, quiet: bool = False) -> None:
    settings = ctx.settings
    doomed = backups.select_for_deletion(
        backups.list_backups(directory),
        now_utc(),
        keep_daily=settings.keep_daily,
        keep_weekly=settings.keep_weekly,
        keep_monthly=settings.keep_monthly,
        protected=protected_backups(ctx.state),
    )
    for item in doomed:
        backups.remove_backup(item.path)
    if doomed and not quiet:
        ctx.out.ok(f"Removed {len(doomed)} old backup(s) (kept: daily for {settings.keep_daily} "
                   f"days, weekly for {settings.keep_weekly} weeks, monthly for "
                   f"{settings.keep_monthly} months).")


def backup(ctx: Context, *, scheduled: bool = False) -> int:
    ctx.out.title("Backing up Eurogas Nexus")
    take_backup(ctx, "nightly" if scheduled else "manual")
    return 0


# ====================================================================== restore
def list_choices(ctx: Context) -> list[backups.BackupInfo]:
    rows = backups.list_backups(ctx.settings.backups)
    ctx.out.line("\nBackups on the backup disk (newest first):")
    for number, item in enumerate(rows, 1):
        mark = "" if item.verified else "  (NOT verified: do not use)"
        ctx.out.line(
            f"  {number:>2}. {item.created.strftime('%Y-%m-%d %H:%M')} UTC  {item.label:<14} "
            f"version {item.version or '?':<14} {human_bytes(item.size)}{mark}"
        )
    if not rows:
        ctx.out.line("  (none)")
    return rows


def resolve_backup(ctx: Context, choice: str) -> backups.BackupInfo:
    rows = backups.list_backups(ctx.settings.backups)
    if choice in {"latest", "newest"}:
        rows = [item for item in rows if item.verified]
        if not rows:
            raise Stop("There is no verified backup to restore.")
        return rows[0]
    if choice.isdigit() and 1 <= int(choice) <= len(rows):
        return rows[int(choice) - 1]
    path = Path(choice)
    if path.is_file():
        parsed = backups.parse_name(path.name)
        listed = backups.list_backups(path.parent)
        for item in listed:
            if item.path.resolve() == path.resolve():
                return item
        created, label = parsed if parsed else (now_utc(), "manual")
        return backups.BackupInfo(path=path, created=created, label=label, verified=False)
    raise Stop(f"No backup {choice!r}.", "Run `sudo nexus restore` to list them; give a number, "
               "`latest`, or a file.")


def restore_database(ctx: Context, stack: Stack, info: backups.BackupInfo) -> str:
    """Restore into a fresh database and put it in place. Returns the old database's new name.

    The application must be stopped. Raises Stop (nothing in place changed) on failure.
    """

    values = stack.secrets()
    main_db = values["POSTGRES_DB"]
    stamp = now_utc().strftime("%Y%m%d%H%M%S")
    fresh = f"nexus_restore_{stamp}"
    previous = f"nexus_before_restore_{stamp}"
    owner = values["EUROGAS_NEXUS_OWNER_DB_USER"]
    if info.sha256 and backups.sha256_of(info.path) != info.sha256:
        raise Stop(f"{info.path.name} is damaged (its checksum differs). Nothing was changed.",
                   "Choose another backup (`sudo nexus restore`).")
    ctx.out.step(f"restoring {info.path.name} into a fresh database")
    created = stack.psql(f'CREATE DATABASE "{fresh}" OWNER "{owner}";')
    if not created.ok:
        raise Stop("A fresh database could not be created. Nothing was changed.", SEND_DIAGNOSTICS)
    with info.path.open("rb") as handle:
        restored = stack.exec(
            "postgres",
            ["pg_restore", "--exit-on-error", "--single-transaction",
             "--username", values["POSTGRES_USER"], "--dbname", fresh],
            stdin_file=handle,
            timeout=7200,
        )
    revision = db_revision(stack, fresh) if restored.ok else None
    if not restored.ok or not revision:
        stack.psql(f'DROP DATABASE IF EXISTS "{fresh}";')
        detail = (restored.stderr or "").strip().splitlines()[-1:] or ["no schema version"]
        raise Stop(f"The backup could not be restored ({detail[0][:160]}). Nothing was changed.",
                   SEND_DIAGNOSTICS)
    ctx.out.ok(f"Restored and readable (database version {revision}).")
    swapped = stack.psql(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname IN ('{main_db}', '{fresh}') AND pid <> pg_backend_pid();\n"
        f'ALTER DATABASE "{main_db}" RENAME TO "{previous}";\n'
        f'ALTER DATABASE "{fresh}" RENAME TO "{main_db}";\n'
    )
    if not swapped.ok:
        raise Stop("The restored database could not be put in place.", SEND_DIAGNOSTICS)
    # Keep only the newest replaced database (it is the way back from this restore).
    older = stack.psql(
        "SELECT datname FROM pg_database WHERE datname LIKE 'nexus_before_restore_%' "
        f"AND datname <> '{previous}';"
    )
    for name in (older.stdout or "").split():
        if re.fullmatch(r"nexus_before_restore_\d{14}", name):
            stack.psql(f'DROP DATABASE IF EXISTS "{name}";')
    return previous


def swap_back(stack: Stack, previous: str) -> bool:
    main_db = stack.secrets()["POSTGRES_DB"]
    failed = f"nexus_failed_restore_{now_utc().strftime('%Y%m%d%H%M%S')}"
    result = stack.psql(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{main_db}' AND pid <> pg_backend_pid();\n"
        f'ALTER DATABASE "{main_db}" RENAME TO "{failed}";\n'
        f'ALTER DATABASE "{previous}" RENAME TO "{main_db}";\n'
    )
    return result.ok


def bring_schema_current(ctx: Context, stack: Stack, info: backups.BackupInfo) -> None:
    plan = migrate_plan(stack)
    if plan is None:
        raise Stop(
            f"{info.path.name} comes from a newer version than the one running "
            f"({ctx.version}).",
            "Restore it after updating to that version, or choose an older backup.",
        )
    if plan.get("up_to_date"):
        return
    ctx.out.step("the backup is from an older version: upgrading its database (gated upgrade)")
    code = run_upgrade(
        ctx, stack, "nexus restore", reason=f"the restored backup {info.path.name} is the backup"
    )
    if code != 0:
        raise Stop("The restored database could not be upgraded to this version.",
                   SEND_DIAGNOSTICS)


def restore(
    ctx: Context,
    choice: str | None,
    *,
    assume_yes: bool,
    safety_backup: bool = True,
    start: bool = True,
    stack: Stack | None = None,
) -> int:
    stack = stack or ctx.stack()
    if not choice:
        ctx.out.title("Restore a backup")
        list_choices(ctx)
        ctx.out.line(
            "\nTo restore one: sudo nexus restore <number>   (or `latest`, or a backup file)."
        )
        return 0
    info = resolve_backup(ctx, choice)
    ctx.out.title(f"Restoring the backup of {info.created.strftime('%Y-%m-%d %H:%M')} UTC")
    ctx.out.line(
        "Everything recorded after that time is replaced by the backup. The current data is "
        "first saved as a backup of its own, and the replaced database is kept until the next "
        "restore."
    )
    if not assume_yes and not confirm("Type 'restore' to continue: ", "restore"):
        ctx.out.line("Not restored. Nothing was changed.")
        return 1
    if safety_backup:
        try:
            take_backup(ctx, "before-restore", stack=stack)
        except Stop as exc:
            ctx.out.warn(f"The current data could not be backed up first ({exc}).")
            if not assume_yes and not confirm("Restore anyway? Type 'yes': ", "yes"):
                return 1
    ctx.out.step("stopping the application (the database keeps running)")
    stack.remove_application()
    stack.up(["postgres"])
    stack.wait_database()
    previous = restore_database(ctx, stack, info)
    try:
        bring_schema_current(ctx, stack, info)
    except Stop:
        swap_back(stack, previous)
        stack.up()
        raise
    if not start:
        return 0
    healthy, reason = bring_up(ctx, stack)
    if not healthy:
        ctx.out.problem(f"The restored desk did not start ({reason}); putting the previous "
                        "database back.")
        stack.remove_application()
        swap_back(stack, previous)
        bring_up(ctx, stack)
        raise Stop("The restore was undone; the desk runs on the data it had before.",
                   SEND_DIAGNOSTICS)
    ctx.state.setdefault("history", []).append(
        {"at_utc": iso(now_utc()), "event": "restored", "backup": info.path.name}
    )
    ctx.save()
    ctx.out.ok(f"Restored. The replaced database is kept as {previous}.")
    return 0


def confirm(prompt: str, word: str) -> bool:
    try:
        return input(prompt).strip().lower() == word
    except EOFError:
        return False


# ====================================================================== update, undo
def update(ctx: Context, bundle: Path, *, assume_yes: bool, force: bool = False) -> int:
    new = release.read_release(bundle)
    current = ctx.state.get("current") or {}
    out = ctx.out
    out.title(f"Updating Eurogas Nexus from {current.get('version')} to {new['version']}")
    if new["version"] == current.get("version") and not force:
        out.ok(f"Version {new['version']} is already running. Nothing to do.")
        return 0
    out.line(
        "The desk is unavailable for a few minutes. A backup is taken first; if the new version "
        "does not start properly the previous one comes back by itself."
    )
    if not assume_yes and not confirm("Type 'update' to continue: ", "update"):
        out.line("Not updated. Nothing was changed.")
        return 1
    old_stack = ctx.stack()

    out.step("backing up before the update")
    pre = take_backup(ctx, "pre-update", stack=old_stack)
    from_revision = db_revision(old_stack)

    out.step("putting the new version in place")
    new_dir = release.install_release(bundle, new, ctx.settings.releases_dir, ctx.runner)
    if (bundle / "deploy" / "database_roles.sql").is_file():
        shutil.copyfile(bundle / "deploy" / "database_roles.sql", new_dir / "database_roles.sql")
    if (bundle / "nexusctl").is_dir():
        copy_tool(bundle, ctx.settings, None)
    new_stack = Stack(ctx.settings, new_dir, new, ctx.runner)

    out.step("stopping the application")
    old_stack.remove_application()
    new_stack.up(["postgres"])
    new_stack.wait_database()
    plan = migrate_plan(new_stack) or {"pending": []}
    pending = plan.get("pending") or []
    ctx.state["previous"] = dict(current)
    ctx.state["update"] = {
        "from": current.get("version"),
        "to": new["version"],
        "from_revision": from_revision,
        "applied": [
            {"revision": item["revision"], "reversibility": item["reversibility"]}
            for item in pending
        ],
        "pre_update_backup": str(pre.path),
        "started_at_utc": iso(now_utc()),
        "status": "applying",
    }
    ctx.state["current"] = {
        "version": new["version"], "api_image": new["api_image"],
        "installed_at_utc": iso(now_utc()),
    }
    ctx.save()
    undo_note = release.plan_undo(ctx.state["update"]["applied"])
    out.info(f"Database changes in this update: {len(pending)}. If undone: {undo_note.reason}.")

    code = 0
    if pending:
        out.step("upgrading the database (the gated upgrade)")
        code = run_upgrade(ctx, new_stack, "nexus update")
    healthy, reason = (False, "the database upgrade did not complete")
    if code == 0:
        out.step("starting the new version and checking its health")
        healthy, reason = bring_up(ctx, new_stack)
    if not healthy:
        out.problem(f"The new version is not healthy: {reason}.")
        out.line(f"Going back to {current.get('version')} automatically.")
        undo_update(ctx, assume_yes=True, automatic=True)
        ctx.state["update"]["status"] = "rolled back"
        ctx.save()
        raise Stop(
            f"The update to {new['version']} failed and was undone: the desk runs version "
            f"{current.get('version')} again.",
            SEND_DIAGNOSTICS,
        )
    ctx.state["update"]["status"] = "done"
    ctx.state.setdefault("history", []).append(
        {"at_utc": iso(now_utc()), "event": "updated", "from": current.get("version"),
         "to": new["version"]}
    )
    ctx.save()
    out.title(f"Updated to {new['version']}")
    out.line(
        f"If something is wrong, `sudo nexus undo-update` returns to {current.get('version')}."
    )
    return 0


def undo_update(ctx: Context, *, assume_yes: bool, automatic: bool = False) -> int:
    out = ctx.out
    previous = ctx.state.get("previous")
    update_record = ctx.state.get("update") or {}
    if not previous:
        out.title("Undo the last update")
        out.ok("There is no update to undo.")
        return 0
    current_version = ctx.version
    current_stack = ctx.stack()
    previous_stack = ctx.stack_for(previous["version"])
    target = update_record.get("from_revision")
    actual = db_revision(current_stack)
    applied = update_record.get("applied") or []
    plan = (
        release.UndoPlan("switch", "the database was not changed")
        if actual is not None and actual == target
        else release.plan_undo(applied)
    )
    if not automatic:
        out.title(f"Undoing the update: back from {current_version} to {previous['version']}")
    out.info(f"How: {plan.reason}.")
    if plan.method == "restore":
        out.line(
            "The backup taken just before the update will be restored: anything entered since "
            f"the update ({update_record.get('started_at_utc')}) is not in it. The current data "
            "is saved as a backup file first."
        )
    if not assume_yes and not confirm("Type 'undo' to continue: ", "undo"):
        out.line("Not changed.")
        return 1

    method = plan.method
    if method in {"downgrade", "restore"}:
        try:
            current_stack.up(["postgres"])
            current_stack.wait_database()
            kept = take_backup(ctx, "before-undo", stack=current_stack)
            out.info(f"The data as it was before the undo is kept in {kept.path}.")
        except Stop as exc:
            out.warn(f"The current data could not be backed up first ({exc}).")
            if method == "downgrade":
                method = "restore"
    current_stack.remove_application()
    current_stack.up(["postgres"])
    current_stack.wait_database()
    if method == "downgrade":
        out.step("undoing the database changes of the update")
        result = current_stack.run_once(
            "migrate",
            [*UPGRADE, "downgrade", "--to", target, "--operator", "nexus undo-update", "--yes"],
            timeout=7200,
        )
        if not result.ok:
            out.warn(
                "The database changes could not be undone in place (a change refused because "
                "data recorded since would be lost); restoring the backup taken before the "
                "update instead."
            )
            method = "restore"
    if method == "restore":
        info = resolve_backup(ctx, update_record["pre_update_backup"])
        restore_database(ctx, previous_stack, info)
        out.info(
            f"Restored the backup taken before the update ({info.path.name}). Data entered "
            "after the update is not in the desk's database."
        )
    ctx.state["current"] = dict(previous)
    ctx.state["previous"] = None
    update_record["status"] = "undone"
    update_record["undone_at_utc"] = iso(now_utc())
    update_record["undo_method"] = method
    ctx.state["update"] = update_record
    ctx.state.setdefault("history", []).append(
        {"at_utc": iso(now_utc()), "event": "update undone", "from": current_version,
         "to": previous["version"], "method": method}
    )
    ctx.save()
    out.step(f"starting version {previous['version']}")
    healthy, reason = bring_up(ctx, previous_stack)
    if not healthy:
        raise Stop(f"Version {previous['version']} did not start properly: {reason}.",
                   SEND_DIAGNOSTICS)
    out.ok(f"The desk runs version {previous['version']} again.")
    return 0


# ====================================================================== diagnostics
def diagnostics(ctx: Context, destination: Path | None) -> int:
    from nexusctl import diagnostics as bundle

    out = ctx.out
    out.title("Collecting diagnostics")
    stack = ctx.stack()
    facts = status.collect(ctx.settings, stack, ctx.runner, version=ctx.version)
    findings = status.evaluate(facts, now_utc())
    lines: list[str] = []

    class Capture(Out):
        def _emit(self, text: str) -> None:
            lines.append(text)

    status.render(findings, Capture(), version=ctx.version)
    try:
        archive, summary = bundle.build_archive(
            settings=ctx.settings,
            stack=stack,
            runner=ctx.runner,
            version=ctx.version,
            facts=facts,
            findings=findings,
            status_text="\n".join(lines) + "\n",
            destination=destination or ctx.settings.root / "diagnostics",
        )
    except bundle.LeakRefused as exc:
        raise Stop(str(exc), "Tell the developers this message (it contains no secret).") from exc
    out.ok(f"Diagnostics written: {archive}")
    out.ok(f"Summary to paste into a message or an AI: {summary}")
    out.line("Send the .zip file to the developers. Every password, key and token was removed.")
    return 0

"""`nexus status`: collect the facts, then judge them in plain words (the judging is pure)."""

from __future__ import annotations

import json
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from nexusctl import backup as backups
from nexusctl import checks
from nexusctl.checks import FAIL, OK, WARN
from nexusctl.settings import Settings
from nexusctl.stack import LONG_RUNNING, ONE_SHOT, Runner, Stack
from nexusctl.ui import human_age, human_bytes

#: A nightly backup plus slack for a slow night or a PC switched on late.
BACKUP_MAX_AGE_HOURS = 26
SCHEDULER_LATE_SECONDS = 180
SCHEDULER_DOWN_SECONDS = 900

SEND_DIAGNOSTICS = "run `sudo nexus diagnostics` and send the file it names to the developers"

@dataclass(frozen=True)
class Finding:
    area: str
    status: str
    message: str
    todo: str | None = None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def evaluate(facts: dict, now: datetime) -> list[Finding]:
    """Every part of the desk server, healthy or not, with what to do. Pure."""

    found: list[Finding] = []
    services = facts.get("services") or {}

    # -- the parts
    if not services:
        found.append(
            Finding(
                "parts",
                FAIL,
                "The product is not running.",
                "Start it: `sudo nexus start`. If it does not start, " + SEND_DIAGNOSTICS + ".",
            )
        )
    for name, label in LONG_RUNNING.items():
        item = services.get(name)
        if not services:
            break
        if item is None or item["state"] != "running":
            found.append(
                Finding(
                    "parts",
                    FAIL,
                    f"{label}: not running.",
                    "Run `sudo nexus start`. If it stays down, " + SEND_DIAGNOSTICS + ".",
                )
            )
        elif item["health"] == "unhealthy":
            found.append(
                Finding(
                    "parts",
                    FAIL,
                    f"{label}: running but not answering.",
                    "Run `sudo nexus stop` then `sudo nexus start`. If it stays so, "
                    + SEND_DIAGNOSTICS
                    + ".",
                )
            )
        elif item["health"] == "starting":
            found.append(Finding("parts", WARN, f"{label}: still starting.", "Wait a minute."))
        else:
            found.append(Finding("parts", OK, f"{label}: running."))
    for name, label in ONE_SHOT.items():
        item = services.get(name)
        if item and item["state"] == "exited" and item.get("exit_code") not in (0, None):
            todo = SEND_DIAGNOSTICS
            if name == "migrate":
                todo = (
                    "the database is not at the version this release needs: finish the update "
                    "(`sudo nexus update <release folder>`) or go back (`sudo nexus "
                    "undo-update`)"
                )
            found.append(Finding("parts", FAIL, f"{label}: failed at the last start.", todo))

    # -- the web address
    gateway = facts.get("gateway") or {}
    if gateway:
        if gateway.get("ok"):
            found.append(
                Finding("address", OK, f"The web address answers: {gateway.get('address')}")
            )
        else:
            found.append(
                Finding(
                    "address",
                    FAIL,
                    f"The web address does not answer ({gateway.get('detail')}).",
                    "Run `sudo nexus stop` then `sudo nexus start`; if it still does not answer, "
                    + SEND_DIAGNOSTICS
                    + ".",
                )
            )

    # -- inside the product
    probe = facts.get("probe")
    if services.get("api", {}).get("state") == "running" and probe is None:
        found.append(
            Finding(
                "database",
                WARN,
                "Could not ask the application about its data.",
                "Wait a minute and run `sudo nexus status` again.",
            )
        )
    if probe:
        database = probe.get("database") or {}
        if not database.get("reachable"):
            found.append(
                Finding(
                    "database",
                    FAIL,
                    "The application cannot read the database.",
                    "Run `sudo nexus stop` then `sudo nexus start`; then " + SEND_DIAGNOSTICS + ".",
                )
            )
        elif database.get("revision") != database.get("required_revision"):
            found.append(
                Finding(
                    "database",
                    FAIL,
                    "The database is not at the version this release needs.",
                    "Finish the update or run `sudo nexus undo-update`.",
                )
            )
        else:
            found.append(Finding("database", OK, "The database is at the right version."))
        scheduler = probe.get("scheduler") or {}
        age = scheduler.get("age_seconds")
        if age is None:
            found.append(
                Finding(
                    "scheduler",
                    WARN,
                    "The data scheduler has not reported yet.",
                    "If this lasts more than 10 minutes after a start, " + SEND_DIAGNOSTICS + ".",
                )
            )
        elif age > SCHEDULER_DOWN_SECONDS:
            found.append(
                Finding(
                    "scheduler",
                    FAIL,
                    f"The data scheduler last reported {human_age(age)} ago: public data is not "
                    "being refreshed.",
                    "Run `sudo nexus stop` then `sudo nexus start`; if it persists, "
                    + SEND_DIAGNOSTICS
                    + ".",
                )
            )
        elif age > SCHEDULER_LATE_SECONDS:
            found.append(
                Finding(
                    "scheduler",
                    WARN,
                    f"The data scheduler last reported {human_age(age)} ago.",
                    "Check again in five minutes.",
                )
            )
        else:
            found.append(Finding("scheduler", OK, "The data scheduler is running."))
        sources = probe.get("sources") or []
        if not sources:
            found.append(
                Finding(
                    "sources",
                    OK,
                    "No data source is connected yet (an administrator switches them on in "
                    "Admin, Data sources).",
                )
            )
        for row in sources:
            label = row.get("dataset") or row.get("provider") or row.get("source_id")
            minutes = row.get("age_minutes")
            age_text = (
                "never received" if minutes is None else f"newest {human_age(minutes * 60)} old"
            )
            state = row.get("state")
            if state in {"current", "manual"}:
                found.append(Finding("sources", OK, f"{label}: {age_text}."))
            elif state == "never" or minutes is None:
                found.append(
                    Finding(
                        "sources",
                        WARN,
                        f"{label}: nothing received yet.",
                        "The first data arrives on the source's schedule once an administrator "
                        "has switched it on (Admin, Data sources); check again tomorrow.",
                    )
                )
            elif state == "late":
                found.append(
                    Finding(
                        "sources",
                        WARN,
                        f"{label}: late, {age_text}.",
                        "Usually the provider publishes late; check again in an hour.",
                    )
                )
            else:
                found.append(
                    Finding(
                        "sources",
                        FAIL,
                        f"{label}: stale, {age_text}. Screens show the last figures marked "
                        "stale.",
                        "Check the PC can reach the internet. If it lasts a day, "
                        + SEND_DIAGNOSTICS
                        + ".",
                    )
                )

    # -- backups
    last, failed = facts.get("last_backup"), facts.get("failed_backup")
    finished = _parse_time((last or {}).get("finished_at_utc"))
    if finished is None:
        found.append(
            Finding(
                "backup",
                FAIL,
                "No backup has succeeded yet.",
                "Run `sudo nexus backup` now and check it ends with OK.",
            )
        )
    else:
        age_hours = (now - finished).total_seconds() / 3600
        when = f"{human_age(age_hours * 3600)} ago ({finished.strftime('%Y-%m-%d %H:%M')} UTC)"
        if age_hours > BACKUP_MAX_AGE_HOURS:
            found.append(
                Finding(
                    "backup",
                    FAIL,
                    f"The last good backup was {when}.",
                    "Run `sudo nexus backup`. If it fails, " + SEND_DIAGNOSTICS + ".",
                )
            )
        else:
            found.append(Finding("backup", OK, f"Last good backup {when}."))
        for copy in (last or {}).get("copies") or []:
            if not copy.get("ok"):
                found.append(
                    Finding(
                        "backup",
                        WARN,
                        "The office/removable copy of the last backup failed: "
                        f"{copy.get('detail')}.",
                        "Check the office share or the removable disk is connected.",
                    )
                )
    if failed and (finished is None or (_parse_time(failed.get("at_utc")) or now) > finished):
        found.append(
            Finding(
                "backup",
                FAIL,
                f"The most recent backup attempt failed: {failed.get('error')}.",
                "Run `sudo nexus backup`; if it fails again, " + SEND_DIAGNOSTICS + ".",
            )
        )

    # -- disks
    for disk in facts.get("disks") or []:
        check = checks.judge_disk_space(disk["label"], disk["free"], disk["total"], 10)
        status = check.status
        message = f"The {disk['label']} has {human_bytes(disk['free'])} free."
        if check.status != OK:
            message = check.message
        found.append(Finding("disk", status, message, check.todo))
        if disk.get("missing"):
            found.append(
                Finding(
                    "disk",
                    FAIL,
                    f"The {disk['label']} folder {disk['path']} is missing.",
                    "Check the disk is connected and mounted, then run `sudo nexus status`.",
                )
            )

    # -- clock
    clock = facts.get("clock") or {}
    clock_check = checks.judge_clock(clock.get("synchronized"), clock.get("offset"))
    found.append(Finding("clock", clock_check.status, clock_check.message, clock_check.todo))
    return found


def overall(findings: list[Finding]) -> str:
    if any(item.status == FAIL for item in findings):
        return "PROBLEMS"
    if any(item.status == WARN for item in findings):
        return "WORKING, WITH WARNINGS"
    return "HEALTHY"


# ------------------------------------------------------------------ the facts
def clock_facts(runner: Runner) -> dict:
    show = runner.run(["timedatectl", "show"], timeout=10)
    synchronized: bool | None = None
    if show.ok:
        values = checks.parse_key_values(show.stdout)
        if "NTPSynchronized" in values:
            synchronized = values["NTPSynchronized"].lower() == "yes"
    offset = None
    chrony = runner.run(["chronyc", "tracking"], timeout=10)
    if chrony.ok:
        offset = checks.parse_chrony_offset(chrony.stdout)
        if synchronized is None and offset is not None:
            synchronized = "Leap status     : Normal" in chrony.stdout
    if offset is None:
        status = runner.run(["timedatectl", "timesync-status"], timeout=10)
        if status.ok:
            offset = checks.parse_timesync_offset(status.stdout)
    return {"synchronized": synchronized, "offset": offset}


def gateway_fact(settings: Settings, *, timeout: float = 5.0) -> dict:
    """GET /api/health/live through the HTTPS address, trusting the gateway's own CA."""

    address = settings.browser_address()
    name = (settings.server_names or ["localhost"])[0]
    try:
        if settings.tls == "internal" and settings.gateway_root_certificate.is_file():
            context = ssl.create_default_context(cafile=str(settings.gateway_root_certificate))
        else:
            context = ssl.create_default_context()
        with socket.create_connection(("127.0.0.1", settings.https_port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=name) as tls:
                tls.sendall(
                    f"GET /api/health/live HTTP/1.1\r\nHost: {name}\r\nConnection: close\r\n\r\n"
                    .encode("ascii")
                )
                head = tls.recv(64).decode("latin-1")
        ok = head.startswith("HTTP/1.1 200") or head.startswith("HTTP/2 200")
        detail = head.split("\r\n", 1)[0] if head else "no answer"
        return {"ok": ok, "detail": detail, "address": address}
    except (OSError, ssl.SSLError) as exc:
        return {"ok": False, "detail": exc.__class__.__name__, "address": address}


def probe_fact(stack: Stack) -> tuple[dict | None, str | None]:
    result = stack.exec("api", ["python", "-m", "eurogas_nexus.cli.desk_status"], timeout=90)
    if not result.ok:
        return None, (result.stderr or result.stdout)[-300:]
    for line in reversed(result.stdout.strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line), None
            except ValueError:
                break
    return None, "no answer"


def disk_facts(settings: Settings) -> list[dict]:
    rows = []
    for label, path in (("database disk", settings.data_dir), ("backup disk", settings.backup_dir)):
        missing = not Path(path).exists()
        free, total = checks.disk_usage(path)
        rows.append(
            {"label": label, "path": str(path), "free": free, "total": total, "missing": missing}
        )
    return rows


def collect(settings: Settings, stack: Stack, runner: Runner, *, version: str) -> dict:
    services = stack.states()
    probe, probe_error = (None, None)
    if services.get("api", {}).get("state") == "running":
        probe, probe_error = probe_fact(stack)
    last, failed = backups.last_backup(settings.backups)
    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": version,
        "services": services,
        "probe": probe,
        "probe_error": probe_error,
        "gateway": gateway_fact(settings) if services.get("gateway") else {},
        "last_backup": last,
        "failed_backup": failed,
        "disks": disk_facts(settings),
        "clock": clock_facts(runner),
    }


AREA_TITLES = {
    "parts": "Parts",
    "address": "Web address",
    "database": "Database",
    "scheduler": "Data scheduler",
    "sources": "Connected data sources (age of the newest data)",
    "backup": "Backups",
    "disk": "Disks",
    "clock": "Clock",
}


def render(findings: list[Finding], out, *, version: str) -> None:
    out.title(f"Eurogas Nexus {version}: {overall(findings)}")
    for area, title in AREA_TITLES.items():
        rows = [item for item in findings if item.area == area]
        if not rows:
            continue
        out.line(f"\n{title}")
        for item in rows:
            if item.status == OK:
                out.ok(item.message)
            elif item.status == WARN:
                out.warn(item.message, item.todo)
            else:
                out.problem(item.message, item.todo)

"""`nexus diagnostics`: one file a trader can send to the developers or give to an AI.

A ZIP archive (it opens on Windows with a double click) whose first file, ``SUMMARY.txt``, says
in plain text what is wrong; the same summary is written beside the archive so it can be pasted
into a message. Everything in it passes :class:`nexusctl.redact.Redactor`, and the archive is
not written while :meth:`Redactor.leaks` still finds anything (fail closed).

Contents: the status in words and as data, versions, the settings (``nexus.conf``, the names in
``stack.env`` with every value removed, ``state.json``), the last three days of every part's
log, this program's own log, backup records, recent errors, disk and clock facts.
"""

from __future__ import annotations

import json
import platform
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from nexusctl import TOOL_VERSION
from nexusctl.redact import Redactor
from nexusctl.settings import SECRET_NAMES, Settings, read_env
from nexusctl.stack import LONG_RUNNING, ONE_SHOT, Runner, Stack
from nexusctl.status import Finding, overall

LOG_SINCE = "72h"
LOG_TAIL_LINES = 20000
_ERROR = re.compile(
    r'(?i)("level"\s*:\s*"(error|critical)"|\b(ERROR|CRITICAL|FATAL|PANIC)\b|Traceback|exception)'
)


class LeakRefused(RuntimeError):
    """The bundle still held something secret-looking; nothing was written."""


def known_secrets(settings: Settings) -> list[str]:
    values = read_env(settings.env_path)
    secret = [values[name] for name in SECRET_NAMES if values.get(name)]
    # Anything else in stack.env that is named like a secret.
    for name, value in values.items():
        if re.search(r"PASSWORD|SECRET|TOKEN|KEY", name) and value:
            secret.append(value)
    return secret


def env_names_only(settings: Settings) -> str:
    """stack.env with every value removed: which settings exist, not what they are."""

    lines = ["# stack.env: names only, every value removed"]
    for name, value in read_env(settings.env_path).items():
        plain = name in {"POSTGRES_DB", "POSTGRES_USER"} or name.endswith("_DB_USER")
        shown = value if plain else ""
        lines.append(f"{name}={shown or '<removed>'}")
    return "\n".join(lines) + "\n"


def recent_errors(logs: dict[str, str], limit: int = 200) -> list[str]:
    rows: list[str] = []
    for service, text in logs.items():
        for line in text.splitlines():
            if _ERROR.search(line):
                rows.append(f"[{service}] {line[:600]}")
    return rows[-limit:]


def _finding_line(item: Finding) -> str:
    return f"  - {item.message}" + (f"  -> {item.todo}" if item.todo else "")


def summary_text(
    *,
    settings: Settings,
    version: str,
    findings: list[Finding],
    errors: list[str],
    now: datetime,
) -> str:
    problems = [item for item in findings if item.status == "fail"]
    warnings = [item for item in findings if item.status == "warn"]
    lines = [
        "EUROGAS NEXUS DIAGNOSTICS SUMMARY",
        "=================================",
        f"Written     : {now.strftime('%Y-%m-%d %H:%M')} UTC",
        f"Version     : {version}",
        f"Overall     : {overall(findings)}",
        "",
        "This file was written by `nexus diagnostics` on the desk's server PC. Every password,",
        "key and token was removed. To get help: send the .zip file next to this summary to the",
        "developers, or paste this summary into a message or an AI assistant and ask what to do.",
        "",
        f"PROBLEMS ({len(problems)})",
    ]
    lines += [_finding_line(item) for item in problems]
    lines += ["  (none)"] if not problems else []
    lines += ["", f"WARNINGS ({len(warnings)})"]
    lines += [_finding_line(item) for item in warnings]
    lines += ["  (none)"] if not warnings else []
    lines += ["", "WORKING"]
    lines += [f"  - {item.message}" for item in findings if item.status == "ok"]
    lines += ["", f"RECENT ERRORS IN THE LOGS (last {min(len(errors), 15)} of {len(errors)})"]
    lines += [f"  {line[:300]}" for line in errors[-15:]] or ["  (none)"]
    lines += [
        "",
        "IN THE ARCHIVE",
        "  status.txt / status.json   the full status, in words and as data",
        "  versions.txt               product, program, Docker and system versions",
        "  config/                    settings, with every secret value removed",
        "  logs/                      the last three days of each part's log",
        "  recent-errors.txt          error lines from all logs",
        "  backups.txt, disk.txt, clock.txt",
        "",
    ]
    return "\n".join(lines)


def collect_logs(stack: Stack) -> dict[str, str]:
    logs: dict[str, str] = {}
    for service in [*LONG_RUNNING, *ONE_SHOT]:
        result = stack.compose(
            [
                "logs",
                "--no-color",
                "--timestamps",
                "--since",
                LOG_SINCE,
                "--tail",
                str(LOG_TAIL_LINES),
                service,
            ],
            timeout=120,
        )
        logs[service] = (result.stdout or "") + (result.stderr or "")
    return logs


def system_facts(runner: Runner, settings: Settings) -> dict[str, str]:
    def run(argv: list[str]) -> str:
        result = runner.run(argv, timeout=30)
        return (result.stdout or "") + (result.stderr or "")

    facts = {
        "versions.txt": "\n".join(
            [
                f"nexus tool      : {TOOL_VERSION}",
                f"python          : {platform.python_version()}",
                f"system          : {platform.platform()}",
                "docker          : " + run(["docker", "version", "--format",
                                             "{{.Server.Version}}"]).strip(),
                "docker compose  : " + run(["docker", "compose", "version", "--short"]).strip(),
                "",
                "os-release:",
                run(["cat", "/etc/os-release"]),
                "images:",
                run(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}} {{.ID}}"]),
            ]
        ),
        "disk.txt": run(["df", "-h"]) + "\n" + run(["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT"]),
        "clock.txt": run(["timedatectl"]) + "\n" + run(["chronyc", "tracking"]),
        "journal.txt": run(
            [
                "journalctl",
                "--no-pager",
                "--since",
                "-3d",
                "-u",
                "eurogas-nexus.service",
                "-u",
                "eurogas-nexus-backup.service",
                "-u",
                "docker.service",
            ]
        )[-2_000_000:],
    }
    return facts


def build_archive(
    *,
    settings: Settings,
    stack: Stack | None,
    runner: Runner,
    version: str,
    facts: dict,
    findings: list[Finding],
    status_text: str,
    destination: Path,
    now: datetime | None = None,
) -> tuple[Path, Path]:
    """Write the archive and its summary; returns their paths. Raises LeakRefused."""

    now = now or datetime.now(timezone.utc)
    redactor = Redactor(known_secrets(settings))
    logs = collect_logs(stack) if stack is not None else {}
    errors = recent_errors(logs)
    members: dict[str, str] = {}
    members["SUMMARY.txt"] = summary_text(
        settings=settings, version=version, findings=findings, errors=errors, now=now
    )
    members["status.txt"] = status_text
    members["status.json"] = json.dumps(facts, indent=2, sort_keys=True, default=str)
    members.update(system_facts(runner, settings))
    members["config/nexus.conf"] = (
        settings.conf_path.read_text(encoding="utf-8") if settings.conf_path.is_file() else ""
    )
    members["config/stack.env.names-only"] = env_names_only(settings)
    members["config/state.json"] = (
        settings.state_path.read_text(encoding="utf-8") if settings.state_path.is_file() else ""
    )
    for service, text in logs.items():
        members[f"logs/{service}.log"] = text
    if settings.log_path.is_file():
        members["logs/nexus-tool.log"] = settings.log_path.read_text(
            encoding="utf-8", errors="replace"
        )[-2_000_000:]
    members["recent-errors.txt"] = "\n".join(errors) + "\n"
    backup_rows = []
    if settings.backups.is_dir():
        for path in sorted(settings.backups.glob("*.json")):
            backup_rows.append(f"--- {path.name}\n{path.read_text(encoding='utf-8')}")
    members["backups.txt"] = "\n".join(backup_rows) or "no backup records\n"

    cleaned = {name: redactor.redact(text) for name, text in members.items()}
    leaks = {name: redactor.leaks(text) for name, text in cleaned.items()}
    leaks = {name: found for name, found in leaks.items() if found}
    if leaks:
        detail = "; ".join(f"{name}: {', '.join(found)}" for name, found in sorted(leaks.items()))
        raise LeakRefused(f"diagnostics not written, secret-looking text remained in {detail}")

    destination.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    archive = destination / f"nexus-diagnostics-{stamp}.zip"
    summary = destination / f"nexus-diagnostics-{stamp}-SUMMARY.txt"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        # SUMMARY.txt first: the file a person (or an AI) reads before anything else.
        bundle.writestr("SUMMARY.txt", cleaned.pop("SUMMARY.txt"))
        for name, text in cleaned.items():
            bundle.writestr(name, text)
    summary.write_text(redactor.redact(members["SUMMARY.txt"]), encoding="utf-8")
    archive.chmod(0o644)
    return archive, summary

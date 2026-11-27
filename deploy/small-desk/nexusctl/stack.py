"""The running product: `docker compose` for one installed version, behind one small class.

Every program call goes through :class:`Runner`, so the tests replace the machine with a fake
and check the decisions without Docker.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from nexusctl.settings import PROJECT, Settings, read_env

#: The parts that run all the time, in the words `nexus status` uses for them.
LONG_RUNNING = {
    "postgres": "Database",
    "api": "Application",
    "scheduler": "Data scheduler",
    "market-events": "Live re-evaluation",
    "gateway": "Web address (HTTPS)",
}
#: Steps that run once at each start and must finish without error.
ONE_SHOT = {
    "config-check": "Settings check",
    "migrate": "Database version check",
    "reference-seed": "Gas network reference",
}
#: Everything that writes to the database (stopped for a restore, an update or an undo).
APPLICATION_SERVICES = ("gateway", "api", "scheduler", "market-events")


@dataclass
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Runner:
    """Runs programs. ``stdout_file``/``stdin_file`` stream bytes (database dumps)."""

    def run(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        stdin_file: IO[bytes] | None = None,
        stdout_file: IO[bytes] | None = None,
        timeout: float | None = None,
        passthrough: bool = False,
    ) -> Result:
        try:
            if passthrough:
                # Straight to the terminal and never captured (the one-time password).
                done = subprocess.run(list(argv), env=env, timeout=timeout, check=False)
                return Result(done.returncode)
            if stdout_file is not None or stdin_file is not None:
                done = subprocess.run(
                    list(argv),
                    env=env,
                    stdin=stdin_file,
                    stdout=stdout_file if stdout_file is not None else subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    check=False,
                )
                out = b"" if stdout_file is not None else (done.stdout or b"")
                return Result(
                    done.returncode,
                    out.decode("utf-8", "replace"),
                    (done.stderr or b"").decode("utf-8", "replace"),
                )
            done = subprocess.run(
                list(argv),
                env=env,
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            return Result(done.returncode, done.stdout or "", done.stderr or "")
        except FileNotFoundError:
            return Result(127, "", f"{argv[0]}: not found")
        except subprocess.TimeoutExpired:
            return Result(124, "", f"{argv[0]}: timed out")


def parse_ps(text: str) -> list[dict]:
    """`docker compose ps --format json`: a JSON array (older Compose) or one object a line."""

    text = (text or "").strip()
    if not text:
        return []
    if text.startswith("["):
        return list(json.loads(text))
    return [json.loads(line) for line in text.splitlines() if line.strip().startswith("{")]


def service_states(rows: list[dict]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for row in rows:
        name = row.get("Service") or row.get("service")
        if not name:
            continue
        states[name] = {
            "state": (row.get("State") or "").lower(),
            "health": (row.get("Health") or "").lower(),
            "exit_code": row.get("ExitCode"),
        }
    return states


def readiness(states: dict[str, dict]) -> tuple[bool, list[str], list[str]]:
    """(all ready, parts still starting, parts that failed). Pure."""

    waiting: list[str] = []
    failed: list[str] = []
    for name in ONE_SHOT:
        item = states.get(name)
        if item is None or item["state"] in {"created", "running", "restarting"}:
            waiting.append(name)
        elif item["state"] == "exited" and item.get("exit_code") not in (0, None):
            failed.append(name)
    for name in LONG_RUNNING:
        item = states.get(name)
        if item is None:
            waiting.append(name)
        elif item["state"] != "running":
            if item["state"] in {"created", "restarting"}:
                waiting.append(name)
            else:
                failed.append(name)
        elif item["health"] == "unhealthy":
            failed.append(name)
        elif item["health"] not in {"", "healthy"}:
            waiting.append(name)
    return (not waiting and not failed), waiting, failed


class Stack:
    def __init__(self, settings: Settings, release_dir: Path, release: dict, runner: Runner):
        self.settings = settings
        self.release_dir = release_dir
        self.release = release
        self.runner = runner

    # ------------------------------------------------------------------ the command line
    def base(self) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "--file",
            str(self.release_dir / "compose.yaml"),
            "--env-file",
            str(self.settings.env_path),
        ]

    def environ(self) -> dict[str, str]:
        env = dict(os.environ)
        settings = self.settings
        env.update(
            {
                "EUROGAS_NEXUS_API_IMAGE": self.release["api_image"],
                "EUROGAS_NEXUS_VERSION": self.release["version"],
                "NEXUS_WEB_DIR": str(self.release_dir / "web"),
                "NEXUS_DATA_DIR": str(settings.data_dir),
                "NEXUS_SITE_ADDRESSES": settings.site_addresses(),
                "NEXUS_HTTPS_PORT": str(settings.https_port),
                "NEXUS_BIND_ADDRESS": settings.bind_address,
                "NEXUS_SUBNET_PREFIX": settings.subnet_prefix,
                "NEXUS_TLS": settings.tls,
            }
        )
        return env

    def compose(
        self, args: Sequence[str], *, extra_env: dict[str, str] | None = None, **kwargs
    ) -> Result:
        env = self.environ()
        env.update(extra_env or {})
        return self.runner.run([*self.base(), *args], env=env, **kwargs)

    # ------------------------------------------------------------------ lifecycle
    def up(self, services: Sequence[str] = ()) -> Result:
        return self.compose(["up", "--detach", "--remove-orphans", *services], timeout=1800)

    def stop(self, services: Sequence[str] = ()) -> Result:
        return self.compose(["stop", *services], timeout=300)

    def remove_application(self) -> Result:
        """Stop and remove the application containers (the next `up` recreates them from
        whichever version is then current); the database keeps running."""

        names = [*APPLICATION_SERVICES, *ONE_SHOT]
        self.compose(["stop", *APPLICATION_SERVICES], timeout=300)
        return self.compose(["rm", "--force", "--stop", *names], timeout=300)

    def states(self) -> dict[str, dict]:
        result = self.compose(["ps", "--all", "--format", "json"], timeout=60)
        if not result.ok:
            return {}
        try:
            return service_states(parse_ps(result.stdout))
        except ValueError:
            return {}

    def wait_ready(self, timeout: float, *, sleep=time.sleep, clock=time.monotonic):
        """Wait until every part is up and healthy. (ready, states, failed parts)."""

        deadline = clock() + timeout
        states: dict[str, dict] = {}
        failed: list[str] = []
        while True:
            states = self.states()
            ready, _waiting, failed = readiness(states)
            if ready or failed or clock() >= deadline:
                return ready, states, failed
            sleep(3)

    def wait_database(self, timeout: float = 180, *, sleep=time.sleep, clock=time.monotonic):
        deadline = clock() + timeout
        while clock() < deadline:
            item = self.states().get("postgres") or {}
            if item.get("state") == "running" and item.get("health") == "healthy":
                return True
            sleep(2)
        return False

    # ------------------------------------------------------------------ in the containers
    def secrets(self) -> dict[str, str]:
        return read_env(self.settings.env_path)

    def psql(
        self,
        sql: str,
        *,
        database: str | None = None,
        timeout: float = 600,
        single_transaction: bool = False,
    ) -> Result:
        values = self.secrets()
        return self.compose(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "--no-psqlrc",
                "--quiet",
                "--tuples-only",
                "--no-align",
                "-v",
                "ON_ERROR_STOP=1",
                *(["--single-transaction"] if single_transaction else []),
                "-U",
                values["POSTGRES_USER"],
                "-d",
                database or "postgres",
            ],
            input_text=sql,
            timeout=timeout,
        )

    def run_once(
        self,
        service: str,
        argv: Sequence[str],
        *,
        pass_env: dict[str, str] | None = None,
        **kwargs,
    ) -> Result:
        """A one-off command in a fresh container of ``service`` (the database must be up).

        ``pass_env`` values reach the container by name only (``-e NAME``), so a secret in one
        never appears on a command line.
        """

        names: list[str] = []
        for name in pass_env or {}:
            names += ["-e", name]
        return self.compose(
            ["run", "--rm", "--no-deps", "-T", *names, service, *argv],
            extra_env=pass_env,
            **kwargs,
        )

    def exec(self, service: str, argv: Sequence[str], **kwargs) -> Result:
        return self.compose(["exec", "-T", service, *argv], **kwargs)

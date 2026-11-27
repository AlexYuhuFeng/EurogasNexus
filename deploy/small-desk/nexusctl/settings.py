"""Where things are, and the installation's own files.

An installation is one folder (``/opt/eurogas-nexus`` by default)::

    nexus.conf        settings a person may read (disks, address, backup times), no secret
    stack.env         every value the services need, secrets included; root only (0600)
    state.json        the running version, the previous one and the last update
    releases/<v>/     each installed version: release.json, compose.yaml, Caddyfile, web/
    tool/             this program (``/usr/local/bin/nexus`` points here)
    logs/nexus.log    what this program did, for the diagnostics bundle
    diagnostics/      the bundles ``nexus diagnostics`` writes

The database lives under ``NEXUS_DATA_DIR`` (the SSD) and backups under ``NEXUS_BACKUP_DIR``
(the second disk), so neither is inside this folder.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path("/opt/eurogas-nexus")
PROJECT = "eurogas-nexus"

#: Names of stack.env entries that are secrets (never printed, removed from diagnostics).
SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "EUROGAS_NEXUS_OWNER_DB_PASSWORD",
    "EUROGAS_NEXUS_APP_DB_PASSWORD",
    "NEXUS_READER_DB_PASSWORD",
    "EUROGAS_NEXUS_SECRET_KEY",
    "EUROGAS_NEXUS_SECRET_KEY_PREVIOUS",
    "EUROGAS_NEXUS_PUBLIC_API_TOKEN",
)

#: What a restore on a replaced PC cannot do without: the key that encrypts the second-factor
#: secrets and the stored data-provider keys (security/credentials.py).
RECOVERY_NAMES = ("EUROGAS_NEXUS_SECRET_KEY", "EUROGAS_NEXUS_SECRET_KEY_PREVIOUS")


def read_env(path: Path) -> dict[str, str]:
    """``NAME=value`` lines; blank lines and ``#`` comments ignored."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def write_private(path: Path, text: str, mode: int = 0o600) -> None:
    """Write atomically, readable only by the owner from the first byte."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        os.fchmod(handle, mode)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def write_env(path: Path, values: dict[str, str], header: str = "", mode: int = 0o600) -> None:
    for name, value in values.items():
        if "\n" in value or "\n" in name:
            raise ValueError(f"{name}: a value may not span lines")
    lines = [f"# {line}" for line in header.splitlines()] if header else []
    lines.extend(f"{name}={value}" for name, value in values.items())
    write_private(path, "\n".join(lines) + "\n", mode)


def generate_secrets() -> dict[str, str]:
    """Fresh secrets for a new installation. Letters and digits only (safe in a URL and SQL)."""

    return {
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "EUROGAS_NEXUS_OWNER_DB_PASSWORD": secrets.token_hex(24),
        "EUROGAS_NEXUS_APP_DB_PASSWORD": secrets.token_hex(24),
        "NEXUS_READER_DB_PASSWORD": secrets.token_hex(24),
        # A Fernet key (32 random bytes, URL-safe base64), as security/credentials.py needs.
        "EUROGAS_NEXUS_SECRET_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN": secrets.token_urlsafe(32),
    }


FIXED_STACK_VALUES = {
    "POSTGRES_DB": "eurogas",
    "POSTGRES_USER": "nexus_superuser",
    "EUROGAS_NEXUS_OWNER_DB_USER": "eurogas_owner",
    "EUROGAS_NEXUS_APP_DB_USER": "eurogas_app",
}


@dataclass
class Settings:
    root: Path = DEFAULT_ROOT
    data_dir: Path = Path("/var/lib/eurogas-nexus")
    backup_dir: Path = Path("/srv/nexus-backup")
    copy_dir: Path | None = None
    server_names: list[str] = field(default_factory=list)
    https_port: int = 443
    bind_address: str = "0.0.0.0"
    subnet_prefix: str = "172.30.58"
    tls: str = "internal"
    keep_daily: int = 14
    keep_weekly: int = 8
    keep_monthly: int = 12
    backup_time: str = "01:30"
    copy_keys: bool = False
    health_timeout_seconds: int = 600

    # ---------------------------------------------------------------- the files
    @property
    def conf_path(self) -> Path:
        return self.root / "nexus.conf"

    @property
    def env_path(self) -> Path:
        return self.root / "stack.env"

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def log_path(self) -> Path:
        return self.root / "logs" / "nexus.log"

    @property
    def releases_dir(self) -> Path:
        return self.root / "releases"

    @property
    def backups(self) -> Path:
        return self.backup_dir / "nexus-backups"

    @property
    def gateway_root_certificate(self) -> Path:
        return self.data_dir / "gateway" / "caddy" / "pki" / "authorities" / "local" / "root.crt"

    def site_addresses(self) -> str:
        names = self.server_names or ["localhost"]
        return ", ".join(f"https://{name}:443" for name in names)

    def browser_address(self) -> str:
        name = (self.server_names or ["localhost"])[0]
        return f"https://{name}" + ("" if self.https_port == 443 else f":{self.https_port}")

    # ---------------------------------------------------------------- nexus.conf
    def to_conf(self) -> dict[str, str]:
        return {
            "NEXUS_DATA_DIR": str(self.data_dir),
            "NEXUS_BACKUP_DIR": str(self.backup_dir),
            "NEXUS_BACKUP_COPY_DIR": str(self.copy_dir or ""),
            "NEXUS_SERVER_NAMES": ",".join(self.server_names),
            "NEXUS_HTTPS_PORT": str(self.https_port),
            "NEXUS_BIND_ADDRESS": self.bind_address,
            "NEXUS_SUBNET_PREFIX": self.subnet_prefix,
            "NEXUS_TLS": self.tls,
            "NEXUS_KEEP_DAILY": str(self.keep_daily),
            "NEXUS_KEEP_WEEKLY": str(self.keep_weekly),
            "NEXUS_KEEP_MONTHLY": str(self.keep_monthly),
            "NEXUS_BACKUP_TIME": self.backup_time,
            "NEXUS_COPY_KEYS": "yes" if self.copy_keys else "no",
            "NEXUS_HEALTH_TIMEOUT": str(self.health_timeout_seconds),
        }

    def save(self) -> None:
        write_env(
            self.conf_path,
            self.to_conf(),
            header="Eurogas Nexus small-desk settings (no secrets here; they are in stack.env).\n"
            "Change with care, then run: sudo nexus stop && sudo nexus start",
            mode=0o644,
        )

    @classmethod
    def load(cls, root: Path) -> Settings:
        values = read_env(root / "nexus.conf")
        if not values:
            raise FileNotFoundError(root / "nexus.conf")
        copy = values.get("NEXUS_BACKUP_COPY_DIR") or ""
        return cls(
            root=root,
            data_dir=Path(values["NEXUS_DATA_DIR"]),
            backup_dir=Path(values["NEXUS_BACKUP_DIR"]),
            copy_dir=Path(copy) if copy else None,
            server_names=[n for n in values.get("NEXUS_SERVER_NAMES", "").split(",") if n],
            https_port=int(values.get("NEXUS_HTTPS_PORT") or 443),
            bind_address=values.get("NEXUS_BIND_ADDRESS") or "0.0.0.0",
            subnet_prefix=values.get("NEXUS_SUBNET_PREFIX") or "172.30.58",
            tls=values.get("NEXUS_TLS") or "internal",
            keep_daily=int(values.get("NEXUS_KEEP_DAILY") or 14),
            keep_weekly=int(values.get("NEXUS_KEEP_WEEKLY") or 8),
            keep_monthly=int(values.get("NEXUS_KEEP_MONTHLY") or 12),
            backup_time=values.get("NEXUS_BACKUP_TIME") or "01:30",
            copy_keys=(values.get("NEXUS_COPY_KEYS") or "no").lower() in {"yes", "true", "1"},
            health_timeout_seconds=int(values.get("NEXUS_HEALTH_TIMEOUT") or 600),
        )


# -------------------------------------------------------------------- state.json
def load_state(settings: Settings) -> dict:
    if not settings.state_path.is_file():
        return {}
    return json.loads(settings.state_path.read_text(encoding="utf-8"))


def save_state(settings: Settings, state: dict) -> None:
    write_private(settings.state_path, json.dumps(state, indent=2, sort_keys=True) + "\n", 0o644)

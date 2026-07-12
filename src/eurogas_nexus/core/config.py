"""Import-safe runtime configuration."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

ApiProfile = Literal["development", "internal", "release"]
RuntimeEnvironment = Literal["development", "test", "trial", "release"]
DB_DSN_ENV_VARS = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
)


class DbRuntimeConfig(BaseModel):
    """DB runtime options kept local to core to preserve import boundaries."""

    dsn: str | None = None
    echo: bool = False
    pool_pre_ping: bool = True


def parse_env_bool(value: str | None, *, default: bool) -> bool:
    """Parse explicit boolean environment values."""

    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def resolve_db_dsn_from_env() -> str | None:
    """Resolve DB DSN for settings without importing DB modules."""

    for env_var in DB_DSN_ENV_VARS:
        raw_dsn = os.getenv(env_var)
        dsn = raw_dsn.strip() if raw_dsn else None
        if dsn:
            return dsn

    return None


class Settings(BaseModel):
    """Settings loaded from environment variables without side effects."""

    app_name: str = "Eurogas Nexus"
    app_version: str = Field(default="0.5.0")
    environment: RuntimeEnvironment = "development"
    api_profile: ApiProfile = "development"
    db: DbRuntimeConfig = Field(default_factory=DbRuntimeConfig)

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from process environment variables."""

        return cls(
            app_version=os.getenv("EUROGAS_NEXUS_VERSION", "0.5.0"),
            environment=os.getenv("EUROGAS_NEXUS_ENV", "development"),
            api_profile=os.getenv("EUROGAS_NEXUS_API_PROFILE", "development"),
            db=DbRuntimeConfig(
                dsn=resolve_db_dsn_from_env(),
                echo=parse_env_bool(os.getenv("EUROGAS_NEXUS_DB_ECHO"), default=False),
                pool_pre_ping=parse_env_bool(
                    os.getenv("EUROGAS_NEXUS_DB_POOL_PRE_PING"),
                    default=True,
                ),
            ),
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()

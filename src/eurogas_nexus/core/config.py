"""Import-safe runtime configuration."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

ApiProfile = Literal["development", "internal", "release"]
RuntimeEnvironment = Literal["development", "test", "trial", "release"]


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


class Settings(BaseModel):
    """Settings loaded from environment variables without side effects."""

    app_name: str = "Eurogas Nexus"
    app_version: str = Field(default="0.1.0")
    environment: RuntimeEnvironment = "development"
    api_profile: ApiProfile = "development"
    db: DbRuntimeConfig = Field(default_factory=DbRuntimeConfig)

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from process environment variables."""

        raw_dsn = os.getenv("EUROGAS_NEXUS_DB_DSN")
        dsn = raw_dsn.strip() if raw_dsn else None
        if dsn == "":
            dsn = None

        return cls(
            app_version=os.getenv("EUROGAS_NEXUS_VERSION", "0.1.0"),
            environment=os.getenv("EUROGAS_NEXUS_ENV", "development"),
            api_profile=os.getenv("EUROGAS_NEXUS_API_PROFILE", "development"),
            db=DbRuntimeConfig(
                dsn=dsn,
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

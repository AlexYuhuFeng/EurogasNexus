"""Database configuration primitives (import-safe)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, model_validator

if TYPE_CHECKING:
    from eurogas_nexus.core.config import DbRuntimeConfig


class DatabaseSettings(BaseModel):
    """Canonical runtime database settings for DB module consumers."""

    dsn: str | None = None
    echo: bool = False
    pool_pre_ping: bool = True

    @model_validator(mode="after")
    def _normalize_blank_dsn(self) -> DatabaseSettings:
        if self.dsn is not None and self.dsn.strip() == "":
            object.__setattr__(self, "dsn", None)
        return self

    @classmethod
    def from_core_config(cls, config: DbRuntimeConfig) -> DatabaseSettings:
        """Build canonical settings from import-safe core config."""
        return cls(
            dsn=config.dsn,
            echo=config.echo,
            pool_pre_ping=config.pool_pre_ping,
        )

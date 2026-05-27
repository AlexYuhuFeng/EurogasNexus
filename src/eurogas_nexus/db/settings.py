"""Database configuration primitives (import-safe)."""

from pydantic import BaseModel


class DatabaseSettings(BaseModel):
    """Runtime database settings loaded by DB module users."""

    dsn: str | None = None
    echo: bool = False
    pool_pre_ping: bool = True

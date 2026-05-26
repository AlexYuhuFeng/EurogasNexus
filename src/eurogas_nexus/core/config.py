"""Import-safe runtime configuration."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

ApiProfile = Literal["development", "release"]
RuntimeEnvironment = Literal["development", "test", "trial", "release"]


class Settings(BaseModel):
    """Settings loaded from environment variables without side effects."""

    app_name: str = "Eurogas Nexus"
    app_version: str = Field(default="0.1.0")
    environment: RuntimeEnvironment = "development"
    api_profile: ApiProfile = "development"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from process environment variables."""

        return cls(
            app_version=os.getenv("EUROGAS_NEXUS_VERSION", "0.1.0"),
            environment=os.getenv("EUROGAS_NEXUS_ENV", "development"),
            api_profile=os.getenv("EUROGAS_NEXUS_API_PROFILE", "development"),
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()

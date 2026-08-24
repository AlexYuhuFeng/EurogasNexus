"""Import-safe runtime configuration."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ApiProfile = Literal["development", "internal", "release"]
RuntimeEnvironment = Literal["development", "test", "trial", "release"]
DeploymentPosture = Literal["private_network_preview", "security_accepted"]
DEPLOYMENT_POSTURE_ENV = "EUROGAS_NEXUS_DEPLOYMENT_POSTURE"
SECURITY_ACCEPTANCE_EVIDENCE_ENV = "EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE"
DB_DSN_ENV_VARS = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
)


class DeploymentConfig(BaseModel):
    """Deployment network posture and its operator evidence."""

    posture: DeploymentPosture = "private_network_preview"
    security_acceptance_evidence_path: str | None = None


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
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    llm_external_provider_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from process environment variables."""

        environment = os.getenv("EUROGAS_NEXUS_ENV", "development")
        # Fail-closed: trial/release environments can never enable external
        # LLM providers, even with an explicit env override (P0-2).
        if environment in {"trial", "release"}:
            llm_external_provider_enabled = False
        else:
            llm_external_provider_enabled = parse_env_bool(
                os.getenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED"),
                default=True,
            )
        return cls(
            app_version=os.getenv("EUROGAS_NEXUS_VERSION", "0.5.0"),
            environment=environment,
            api_profile=os.getenv("EUROGAS_NEXUS_API_PROFILE", "development"),
            db=DbRuntimeConfig(
                dsn=resolve_db_dsn_from_env(),
                echo=parse_env_bool(os.getenv("EUROGAS_NEXUS_DB_ECHO"), default=False),
                pool_pre_ping=parse_env_bool(
                    os.getenv("EUROGAS_NEXUS_DB_POOL_PRE_PING"),
                    default=True,
                ),
            ),
            deployment=DeploymentConfig(
                posture=os.getenv(
                    DEPLOYMENT_POSTURE_ENV, "private_network_preview"
                ),
                security_acceptance_evidence_path=os.getenv(
                    SECURITY_ACCEPTANCE_EVIDENCE_ENV
                ),
            ),
            llm_external_provider_enabled=llm_external_provider_enabled,
        )


def public_network_deployment_allowed(
    settings: Settings | None = None,
) -> tuple[bool, str]:
    """Return whether a public-network server deployment may be considered.

    ``security_accepted`` alone is not enough: an operator must also point at
    an existing security-acceptance evidence file. Until both are present the
    deployment remains private-network/VPN-only (fail-closed).
    """

    resolved = settings or get_settings()
    posture = resolved.deployment.posture
    if posture != "security_accepted":
        return False, (
            f"deployment_posture={posture!r}; expected 'security_accepted'"
        )
    evidence_path = (
        resolved.deployment.security_acceptance_evidence_path or ""
    ).strip()
    if not evidence_path:
        return False, "security-acceptance evidence path is not configured"
    if not Path(evidence_path).is_file():
        return False, f"security-acceptance evidence file not found: {evidence_path}"
    return True, f"security_accepted evidence file present: {evidence_path}"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()

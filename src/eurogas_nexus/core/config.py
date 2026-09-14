"""Import-safe runtime configuration."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from eurogas_nexus.version import APPLICATION_VERSION, DEFAULT_RELEASE_CHANNEL

ApiProfile = Literal["development", "internal", "release"]
RuntimeEnvironment = Literal["development", "test", "trial", "release"]
DeploymentPosture = Literal["private_network_preview", "security_accepted"]
ReleaseChannel = Literal["preview", "rc", "stable"]
DEPLOYMENT_POSTURE_ENV = "EUROGAS_NEXUS_DEPLOYMENT_POSTURE"
SECURITY_ACCEPTANCE_EVIDENCE_ENV = "EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE"
DB_DSN_ENV_VARS = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
)
DEV_LOGIN_USERNAME_ENV = "EUROGAS_NEXUS_DEV_LOGIN_USERNAME"
DEV_LOGIN_PASSWORD_ENV = "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD"
RESEARCH_ARTIFACT_ROOT_ENV = "EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT"
# Repository default for the CR-14 research artifact root. ``data/snapshots/``
# already exists as a git-ignored generated-output directory (see .gitignore and
# docs/policies/DATA_POLICY.md: local files may hold generated reports and
# snapshots). PostgreSQL remains the runtime source of truth for ingested data;
# artifacts are derived research output, never a fallback source of business
# data.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESEARCH_ARTIFACT_ROOT = REPOSITORY_ROOT / "data" / "snapshots"


class DeploymentConfig(BaseModel):
    """Deployment network posture and its operator evidence."""

    posture: DeploymentPosture = "private_network_preview"
    security_acceptance_evidence_path: str | None = None


class ResearchArtifactConfig(BaseModel):
    """Server-side storage root for materialized research dataset artifacts.

    CR14-ARTIFACT-001 storage decision: dataset artifacts are written beneath one
    operator-configurable root (``EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT``) that
    defaults to the git-ignored ``data/snapshots/`` directory of the deployment
    checkout. Rationale:

    - DATA_POLICY permits local files for generated reports and snapshots while
      PostgreSQL stays the source of truth for ingested runtime data;
    - that directory is already ignored by Git, so restricted or licensed
      research rows can never be committed by accident;
    - a single root keeps the persisted snapshot ``artifact_ref`` a short
      relative reference instead of an absolute server path that would leak
      host layout.

    Only a filesystem path is configured here; no credential or secret is read.
    An unusable root fails closed at write time rather than silently dropping an
    artifact.
    """

    root: str = str(DEFAULT_RESEARCH_ARTIFACT_ROOT)


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
    app_version: str = Field(default=APPLICATION_VERSION)
    release_channel: ReleaseChannel = Field(default=DEFAULT_RELEASE_CHANNEL)
    build_git_sha: str | None = None
    build_git_ref: str | None = None
    build_run_id: str | None = None
    build_timestamp: str | None = None
    environment: RuntimeEnvironment = "development"
    api_profile: ApiProfile = "development"
    db: DbRuntimeConfig = Field(default_factory=DbRuntimeConfig)
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    research_artifacts: ResearchArtifactConfig = Field(default_factory=ResearchArtifactConfig)
    llm_external_provider_enabled: bool = True
    # Development-only credential login (mounted by the development route
    # profile only). Both must be set; the value is never defaulted in source.
    dev_login_username: str | None = None
    dev_login_password: str | None = None

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
            app_version=os.getenv("EUROGAS_NEXUS_VERSION", APPLICATION_VERSION),
            release_channel=os.getenv("EUROGAS_NEXUS_RELEASE_CHANNEL", DEFAULT_RELEASE_CHANNEL),
            build_git_sha=(os.getenv("EUROGAS_NEXUS_BUILD_GIT_SHA") or "").strip() or None,
            build_git_ref=(os.getenv("EUROGAS_NEXUS_BUILD_GIT_REF") or "").strip() or None,
            build_run_id=(os.getenv("EUROGAS_NEXUS_BUILD_RUN_ID") or "").strip() or None,
            build_timestamp=(os.getenv("EUROGAS_NEXUS_BUILD_TIMESTAMP") or "").strip() or None,
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
                posture=os.getenv(DEPLOYMENT_POSTURE_ENV, "private_network_preview"),
                security_acceptance_evidence_path=os.getenv(SECURITY_ACCEPTANCE_EVIDENCE_ENV),
            ),
            research_artifacts=ResearchArtifactConfig(
                root=str(resolve_research_artifact_root()),
            ),
            llm_external_provider_enabled=llm_external_provider_enabled,
            dev_login_username=(os.getenv(DEV_LOGIN_USERNAME_ENV) or "").strip() or None,
            dev_login_password=(os.getenv(DEV_LOGIN_PASSWORD_ENV) or "").strip() or None,
        )


def resolve_research_artifact_root() -> Path:
    """Return the configured research artifact root, else the documented default.

    Read from the process environment on every call so an operator can relocate
    artifact storage (or a test can redirect it) without a code change. The
    returned path is not created or validated here: the artifact writer fails
    closed with a structured error when the root cannot be used.
    """

    raw = (os.getenv(RESEARCH_ARTIFACT_ROOT_ENV) or "").strip()
    if not raw:
        return DEFAULT_RESEARCH_ARTIFACT_ROOT
    return Path(raw)


def resolve_dev_login_credentials_from_env() -> tuple[str, str] | None:
    """Return the development-only login credentials, or ``None`` when unset.

    Both ``EUROGAS_NEXUS_DEV_LOGIN_USERNAME`` and
    ``EUROGAS_NEXUS_DEV_LOGIN_PASSWORD`` must be non-blank. The development
    credential login is disabled (fail-closed) whenever either is missing, and
    it is only ever mounted by the development route profile. No credential
    value is defaulted in source.

    Settings are read from the current process environment on every call so an
    operator can rotate the development credential without a code change.
    """

    settings = Settings.from_env()
    username = settings.dev_login_username or ""
    password = settings.dev_login_password or ""
    if not username or not password:
        return None
    return username, password


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
        return False, (f"deployment_posture={posture!r}; expected 'security_accepted'")
    evidence_path = (resolved.deployment.security_acceptance_evidence_path or "").strip()
    if not evidence_path:
        return False, "security-acceptance evidence path is not configured"
    if not Path(evidence_path).is_file():
        return False, f"security-acceptance evidence file not found: {evidence_path}"
    return True, f"security_accepted evidence file present: {evidence_path}"


def simulated_sources_allowed() -> bool:
    """Return whether simulated market/price sources are permitted.

    Trial and release environments are fail-closed: simulated sources are only
    for local development and explicit demonstration worktrees. An operator
    cannot silently ship demo data in a delivered release environment.
    """

    environment = os.getenv("EUROGAS_NEXUS_ENV", "development").strip().lower()
    if environment in {"trial", "release"}:
        return False
    return parse_env_bool(
        os.getenv("EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES"),
        default=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()

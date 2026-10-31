"""Preflight validation for a deployment's environment.

The configuration contract (``eurogas_nexus.core.config_contract``) declares what
the product reads; this module decides whether the values an operator actually
supplied can serve. It exists because the failure mode without it is silence: a
missing credential-encryption key raises only when the first provider credential
is written, a partially configured OIDC block answers 503 only when a user clicks
sign-in, and a mistyped variable name is simply ignored.

Every finding names the variable, what is wrong, and what to do about it. The
caller decides what to do with severities; :func:`main` exits non-zero when any
finding is an error.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from eurogas_nexus.core.config_contract import (
    CONFIG_VARS,
    CONFIG_VARS_BY_NAME,
    OPERATOR_CONFIG_VARS,
)

Severity = Literal["error", "warning", "info"]

#: Placeholder values that must never reach a deployment. ``.env.example`` ships
#: them, so copying the template without editing it would otherwise "configure" a
#: deployment with a known value.
PLACEHOLDER_VALUES = frozenset(
    {
        "changeme",
        "change-me",
        "secret",
        "password",
        "test",
        "example",
        "your-token-here",
        "todo",
        "xxx",
    }
)

#: Prefixes that mark a variable as this product's configuration. An unset or
#: unrecognised name under these prefixes is far more likely a typo than an
#: intentional extra, so it is reported.
CONFIG_PREFIXES = ("EUROGAS_NEXUS_", "EUROGAS_")

#: Variables read by a component outside this repository's Python. They are still
#: expected in the deployment environment, but the Python side never reads them.
EXTERNALLY_READ = {var.name: var.external_reader for var in CONFIG_VARS if var.external_reader}

MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class Finding:
    """One preflight result."""

    severity: Severity
    code: str
    variable: str | None
    message: str
    remedy: str = ""

    def render(self) -> str:
        prefix = {"error": "ERROR", "warning": "WARN ", "info": "info "}[self.severity]
        location = f" {self.variable}" if self.variable else ""
        line = f"{prefix} [{self.code}]{location}: {self.message}"
        if self.remedy:
            line += f"\n        fix: {self.remedy}"
        return line


@dataclass
class PreflightReport:
    """All findings for one environment, plus the resolved context."""

    environment: str
    api_profile: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _value(environ: Mapping[str, str], name: str) -> str:
    return (environ.get(name) or "").strip()


def _is_production(environment: str, api_profile: str) -> bool:
    return environment in {"trial", "release"} or api_profile in {"internal", "release"}


def _closest_declared_name(name: str, declared: tuple[str, ...]) -> str | None:
    """Return the declared variable name most similar to ``name``, if close enough.

    A typo is the common case for an unrecognised variable, and naming the
    intended variable turns a puzzling report into a one-character fix. The
    threshold is deliberately conservative so an unrelated extra variable does not
    attract a misleading suggestion.
    """

    import difflib

    matches = difflib.get_close_matches(name, declared, n=1, cutoff=0.82)
    return matches[0] if matches else None


def _check_unknown_variables(environ: Mapping[str, str]) -> list[Finding]:
    """Report ``EUROGAS_*`` names the contract does not declare.

    This is the typo net: ``EUROGAS_NEXUS_OIDC_ISUER`` or
    ``EUROGAS_NEXUS_SECRET_KEYS`` would otherwise be accepted in silence while the
    intended setting stayed unset. It also catches the inverse mistake of copying a
    flag the product has since removed.
    """

    declared = tuple(CONFIG_VARS_BY_NAME)
    findings: list[Finding] = []
    for name in sorted(environ):
        if not name.startswith(CONFIG_PREFIXES):
            continue
        if name in CONFIG_VARS_BY_NAME:
            continue
        suggestion = _closest_declared_name(name, declared)
        if suggestion:
            remedy = f"did you mean {suggestion}? Nothing reads the name as written"
        else:
            remedy = (
                "nothing reads this name; remove it, or check it against "
                "deploy/runtime/env.server.example"
            )
        findings.append(
            Finding(
                severity="error",
                code="unknown_variable",
                variable=name,
                message=("set but not part of the configuration contract, so it has no effect"),
                remedy=remedy,
            )
        )
    return findings


def _resolved(name: str, environ: Mapping[str, str]) -> str:
    """Return the value supplied for a variable, or for any of its accepted aliases.

    Consulting the contract's declared aliases keeps this check in step with the
    readers: ``RUNTIME_STORE_DATABASE_URL`` is satisfied by ``DATABASE_URL`` or
    ``EUROGAS_NEXUS_DB_DSN``, and reporting it "missing" while an accepted alias is
    set would send an operator to fix a variable that is not the problem.
    """

    value = _value(environ, name)
    if value:
        return value
    declared = CONFIG_VARS_BY_NAME.get(name)
    for alias in declared.aliases if declared else ():
        value = _value(environ, alias)
        if value:
            return value
    return ""


def _check_required(
    environ: Mapping[str, str], *, environment: str, api_profile: str
) -> list[Finding]:
    """Report required-but-missing variables for the resolved deployment shape."""

    findings: list[Finding] = []
    production = _is_production(environment, api_profile)

    required: list[tuple[str, str, str]] = [
        (
            "EUROGAS_NEXUS_PUBLIC_API_TOKEN",
            "every route profile identifies its callers; without it the API "
            "refuses protected routes with 503",
            "set the deployment token, or enable EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS "
            "if this deployment really does trust its network",
        ),
        (
            "EUROGAS_NEXUS_SECRET_KEY",
            "provider credentials are encrypted with it and identity digests are keyed by it",
            'generate one with: python -c "import base64,os;'
            'print(base64.urlsafe_b64encode(os.urandom(32)).decode())"',
        ),
    ]

    # A DB-less development session is legitimate; a served production
    # deployment without a runtime store is not.
    if production or api_profile != "development":
        required.append(
            (
                "RUNTIME_STORE_DATABASE_URL",
                "PostgreSQL is the runtime source of truth; without it every "
                "DB-backed read reports a diagnostic state instead of data",
                "set RUNTIME_STORE_DATABASE_URL (DATABASE_URL and "
                "EUROGAS_NEXUS_DB_DSN are accepted aliases)",
            )
        )

    if api_profile == "internal":
        required.append(
            (
                "EUROGAS_NEXUS_INTERNAL_API_TOKEN",
                "the internal route profile is mounted but has no token to check",
                "set the internal API token, or stop mounting the internal profile",
            )
        )

    for name, why, remedy in required:
        if not _resolved(name, environ):
            findings.append(
                Finding(
                    severity="error",
                    code="missing_required",
                    variable=name,
                    message=f"not set: {why}",
                    remedy=remedy,
                )
            )
    return findings


def _check_secret_key(environ: Mapping[str, str]) -> list[Finding]:
    """Validate the credential-encryption key: base64 32 bytes, not a placeholder."""

    findings: list[Finding] = []
    raw = _value(environ, "EUROGAS_NEXUS_SECRET_KEY")
    if not raw:
        return findings

    if raw.lower() in PLACEHOLDER_VALUES:
        findings.append(
            Finding(
                severity="error",
                code="placeholder_secret",
                variable="EUROGAS_NEXUS_SECRET_KEY",
                message="the value is a placeholder, not a key",
                remedy="generate a random 32-byte urlsafe-base64 key",
            )
        )
        return findings

    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception:
        decoded = b""

    if len(decoded) != 32:
        # The code hashes any other value into a key, so this is a warning about a
        # weak or mistyped value rather than a hard failure.
        findings.append(
            Finding(
                severity="warning",
                code="secret_key_not_fernet",
                variable="EUROGAS_NEXUS_SECRET_KEY",
                message=(
                    "not a 32-byte urlsafe-base64 Fernet key; the product falls back "
                    "to hashing the raw string, which cannot be rotated deliberately"
                ),
                remedy=(
                    'generate one with: python -c "import base64,os;'
                    'print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
                ),
            )
        )
    if len(raw) < MIN_SECRET_LENGTH:
        findings.append(
            Finding(
                severity="warning",
                code="secret_key_short",
                variable="EUROGAS_NEXUS_SECRET_KEY",
                message=f"shorter than {MIN_SECRET_LENGTH} characters",
                remedy="use a generated 44-character Fernet key",
            )
        )
    return findings


def _check_secret_quality(environ: Mapping[str, str]) -> list[Finding]:
    """Flag placeholder values in any declared secret.

    ``EUROGAS_NEXUS_SECRET_KEY`` is excluded: it has its own check that says
    whether the value is unusable as a key rather than merely fake.
    """

    findings: list[Finding] = []
    for var in CONFIG_VARS:
        if var.sensitivity != "secret":
            continue
        if var.name == "EUROGAS_NEXUS_SECRET_KEY":
            continue
        raw = _value(environ, var.name)
        if raw and raw.lower() in PLACEHOLDER_VALUES:
            findings.append(
                Finding(
                    severity="error",
                    code="placeholder_secret",
                    variable=var.name,
                    message="the value is a placeholder, not a credential",
                    remedy="inject the real value at deploy time",
                )
            )
    return findings


def _check_production_guards(
    environ: Mapping[str, str], *, environment: str, api_profile: str
) -> list[Finding]:
    """Refuse development-only switches in a production deployment."""

    if not _is_production(environment, api_profile):
        return []

    findings: list[Finding] = []
    guards = (
        (
            "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS",
            "anonymous callers would be accepted in a production deployment",
        ),
        (
            "EUROGAS_NEXUS_OIDC_ALLOW_HTTP",
            "OIDC discovery and token exchange would cross cleartext",
        ),
        (
            "EUROGAS_NEXUS_DEV_LOGIN_USERNAME",
            "the development credential login is not mounted in production profiles, "
            "so this only leaks a credential into the environment",
        ),
        (
            "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
            "the development credential login is not mounted in production profiles, "
            "so this only leaks a credential into the environment",
        ),
        (
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED",
            "a fixture seed must never be permitted against a production store",
        ),
        (
            "EUROGAS_NEXUS_DB_ECHO",
            "echoed SQL can carry business values into the log",
        ),
    )
    truthy = {"1", "true", "yes", "on"}
    for name, why in guards:
        raw = _value(environ, name).lower()
        enabled = raw in truthy if name != "EUROGAS_NEXUS_DEV_LOGIN_USERNAME" else bool(raw)
        if name == "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD":
            enabled = bool(raw)
        if enabled:
            findings.append(
                Finding(
                    severity="error",
                    code="dev_setting_in_production",
                    variable=name,
                    message=f"enabled in a production deployment: {why}",
                    remedy="remove it from the deployment environment",
                )
            )
    return findings


def _check_llm_egress(
    environ: Mapping[str, str], *, environment: str, api_profile: str
) -> list[Finding]:
    """Warn when external LLM egress is permitted.

    Trial and release force the provider off, so this can only fire for
    development and test. It is reported anyway because the flag controls whether
    request payloads leave the deployment boundary.
    """

    if _is_production(environment, api_profile):
        return []
    raw = _value(environ, "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED").lower()
    if raw in {"1", "true", "yes", "on"}:
        return [
            Finding(
                severity="warning",
                code="llm_egress_enabled",
                variable="EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED",
                message=(
                    "external LLM calls are permitted in this environment, so the "
                    "request payload leaves the deployment boundary"
                ),
                remedy=(
                    "set it to 0 unless the payloads are safe to send to the provider; "
                    "trial and release force it off regardless"
                ),
            )
        ]
    return []


def _check_gateway_auth(environ: Mapping[str, str]) -> list[Finding]:
    """Gateway SSO trusts headers, so it starts only with a strong shared secret."""

    from eurogas_nexus.security.gateway_auth import GatewayConfig

    try:
        config = GatewayConfig.from_env(environ)
    except ValueError as exc:
        return [
            Finding(
                severity="error",
                code="gateway_trusted_proxies_invalid",
                variable="EUROGAS_NEXUS_GATEWAY_TRUSTED_PROXIES",
                message=str(exc),
                remedy="list the gateway's addresses as comma-separated CIDRs",
            )
        ]
    findings = [
        Finding(
            severity="error",
            code="gateway_secret_weak",
            variable="EUROGAS_NEXUS_GATEWAY_SECRET",
            message=problem,
            remedy="generate a random secret and configure the gateway to send it",
        )
        for problem in config.problems()
    ]
    if config.enabled and not config.trusted_proxies:
        findings.append(
            Finding(
                severity="warning",
                code="gateway_trusted_proxies_unset",
                variable="EUROGAS_NEXUS_GATEWAY_TRUSTED_PROXIES",
                message="any network peer holding the secret can assert identities",
                remedy="restrict to the gateway's addresses as seen by the API",
            )
        )
    return findings


def _check_oidc(environ: Mapping[str, str]) -> list[Finding]:
    """A half-configured OIDC block answers 503 only when a user tries to sign in."""

    names = (
        "EUROGAS_NEXUS_OIDC_ISSUER",
        "EUROGAS_NEXUS_OIDC_CLIENT_ID",
        "EUROGAS_NEXUS_OIDC_REDIRECT_URI",
    )
    configured = [name for name in names if _value(environ, name)]
    if not configured:
        return []
    missing = [name for name in names if name not in configured]
    if not missing:
        provisioning = _value(environ, "EUROGAS_NEXUS_OIDC_PROVISIONING_MODE").lower()
        if provisioning and provisioning not in {"preprovisioned", "approved_domain", "directory"}:
            return [
                Finding(
                    severity="error",
                    code="oidc_provisioning_mode_invalid",
                    variable="EUROGAS_NEXUS_OIDC_PROVISIONING_MODE",
                    message=(
                        f"unknown mode {provisioning!r}; expected preprovisioned, approved_domain "
                        "or directory"
                    ),
                    remedy="set a supported mode; the reader falls back silently otherwise",
                )
            ]
        return []
    return [
        Finding(
            severity="error",
            code="oidc_partially_configured",
            variable=", ".join(missing),
            message=(
                "interactive SSO is partially configured, so sign-in fails with "
                "oidc_not_configured at the moment a user tries it"
            ),
            remedy=f"set the missing value(s): {', '.join(missing)}",
        )
    ]


def _check_proxy_topology(
    environ: Mapping[str, str], *, environment: str, api_profile: str
) -> list[Finding]:
    """Warn when a production deployment has not declared its trusted proxy hop.

    The shipped topology terminates TLS in the gateway and proxies to the API over
    a container network. uvicorn trusts forwarded headers only from
    ``FORWARDED_ALLOW_IPS`` (default ``127.0.0.1,::1``), which excludes that hop, so
    without this the API sees every request as plain HTTP.
    """

    if not _is_production(environment, api_profile):
        return []
    if _value(environ, "FORWARDED_ALLOW_IPS"):
        return []
    return [
        Finding(
            severity="warning",
            code="proxy_hop_not_trusted",
            variable="FORWARDED_ALLOW_IPS",
            message=(
                "a production deployment is served but no trusted proxy hop is "
                "declared; the API will observe every request as plain http, which "
                "suppresses the Secure cookie attribute"
            ),
            remedy=(
                "set FORWARDED_ALLOW_IPS to the proxy network (for example "
                "172.16.0.0/12) when TLS is terminated in front of the API"
            ),
        )
    ]


def _check_dev_browser_origin(
    environ: Mapping[str, str], *, environment: str, api_profile: str
) -> list[Finding]:
    """Warn when a development browser session will have its mutations refused.

    The shipped topology differs between development and production, and the origin
    guard treats them differently on purpose:

    * production serves the web client and the API from one host, so the guard
      derives the expected origin from ``Host`` and accepts it;
    * development serves the client from a Vite dev server on its own port, so the
      browser's ``Origin`` names that port while the backend sees the API's, and the
      derived origin does not match.

    ``EUROGAS_NEXUS_CORS_ORIGINS`` is the declared remedy. Without it every
    cookie-authenticated mutation is refused with ``origin_not_allowed``, which the
    browser reports as a console error whose text does not name the cause. The CI
    browser-acceptance job sets it; a developer following the deployment documents
    does not, and then meets 403s on the Decision workspace's optimiser.
    """

    if _is_production(environment, api_profile):
        return []
    # Only the development route profile mounts a browser sign-in at all.
    if api_profile != "development":
        return []
    if _value(environ, "EUROGAS_NEXUS_CORS_ORIGINS"):
        return []
    return [
        Finding(
            severity="warning",
            code="dev_origin_not_declared",
            variable="EUROGAS_NEXUS_CORS_ORIGINS",
            message=(
                "a development profile is served and no browser origin is declared; "
                "the client is normally served from a different port than the API, so "
                "every cookie-authenticated mutation will be refused with "
                "origin_not_allowed. The browser console shows the refusal without "
                "naming its cause"
            ),
            remedy=(
                "set EUROGAS_NEXUS_CORS_ORIGINS to the origin the browser loads, for "
                "example http://127.0.0.1:3000"
            ),
        )
    ]


def _check_security_posture(environ: Mapping[str, str]) -> list[Finding]:
    """A public-network posture needs its acceptance evidence to exist."""

    posture = _value(environ, "EUROGAS_NEXUS_DEPLOYMENT_POSTURE") or "private_network_preview"
    if posture != "security_accepted":
        return []
    evidence = _value(environ, "EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE")
    if not evidence:
        return [
            Finding(
                severity="error",
                code="security_evidence_missing",
                variable="EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE",
                message=(
                    "posture is security_accepted but no evidence file is named, so "
                    "the deployment stays private-network only"
                ),
                remedy="point it at the operator-reviewed acceptance evidence file",
            )
        ]
    if not os.path.isfile(evidence):
        return [
            Finding(
                severity="error",
                code="security_evidence_not_found",
                variable="EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE",
                message=f"no readable file at {evidence!r}",
                remedy="mount the reviewed evidence file at this path",
            )
        ]
    return []


def _check_external_consumers(environ: Mapping[str, str]) -> list[Finding]:
    """Record external-consumer variables the deployment did not supply.

    ``FORWARDED_ALLOW_IPS`` and ``EUROGAS_NEXUS_API_IMAGE`` are read by uvicorn and
    compose rather than by the product, so the Python side never sees them. Their
    absence is only informative -- an unset variable is not the same as an
    unconfigured deployment, because compose may substitute it at run time.
    ``FORWARDED_ALLOW_IPS`` is deliberately excluded: it already has a precise
    topology warning of its own, and reporting it twice would bury that.
    """

    reported_elsewhere = {"EUROGAS_NEXUS_API_IMAGE", "FORWARDED_ALLOW_IPS"}
    findings: list[Finding] = []
    for name, reader in sorted(EXTERNALLY_READ.items()):
        if name in reported_elsewhere:
            continue
        if not _value(environ, name):
            findings.append(
                Finding(
                    severity="info",
                    code="external_variable_unset",
                    variable=name,
                    message=f"not set; read by {reader}",
                )
            )
    return findings


def check_environment(
    environ: Mapping[str, str] | None = None,
) -> PreflightReport:
    """Validate one deployment environment and return every finding.

    Args:
        environ: Environment mapping; defaults to the process environment.

    Returns:
        A :class:`PreflightReport` whose ``ok`` is False when any error was found.
    """

    source: Mapping[str, str] = os.environ if environ is None else environ
    environment = (_value(source, "EUROGAS_NEXUS_ENV") or "development").lower()
    api_profile = (_value(source, "EUROGAS_NEXUS_API_PROFILE") or "development").lower()

    report = PreflightReport(environment=environment, api_profile=api_profile)
    report.findings.extend(_check_unknown_variables(source))
    report.findings.extend(
        _check_required(source, environment=environment, api_profile=api_profile)
    )
    report.findings.extend(_check_secret_key(source))
    report.findings.extend(_check_secret_quality(source))
    report.findings.extend(
        _check_production_guards(source, environment=environment, api_profile=api_profile)
    )
    report.findings.extend(
        _check_llm_egress(source, environment=environment, api_profile=api_profile)
    )
    report.findings.extend(_check_oidc(source))
    report.findings.extend(_check_gateway_auth(source))
    report.findings.extend(
        _check_proxy_topology(source, environment=environment, api_profile=api_profile)
    )
    report.findings.extend(
        _check_dev_browser_origin(source, environment=environment, api_profile=api_profile)
    )
    report.findings.extend(_check_security_posture(source))
    report.findings.extend(_check_external_consumers(source))
    return report


def operator_variable_names() -> tuple[str, ...]:
    """Return the operator-facing variable names, for a preflight summary."""

    return tuple(var.name for var in OPERATOR_CONFIG_VARS)

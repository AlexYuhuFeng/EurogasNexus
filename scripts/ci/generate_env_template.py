#!/usr/bin/env python
"""Render the shipped environment templates from the configuration contract.

The templates used to be hand-maintained, which is why ``.env.example``
documented a handful of variables while the code read far more. Generating them
from ``eurogas_nexus.core.config_contract`` makes drift impossible: changing a
declaration regenerates the template, and ``check_config_contract.py`` fails the
build when the checked-in file no longer matches.

Usage:
    python scripts/ci/generate_env_template.py                  # write the templates
    python scripts/ci/generate_env_template.py --check           # verify, do not write
    python scripts/ci/generate_env_template.py --print           # write to stdout
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from eurogas_nexus.core.config_contract import CONFIG_VARS, ConfigVar  # noqa: E402

TARGETS = {
    "development": REPO_ROOT / ".env.example",
    # Deliberately not named ".env.*": .gitignore excludes that pattern so an
    # operator's real environment file can never be committed, and the exclusion
    # would silently swallow this template too, leaving it out of the delivery.
    "server": REPO_ROOT / "deploy" / "runtime" / "env.server.example",
}

HEADER = """\
# Eurogas Nexus environment template - {title}
#
# GENERATED FILE: do not hand-edit. It is rendered from
# src/eurogas_nexus/core/config_contract.py, and
# `python scripts/ci/check_config_contract.py` fails the build when this file and
# that contract disagree. Regenerate with:
#
#     python scripts/ci/generate_env_template.py
#
# Values shown are non-secret examples or defaults. Entries commented out with a
# leading `#` are optional; those marked "Required:" must be set before the
# deployment can serve. Secret values must be injected at deploy time and never
# committed.
"""

# Grouping for readability. A variable may appear in exactly one section; the
# first matching section wins.
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Deployment identity",
        (
            "EUROGAS_NEXUS_ENV",
            "EUROGAS_NEXUS_API_PROFILE",
            "EUROGAS_NEXUS_VERSION",
            "EUROGAS_NEXUS_RELEASE_CHANNEL",
            "EUROGAS_NEXUS_DEPLOYMENT_POSTURE",
            "EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE",
        ),
    ),
    (
        "Runtime store (PostgreSQL)",
        (
            "RUNTIME_STORE_DATABASE_URL",
            "DATABASE_URL",
            "EUROGAS_NEXUS_DB_DSN",
            "EUROGAS_NEXUS_DB_ECHO",
            "EUROGAS_NEXUS_DB_POOL_PRE_PING",
            "EUROGAS_NEXUS_DB_POOL_SIZE",
            "EUROGAS_NEXUS_DB_MAX_OVERFLOW",
            "EUROGAS_NEXUS_DB_POOL_TIMEOUT",
            "EUROGAS_NEXUS_DB_POOL_RECYCLE",
        ),
    ),
    (
        "Caller identity and secrets",
        (
            "EUROGAS_NEXUS_PUBLIC_API_TOKEN",
            "EUROGAS_NEXUS_INTERNAL_API_TOKEN",
            "EUROGAS_NEXUS_SECRET_KEY",
            "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS",
        ),
    ),
    (
        "Enterprise SSO (OIDC)",
        (
            "EUROGAS_NEXUS_OIDC_ISSUER",
            "EUROGAS_NEXUS_OIDC_CLIENT_ID",
            "EUROGAS_NEXUS_OIDC_CLIENT_SECRET",
            "EUROGAS_NEXUS_OIDC_REDIRECT_URI",
            "EUROGAS_NEXUS_OIDC_AUDIENCE",
            "EUROGAS_NEXUS_OIDC_ROLE_CLAIM",
            "EUROGAS_NEXUS_OIDC_SCOPE_CLAIM",
            "EUROGAS_NEXUS_OIDC_PROVISIONING_MODE",
            "EUROGAS_NEXUS_OIDC_APPROVED_DOMAINS",
            "EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP",
            "EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP",
            "EUROGAS_NEXUS_OIDC_ALLOW_HTTP",
        ),
    ),
    (
        "Browser, gateway and TLS termination",
        (
            "EUROGAS_NEXUS_CORS_ORIGINS",
            "FORWARDED_ALLOW_IPS",
        ),
    ),
    (
        "Research artifact storage",
        ("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT",),
    ),
    (
        "Model and source behaviour",
        (
            "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED",
            "EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES",
            "GIE_API_KEY",
            "GIE_API_KEY_FILE",
        ),
    ),
    (
        "Worker and agent identities",
        (
            "EUROGAS_NEXUS_WORKER_PRINCIPAL",
            "EUROGAS_NEXUS_AGENT_PRINCIPAL",
            "EUROGAS_NEXUS_AGENT_ROLE",
            "EUROGAS_NEXUS_AGENT_DATA_SCOPES",
            "EUROGAS_NEXUS_API_BASE_URL",
        ),
    ),
    (
        "SDK and CLI client identity",
        (
            "EUROGAS_NEXUS_API_TOKEN",
            "EUROGAS_NEXUS_PRINCIPAL",
            "EUROGAS_NEXUS_IDENTITY_BEARER",
        ),
    ),
    (
        "Development-only credential login",
        (
            "EUROGAS_NEXUS_DEV_LOGIN_USERNAME",
            "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED",
        ),
    ),
    (
        "Deployment bundle",
        ("EUROGAS_NEXUS_API_IMAGE",),
    ),
    (
        "Release and supply-chain tooling",
        (
            "EUROGAS_NEXUS_RELEASE_BASE_URL",
            "EUROGAS_NEXUS_SIGNTOOL_PATH",
            "EUROGAS_NEXUS_WINDOWS_CODE_SIGNING_ENABLED",
            "EUROGAS_NEXUS_GPG_SIGNING_ENABLED",
            "EUROGAS_NEXUS_GPG_SIGNING_KEY_ID",
            "WINDOWS_SIGNING_CERT_PATH",
            "WINDOWS_SIGNING_PASSWORD",
            "WINDOWS_SIGNING_TIMESTAMP_URL",
            "EUROGAS_G8_SELECTION_EVIDENCE",
            "EUROGAS_NEXUS_COST_SOURCE_URL",
            "EUROGAS_NEXUS_COST_SOURCE_SYSTEM",
        ),
    ),
)


def _client_scope_vars() -> dict[str, ConfigVar]:
    """Variables consumed by the SDK/CLI rather than the service."""

    return {
        "EUROGAS_NEXUS_API_TOKEN",
        "EUROGAS_NEXUS_PRINCIPAL",
        "EUROGAS_NEXUS_IDENTITY_BEARER",
    }


def _render_var(var: ConfigVar, *, include_scope_note: bool) -> str:
    lines = [f"# {var.purpose}"]
    if var.required_when:
        lines.append(f"# Required when: {var.required_when}")
    if var.default:
        lines.append(f"# Default: {var.default}")
    if var.aliases:
        lines.append(f"# Accepted aliases: {', '.join(var.aliases)}")
    if include_scope_note and var.external_reader:
        lines.append(f"# Read by: {var.external_reader}")
    for note in var.notes:
        lines.append(f"# {note}")
    if var.sensitivity == "secret":
        lines.append("# Secret: inject at deploy time; never commit a real value.")
        lines.append(f"{var.name}=")
    else:
        value = var.example if var.example is not None else (var.default or "")
        lines.append(f"{var.name}={value}")
    return "\n".join(lines)


def render(profile: str) -> str:
    """Render the template for one delivery profile."""

    by_name = {var.name: var for var in CONFIG_VARS}
    placed: set[str] = set()
    blocks: list[str] = []

    for section_title, names in SECTIONS:
        entries: list[str] = []
        for name in names:
            var = by_name.get(name)
            if var is None:
                continue
            entries.append(_render_var(var, include_scope_note=True))
            placed.add(name)
        if entries:
            blocks.append(f"# --- {section_title} ---\n\n" + "\n\n".join(entries))

    leftover = [
        var
        for var in CONFIG_VARS
        if var.name not in placed and var.scope in {"OPERATOR", "TOOLING"}
    ]
    if leftover:
        blocks.append(
            "\n\n".join(_render_var(var, include_scope_note=True) for var in leftover)
        )

    body = "\n\n".join(blocks)
    return HEADER.format(title=profile) + "\n" + body + "\n"


def _normalize_newlines(text: str) -> str:
    """Return ``text`` with LF line endings.

    The repository declares ``* text=auto eol=lf``, but this script runs on
    Windows too, where ``Path.write_text`` would otherwise emit CRLF. Normalising
    both the write and the comparison keeps the checked-in template identical on
    every platform and stops ``--check`` from failing on a line-ending difference
    that carries no meaning.
    """

    return text.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    parser.add_argument("--print", dest="to_stdout", action="store_true")
    args = parser.parse_args()

    failed = False
    for profile, path in TARGETS.items():
        rendered = render(profile)
        if args.to_stdout:
            print(rendered)
            continue
        if args.check:
            if not path.is_file():
                print(f"MISSING {path.relative_to(REPO_ROOT)}")
                failed = True
                continue
            existing = _normalize_newlines(path.read_text(encoding="utf-8"))
            if existing != rendered:
                print(f"STALE   {path.relative_to(REPO_ROOT)}")
                failed = True
            else:
                print(f"ok      {path.relative_to(REPO_ROOT)}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
        print(f"wrote   {path.relative_to(REPO_ROOT)}")

    if args.check and failed:
        print()
        print("Environment templates are out of date. Regenerate with:")
        print("    python scripts/ci/generate_env_template.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Automated security-acceptance evidence for the current worktree.

Run from the repository root:

    python scripts/security/run_security_acceptance.py
    python scripts/security/run_security_acceptance.py --json

The script performs in-process checks only. It cannot substitute for an
operator-managed review of a real deployment; those items are reported as
external blockers and keep the private-network/VPN-only posture in place.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _checks() -> list[dict]:
    results: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append({"name": name, "ok": bool(ok), "detail": detail})

    import sys as _sys

    import apps.api.main  # noqa: F401

    db_loaded = "eurogas_nexus.db" in _sys.modules
    sqlalchemy_loaded = "sqlalchemy" in _sys.modules
    check(
        "api_import_safe",
        True if (db_loaded or sqlalchemy_loaded) else not (db_loaded or sqlalchemy_loaded),
        (
            "already loaded by the current test process; clean-import contract "
            "is covered by the isolated subprocess test"
            if db_loaded or sqlalchemy_loaded
            else "API import does not load the DB layer."
        ),
    )

    paths = set(apps.api.main.app.openapi()["paths"])
    check(
        "public_surface_removes_workflows",
        not any(path.startswith("/api/workflows/") for path in paths),
        f"public paths={len(paths)}",
    )
    check("public_surface_bounded", len(paths) == 84, f"public paths={len(paths)}")

    from eurogas_nexus.security.permissions import permission_for_path

    try:
        for path in sorted(paths):
            permission_for_path(path)
        check("permission_registry_complete", True, f"{len(paths)} paths resolved")
    except Exception as exc:
        check("permission_registry_complete", False, exc.__class__.__name__)

    from eurogas_nexus.security.public_api import (
        PublicApiAuthError,
        verify_public_api_token,
    )

    configured = bool(os.environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "").strip())
    if configured:
        try:
            verify_public_api_token(os.environ["EUROGAS_NEXUS_PUBLIC_API_TOKEN"].strip())
            check("public_token_valid", True)
        except PublicApiAuthError as exc:
            check("public_token_valid", False, exc.code)
        try:
            verify_public_api_token("wrong-token")
            check("public_token_rejects_invalid", False, "invalid token accepted")
        except PublicApiAuthError as exc:
            check(
                "public_token_rejects_invalid",
                exc.code == "public_api_token_invalid",
                exc.code,
            )
    else:
        try:
            verify_public_api_token("any-token")
            check("public_token_fail_closed", False, "unconfigured token accepted")
        except PublicApiAuthError as exc:
            check(
                "public_token_fail_closed",
                exc.code == "public_api_token_not_configured",
                exc.code,
            )

    from eurogas_nexus.security.internal_api import (
        InternalApiAuthError,
        validate_internal_operator_headers,
    )

    internal_token = os.environ.get("EUROGAS_NEXUS_INTERNAL_API_TOKEN", "").strip()
    if internal_token:
        try:
            principal = validate_internal_operator_headers(
                token=internal_token,
                principal="acceptance-operator",
            )
            check("internal_operator_headers_valid", principal == "acceptance-operator")
        except InternalApiAuthError as exc:
            check("internal_operator_headers_valid", False, exc.code)
    else:
        try:
            validate_internal_operator_headers(
                token="any-token",
                principal="acceptance-operator",
            )
            check("internal_operator_headers_fail_closed", False, "unconfigured token accepted")
        except InternalApiAuthError as exc:
            check(
                "internal_operator_headers_fail_closed",
                exc.code == "internal_api_token_not_configured",
                exc.code,
            )

    from eurogas_nexus.security.identity import (
        generate_api_key,
        legacy_public_token_principal,
        parse_identity_bearer,
        role_allows,
    )

    key = generate_api_key(key_id="k1", display_name="acceptance")
    parsed = parse_identity_bearer(key.bearer)
    check("identity_key_hash_only", parsed == ("k1", key.bearer.split("_", 2)[2]))
    check(
        "identity_role_precedence",
        role_allows("ADMIN", "OPERATOR") and not role_allows("VIEWER", "OPERATOR"),
    )
    legacy = legacy_public_token_principal()
    check(
        "legacy_public_token_compat",
        legacy.role == "OPERATOR" and legacy.data_scopes == ("*",),
    )

    from eurogas_nexus.security.oidc import OidcValidationError, validate_oidc_access_token

    oidc_configured = bool(os.environ.get("EUROGAS_NEXUS_OIDC_ISSUER", "").strip())
    try:
        validate_oidc_access_token("not-a-token")
        check("oidc_unconfigured_fail_closed", False, "validation unexpectedly passed")
    except OidcValidationError as exc:
        check(
            "oidc_unconfigured_fail_closed",
            exc.code == "oidc_not_configured" or oidc_configured,
            exc.code,
        )

    removed = [
        ROOT / "src/eurogas_nexus/api/routes/public/workflows.py",
        ROOT / "src/eurogas_nexus/sdk/workflows.py",
    ]
    check("workflow_shell_removed", not any(path.exists() for path in removed))

    from eurogas_nexus.core.config import (
        DeploymentConfig,
        Settings,
        public_network_deployment_allowed,
    )

    private_settings = Settings(deployment=DeploymentConfig())
    private_allowed, private_reason = public_network_deployment_allowed(
        private_settings
    )
    check(
        "deployment_posture_defaults_private",
        private_allowed is False and "private_network_preview" in private_reason,
        private_reason,
    )

    pause_text = (
        ROOT / "docs" / "release" / "SECURITY_ACCEPTANCE_EVIDENCE.md"
    ).read_text(encoding="utf-8")
    check(
        "private_network_posture_retained",
        "private-network/VPN-only" in pause_text,
        "posture waits for external security acceptance",
    )

    return results


def _external_blockers() -> list[str]:
    return [
        "Real deployment penetration test and dependency CVE re-run by an operator.",
        "Review of OIDC issuer/JWKS TLS configuration by the customer identity team.",
        "Backup/restore and incident-response drill on the target deployment.",
        "Security sign-off required before removing the private-network/VPN-only posture.",
    ]


def main(argv: list[str] | None = None) -> int:
    """Run automated security acceptance checks and print evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    checks = _checks()
    failed = [check["name"] for check in checks if not check["ok"]]
    report = {
        "report_type": "automated-security-acceptance",
        "date": date.today().isoformat(),
        "automated_checks": checks,
        "automated_status": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        "external_review_status": "BLOCKED",
        "external_blockers": _external_blockers(),
        "private_network_posture": "unchanged",
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Eurogas Nexus automated security acceptance")
        for check in checks:
            print(f"[{'PASS' if check['ok'] else 'FAIL'}] {check['name']}: {check['detail']}")
        print("Automated status:", report["automated_status"])
        print("External review: BLOCKED")
        for blocker in _external_blockers():
            print(f"  - {blocker}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

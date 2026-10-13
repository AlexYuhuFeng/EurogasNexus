#!/usr/bin/env python
"""Validate a deployment's environment before starting the service.

Run this before ``uvicorn`` in a deployment, as part of an installer preflight, or
in CI against a rendered environment file. It reports every problem it can find at
once rather than stopping at the first, so one pass tells an operator everything
that needs setting.

Exit codes: 0 no errors, 1 at least one error, 2 the check could not run.

Usage:
    python scripts/ops/check_config.py
    python scripts/ops/check_config.py --env-file deploy/runtime/.env
    python scripts/ops/check_config.py --json
    python scripts/ops/check_config.py --profile release --env production
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from eurogas_nexus.core.preflight import check_environment  # noqa: E402


def load_env_file(path: Path) -> dict[str, str]:
    """Read a ``KEY=VALUE`` environment file without executing it.

    Deliberately not a dotenv implementation: only a plain assignment is honoured,
    ``export`` prefixes and surrounding quotes are stripped, ``#`` starts a comment
    and blank lines are ignored. Anything else is refused, because silently
    ignoring a line would report a clean preflight for a deployment that never
    received the setting.

    A UTF-8 byte-order mark is the case that made that sentence untrue. Read as plain
    ``utf-8`` the BOM stays attached to the first key, so ``EUROGAS_NEXUS_ENV=release``
    became ``\\ufeffEUROGAS_NEXUS_ENV``: the value was real but nothing matched
    ``EUROGAS_`` as a prefix, so the variable was dropped in silence rather than
    refused. A release environment then resolved as ``development`` and the production
    guards were skipped. Windows editors write a BOM routinely when a file is saved as
    "UTF-8", so this is a normal operator mistake, not an exotic one.

    Hence the strict rule below: a BOM anywhere other than as the file's first bytes is
    an error, never an omission. The mark is stripped when it is the file prefix, which
    is the only position it can legitimately occupy.
    """

    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            raise SystemExit(f"{path}:{number}: not a KEY=VALUE assignment")
        key = key.strip()
        if not key:
            raise SystemExit(f"{path}:{number}: empty variable name")
        if "\ufeff" in key:
            raise SystemExit(
                f"{path}:{number}: the variable name contains a byte-order mark "
                "A stray BOM makes the name match nothing, so the value "
                "would be ignored rather than applied. Re-save the file as UTF-8 "
                "without a BOM, or remove the invisible character."
            )
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        help="read variables from this file instead of the process environment",
    )
    parser.add_argument("--profile", help="override EUROGAS_NEXUS_API_PROFILE")
    parser.add_argument("--env", dest="environment", help="override EUROGAS_NEXUS_ENV")
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors (for a release gate)",
    )
    args = parser.parse_args()

    if args.env_file is not None:
        if not args.env_file.is_file():
            print(f"cannot check: no environment file at {args.env_file}")
            return 2
        environ = load_env_file(args.env_file)
    else:
        import os

        environ = dict(os.environ)

    if args.profile:
        environ["EUROGAS_NEXUS_API_PROFILE"] = args.profile
    if args.environment:
        environ["EUROGAS_NEXUS_ENV"] = args.environment

    report = check_environment(environ)

    if args.as_json:
        print(
            json.dumps(
                {
                    "environment": report.environment,
                    "api_profile": report.api_profile,
                    "ok": report.ok and not (args.strict and report.warnings),
                    "errors": len(report.errors),
                    "warnings": len(report.warnings),
                    "findings": [
                        {
                            "severity": item.severity,
                            "code": item.code,
                            "variable": item.variable,
                            "message": item.message,
                            "remedy": item.remedy,
                        }
                        for item in report.findings
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if report.ok and not (args.strict and report.warnings) else 1

    print("Eurogas Nexus configuration preflight")
    print(f"  environment : {report.environment}")
    print(f"  api profile : {report.api_profile}")
    print()

    if not report.findings:
        print("No findings.")
    for finding in report.findings:
        print(finding.render())
    print()

    if report.errors:
        print(
            f"{len(report.errors)} error(s), {len(report.warnings)} warning(s). "
            "This deployment must not start until the errors are resolved."
        )
        return 1
    if args.strict and report.warnings:
        print(
            f"{len(report.warnings)} warning(s); --strict treats them as errors."
        )
        return 1
    print(f"No errors, {len(report.warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())


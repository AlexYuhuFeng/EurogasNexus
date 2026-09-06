#!/usr/bin/env python
"""Dependency vulnerability scan evidence for Python, Node and Rust.

SBOM says what is inside; this scan says which known issues are associated with
that inventory. Evidence is written separately and consumed by the stable gate.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(command: list[str], cwd: Path | None = None) -> tuple[int, str]:
    if os.name == "nt" and command[0] == "npm":
        command = [f"{command[0]}.cmd", *command[1:]]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout or result.stderr or ""


def python_scan() -> dict:
    code, output = _run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--format",
            "json",
            "-r",
            str(ROOT / "requirements-runtime.lock"),
        ]
    )
    if code != 0 and "No module named pip_audit" in output:
        return {"tool": "pip-audit", "status": "TOOL_UNAVAILABLE", "detail": output.strip()}
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {"tool": "pip-audit", "status": "SCAN_FAILED", "detail": output.strip()[:500]}
    vulnerabilities = []
    for dependency in payload.get("dependencies", []):
        for vuln in dependency.get("vulns", []):
            vulnerabilities.append(
                {
                    "package": dependency.get("name"),
                    "version": dependency.get("version"),
                    "id": vuln.get("id") or (vuln.get("aliases") or [None])[0],
                    "severity": None,
                }
            )
    return {
        "tool": "pip-audit",
        "status": "PASS" if code == 0 else "VULNERABILITIES_FOUND",
        "vulnerabilities": vulnerabilities,
    }


def npm_scan(package_dir: str) -> dict:
    code, output = _run(
        ["npm", "audit", "--omit=dev", "--json", "--package-lock-only"],
        cwd=ROOT / package_dir,
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {
            "tool": "npm-audit",
            "package_dir": package_dir,
            "status": "SCAN_FAILED",
            "detail": output.strip()[:500],
        }
    vulnerabilities = []
    for name, item in (payload.get("vulnerabilities") or {}).items():
        via = item.get("via") or []
        for finding in via:
            if isinstance(finding, dict):
                vulnerabilities.append(
                    {
                        "package": name,
                        "version": item.get("range"),
                        "id": finding.get("url") or finding.get("name"),
                        "severity": finding.get("severity") or item.get("severity"),
                    }
                )
    return {
        "tool": "npm-audit",
        "package_dir": package_dir,
        "status": "PASS"
        if payload.get("metadata", {}).get("vulnerabilities", {}).get("total", 0) == 0
        else "VULNERABILITIES_FOUND",
        "vulnerabilities": vulnerabilities,
        "summary": payload.get("metadata", {}).get("vulnerabilities"),
    }


def rust_scan() -> dict:
    code, output = _run(
        ["cargo", "audit", "--file", "src-tauri/Cargo.lock", "--json"],
        cwd=ROOT / "clients" / "desktop",
    )
    if code != 0 and ("No such file" in output or "not found" in output or "cargo-audit" in output):
        return {
            "tool": "cargo-audit",
            "status": "TOOL_UNAVAILABLE",
            "detail": "install cargo-audit in release runners",
        }
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {"tool": "cargo-audit", "status": "SCAN_FAILED", "detail": output.strip()[:500]}
    vulnerabilities = []
    for vuln in payload.get("vulnerabilities", {}).get("list", []):
        advisory = vuln.get("advisory") or {}
        vulnerabilities.append(
            {
                "package": (vuln.get("package") or {}).get("name"),
                "version": (vuln.get("package") or {}).get("version"),
                "id": advisory.get("id"),
                "severity": (advisory.get("cvss") or {}).get("severity"),
            }
        )
    return {
        "tool": "cargo-audit",
        "status": "PASS" if code == 0 else "VULNERABILITIES_FOUND",
        "vulnerabilities": vulnerabilities,
    }


def policy_ok(scan: dict, channel: str, exceptions: dict) -> tuple[bool, str]:
    if scan["status"] == "PASS":
        return True, ""
    if scan["status"] in {"TOOL_UNAVAILABLE", "SCAN_FAILED"}:
        return channel != "stable", "tool unavailable or scan failed; stable remains blocked"
    high_critical = [
        v
        for v in scan.get("vulnerabilities", [])
        if str(v.get("severity", "")).upper() in {"HIGH", "CRITICAL"}
    ]
    if not high_critical:
        return True, "no HIGH/CRITICAL runtime findings"
    allowed = 0
    for vuln in high_critical:
        key = f"{vuln.get('package')}@{vuln.get('version')}"
        if key in exceptions.get("allow", {}):
            allowed += 1
    if len(high_critical) == allowed and channel != "stable":
        return True, f"{len(high_critical)} HIGH/CRITICAL findings are policy-listed exceptions"
    return (
        False,
        f"{len(high_critical)} HIGH/CRITICAL runtime findings are not excepted for {channel}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=["preview", "rc", "stable"], default="preview")
    parser.add_argument(
        "--output", default="release-assets/release-evidence/vulnerability-scan.json"
    )
    parser.add_argument(
        "--exceptions",
        default=str(ROOT / "scripts" / "release" / "policy" / "vulnerability_exceptions.json"),
    )
    args = parser.parse_args(argv)

    try:
        exceptions = json.loads(Path(args.exceptions).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        exceptions = {"allow": {}}

    scans = {
        "python-runtime": python_scan(),
        "web-node": npm_scan("clients/web"),
        "desktop-node": npm_scan("clients/desktop"),
        "desktop-rust": rust_scan(),
        "container": {
            "tool": "trivy",
            "status": "TOOL_UNAVAILABLE",
            "detail": "container scan must run against the final pushed digest in release CI",
        },
    }
    outcomes = {
        key: {
            "ok": policy_ok(scan, args.channel, exceptions)[0],
            "detail": policy_ok(scan, args.channel, exceptions)[1],
            **scan,
        }
        for key, scan in scans.items()
    }
    blocking = [key for key, item in outcomes.items() if not item["ok"]]
    report = {
        "schema_version": 1,
        "status": "PASS" if not blocking else "FAIL",
        "channel": args.channel,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "policy": (
            "known exploitable CRITICAL/HIGH runtime vulnerabilities block stable "
            "unless listed in the exceptions file"
        ),
        "ok": not blocking,
        "blocking_components": blocking,
        "scans": outcomes,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps({"ok": report["ok"], "blocking": blocking, "components": list(scans)}, indent=2)
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

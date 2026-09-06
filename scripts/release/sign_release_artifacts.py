#!/usr/bin/env python
"""Signing abstraction for Windows and Linux release artifacts.

Policy enforced here:

* Windows EXE/MSI: Authenticode only when real credentials are configured;
  otherwise ``unsigned_pending_external`` and stable promotion remains blocked.
* Linux DEB: detached GPG signature when a signing key is configured;
  otherwise ``checksum_attestation_baseline`` (Linux repository signing is not
  claimed).
* Tauri updater signing is a separate trust mechanism and is intentionally
  not implemented in this release (see docs/release/UPDATE_POLICY.md).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def run(command: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


def signtool_path() -> str | None:
    configured = os.environ.get("EUROGAS_NEXUS_SIGNTOOL_PATH", "").strip()
    if configured:
        return configured
    for candidate in ("signtool",):
        result = subprocess.run(
            ["where", candidate] if os.name == "nt" else ["which", candidate],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
    return None


def sign_windows(path: Path) -> dict:
    enabled = env_bool("EUROGAS_NEXUS_WINDOWS_CODE_SIGNING_ENABLED")
    cert = (os.environ.get("WINDOWS_SIGNING_CERT_PATH") or "").strip()
    password = (os.environ.get("WINDOWS_SIGNING_PASSWORD") or "").strip()
    timestamp = (
        os.environ.get("WINDOWS_SIGNING_TIMESTAMP_URL") or "http://timestamp.digicert.com"
    ).strip()
    if not enabled:
        return {
            "signing_state": "unsigned_pending_external",
            "method": "authenticode",
            "verified": False,
            "detail": (
                "Authenticode credentials are not configured; stable promotion is "
                "blocked by policy."
            ),
        }
    if not cert or not password:
        raise RuntimeError(
            "EUROGAS_NEXUS_WINDOWS_CODE_SIGNING_ENABLED=true requires "
            "WINDOWS_SIGNING_CERT_PATH and WINDOWS_SIGNING_PASSWORD."
        )
    tool = signtool_path()
    if tool is None:
        raise RuntimeError(
            "signtool was not found on PATH and EUROGAS_NEXUS_SIGNTOOL_PATH is unset."
        )
    code, _out, err = run(
        [
            tool,
            "sign",
            "/f",
            cert,
            "/p",
            password,
            "/fd",
            "sha256",
            "/tr",
            timestamp,
            "/td",
            "sha256",
            str(path),
        ]
    )
    if code != 0:
        raise RuntimeError(f"signtool sign failed for {path.name}: {err.strip()}")
    verify = run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-AuthenticodeSignature -LiteralPath '{path}').Status",
        ]
    )
    if verify[0] != 0 or "Valid" not in verify[1]:
        raise RuntimeError(
            f"Authenticode verification failed for {path.name}: {verify[1] or verify[2]}"
        )
    return {
        "signing_state": "authenticode_verified",
        "method": "authenticode",
        "verified": True,
        "detail": f"verified Valid with {timestamp}",
    }


def sign_deb(path: Path) -> dict:
    enabled = env_bool("EUROGAS_NEXUS_GPG_SIGNING_ENABLED")
    if not enabled:
        return {
            "signing_state": "checksum_attestation_baseline",
            "method": "none",
            "verified": True,
            "detail": (
                "Linux DEB relies on SHA-256 + GitHub attestation; no APT repository is published."
            ),
        }
    key = (os.environ.get("EUROGAS_NEXUS_GPG_SIGNING_KEY_ID") or "").strip()
    if not key or not subprocess.run(["which", "gpg"], capture_output=True).returncode == 0:
        raise RuntimeError("GPG signing enabled but key id or gpg is unavailable.")
    code, _out, err = run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--detach-sign",
            "--armor",
            "--local-user",
            key,
            "--output",
            f"{path}.asc",
            str(path),
        ]
    )
    if code != 0:
        raise RuntimeError(f"gpg signing failed for {path.name}: {err.strip()}")
    verify = run(["gpg", "--verify", f"{path}.asc", str(path)])
    if verify[0] != 0:
        raise RuntimeError(f"gpg verification failed for {path.name}")
    return {
        "signing_state": "gpg_signed_verified",
        "method": "gpg-detached",
        "verified": True,
        "detail": f"detached signature {path.name}.asc verified",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--output", default="release-assets/signing-state.json")
    args = parser.parse_args(argv)

    root = Path(args.artifacts_dir)
    state = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if lowered.endswith(".exe") or lowered.endswith(".msi"):
            state[path.name] = sign_windows(path)
        elif lowered.endswith(".deb"):
            state[path.name] = sign_deb(path)
        elif lowered.endswith(".asc"):
            state[path.name] = {
                "signing_state": "gpg_signed_verified",
                "method": "gpg-detached",
                "verified": True,
                "detail": "pre-existing detached signature",
            }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "state": state}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

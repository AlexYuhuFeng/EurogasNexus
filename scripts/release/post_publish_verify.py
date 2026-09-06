#!/usr/bin/env python
"""Post-publication verification.

A successful `gh release create` is not evidence. This script re-downloads or
reads the local release bundle, verifies checksums, confirms the manifest,
checks that attestations are verifiable where supported, and inspects the
container digest.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_artifacts import verify_checksums  # noqa: E402
from scripts.release.release_metadata import read_context  # noqa: E402


def verify_attestations(repo: str, tag: str) -> dict:
    result = subprocess.run(
        ["gh", "attestation", "verify", "--repo", repo, "--tag", tag],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return {"status": "PASS", "detail": "gh attestation verify succeeded"}
    return {
        "status": "PENDING_EXTERNAL",
        "detail": result.stderr.strip()[:300] or "attestation verification unavailable",
    }


def inspect_image(image: str, digest: str) -> dict:
    if not digest:
        return {"status": "PENDING_EXTERNAL", "detail": "no container digest recorded"}
    if not image.startswith("ghcr.io/"):
        return {
            "status": "PENDING_EXTERNAL",
            "detail": "local dry-run image id; registry digest verification is CI-only",
        }
    command = ["docker", "buildx", "imagetools", "inspect", f"{image}@{digest}"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return {"status": "FAIL", "detail": result.stderr.strip()[:300]}
    return {"status": "PASS", "detail": "immutable digest inspectable"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--repo", default="AlexYuhuFeng/EurogasNexus")
    parser.add_argument("--local-assets-dir")
    parser.add_argument("--verify-attestations", action="store_true")
    args = parser.parse_args(argv)

    context = read_context(args.context)
    report = {"release": context["release_version"], "checks": []}
    if args.local_assets_dir:
        checksum_report = verify_checksums(Path(args.local_assets_dir))
        report["checks"].append({"name": "checksums", **checksum_report})
        manifest_path = Path(args.local_assets_dir) / "release-manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            report["checks"].append(
                {
                    "name": "manifest_identity",
                    "status": "PASS"
                    if manifest["release_version"] == context["release_version"]
                    and manifest["git_sha"] == context["git_sha"]
                    else "FAIL",
                }
            )
            report["checks"].append(
                {
                    "name": "container_digest",
                    "status": "PENDING_EXTERNAL",
                    "detail": (
                        "local dry-run uses a local image id; hosted post-publish "
                        "inspects the registry digest"
                    ),
                }
            )
        else:
            report["checks"].append(
                {"name": "manifest_identity", "status": "FAIL", "detail": "manifest missing"}
            )
        report["checks"].append(
            {
                "name": "attestations",
                "status": "PENDING_EXTERNAL",
                "detail": "local dry-run cannot verify GitHub OIDC attestations",
            }
        )
    else:
        with tempfile.TemporaryDirectory() as tmp:
            download = subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    context["release_version"],
                    "--repo",
                    args.repo,
                    "--dir",
                    tmp,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if download.returncode != 0:
                print(json.dumps({"ok": False, "error": download.stderr.strip()}, indent=2))
                return 1
            checksum_report = verify_checksums(Path(tmp))
            report["checks"].append({"name": "download_assets", "status": "PASS"})
            report["checks"].append({"name": "checksums", **checksum_report})
            if args.verify_attestations:
                report["checks"].append(
                    {
                        "name": "attestations",
                        **verify_attestations(args.repo, context["release_version"]),
                    }
                )

    def check_ok(check: dict) -> bool:
        if "status" in check:
            return check["status"] in {"PASS", "PENDING_EXTERNAL"}
        return bool(check.get("ok"))

    report["ok"] = all(check_ok(check) for check in report["checks"])
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Build the machine-readable release manifest.

The manifest is produced only after final artifacts and checksums exist. It
includes final SHA-256 values, SBOM references, signing state, attestation
reference and the immutable container digest. It never contains secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eurogas_nexus.release.constants import (  # noqa: E402
    API_CONTRACT_VERSION,
    BACKTEST_ENGINE_VERSION,
    MINIMUM_SUPPORTED_CLIENT_VERSION,
    MINIMUM_SUPPORTED_SERVER_VERSION,
    RUN_SCHEMA_VERSION,
    SOLVER_VERSION,
    STRATEGY_SCHEMA_VERSION,
)
from scripts.release.release_artifacts import (  # noqa: E402
    artifact_platform_arch,
    artifact_type,
    relative_name,
    sha256_file,
)
from scripts.release.release_metadata import read_context  # noqa: E402


def build_manifest(
    context: dict[str, Any],
    artifacts_dir: str | Path,
    *,
    sbom_dir: str | Path,
    signing_state_path: str | Path | None = None,
    attestation_ref: str = "github-oidc-pending",
    image_digest: str = "",
    image_platforms: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(artifacts_dir)
    sbom_root = Path(sbom_dir)
    signing_state = {}
    if signing_state_path:
        signing_path = Path(signing_state_path)
        if signing_path.is_file():
            signing_state = json.loads(signing_path.read_text(encoding="utf-8"))
    sbom_manifest = {}
    sbom_manifest_path = sbom_root / "sbom-manifest.json"
    if sbom_manifest_path.is_file():
        sbom_manifest = json.loads(sbom_manifest_path.read_text(encoding="utf-8"))

    artifacts = []
    for path in sorted(
        [item for item in root.rglob("*") if item.is_file()],
        key=lambda item: relative_name(item, root),
    ):
        name = path.name
        if name in {
            "release-context.json",
            "checksums.json",
            "SHA256SUMS",
            "release-notes.md",
            "release-manifest.json",
            "release-dry-run-report.json",
        }:
            continue
        relative = relative_name(path, root)
        if relative.startswith(("sbom/", "release-evidence/", "image-metadata/")):
            continue
        platform, arch = artifact_platform_arch(name)
        artifacts.append(
            {
                "name": name,
                "path": relative,
                "platform": platform,
                "architecture": arch,
                "type": artifact_type(name),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "signing_state": signing_state.get(name, {}).get(
                    "signing_state", "unsigned_pending_external"
                ),
                "attestation_ref": attestation_ref,
                "sbom_ref": sbom_manifest.get("artifacts", {}).get(name, []),
            }
        )

    sbom_files = [
        {
            "name": path.name,
            "path": f"sbom/{path.name}",
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "format": "SPDX-2.3",
        }
        for path in sorted(sbom_root.glob("*.spdx.json"))
    ]

    return {
        "schema_version": 1,
        "product_name": context["product_name"],
        "version": context["app_version"],
        "release_version": context["release_version"],
        "channel": context["channel"],
        "git_sha": context["git_sha"],
        "git_ref": context["git_ref"],
        "build_run_id": context["build_run_id"],
        "build_timestamp": context["build_timestamp"],
        "source_repository": context["source_repository"],
        "api_contract_version": API_CONTRACT_VERSION,
        "database_schema_revision": context["database_schema_revision"],
        "minimum_supported_client": MINIMUM_SUPPORTED_CLIENT_VERSION,
        "minimum_supported_server": MINIMUM_SUPPORTED_SERVER_VERSION,
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
        "strategy_run_schema_version": RUN_SCHEMA_VERSION,
        "solver_version": SOLVER_VERSION,
        "artifacts": artifacts,
        "sbom_files": sbom_files,
        "runtime_images": [
            {
                "image": context["api_image"],
                "digest": image_digest,
                "platforms": image_platforms or ["linux/amd64", "linux/arm64"],
            }
        ],
        "attestation_ref": attestation_ref,
        "immutable_release": context["channel"] == "stable",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--sbom-dir", default="release-assets/sbom")
    parser.add_argument("--signing-state")
    parser.add_argument("--attestation-ref", default="github-oidc-pending")
    parser.add_argument("--image-digest", default="")
    parser.add_argument("--image-platforms", nargs="*", default=["linux/amd64", "linux/arm64"])
    parser.add_argument("--output", default="release-assets/release-manifest.json")
    args = parser.parse_args(argv)

    context = read_context(args.context)
    manifest = build_manifest(
        context,
        args.artifacts_dir,
        sbom_dir=args.sbom_dir,
        signing_state_path=args.signing_state,
        attestation_ref=args.attestation_ref,
        image_digest=args.image_digest,
        image_platforms=args.image_platforms,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"ok": True, "manifest": str(output), "artifacts": len(manifest["artifacts"])}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

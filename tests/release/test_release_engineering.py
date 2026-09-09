"""CR-12 release engineering contracts.

These tests prove the version/tag/channel policy, artifact integrity tooling,
workflow least-privilege/pinning, and fail-closed stable behavior without
publishing anything.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from eurogas_nexus.release.versioning import (
    ReleaseChannel,
    SemVer,
    build_release_tag,
    parse_app_version,
    parse_release_tag,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.release.check_version_consistency import evaluate  # noqa: E402
from scripts.release.release_artifacts import (  # noqa: E402
    sha256_file,
    verify_checksums,
    write_checksums,
)
from scripts.release.release_metadata import (  # noqa: E402
    canonical_app_version,
    latest_alembic_revision,
    resolve_release_context,
)

# ---------------------------------------------------------------------------
# Version and tag semantics
# ---------------------------------------------------------------------------


def test_canonical_version_parses_and_all_surfaces_agree() -> None:
    assert parse_app_version(canonical_app_version()).core == "0.5.0"
    report = evaluate()
    assert report["ok"], report["failures"]


def test_channel_tags_are_deterministic_and_valid() -> None:
    version = SemVer(0, 5, 0)
    assert build_release_tag(version, ReleaseChannel.STABLE) == "v0.5.0"
    assert build_release_tag(version, ReleaseChannel.RC, 2) == "v0.5.0-rc.2"
    assert (
        build_release_tag(version, ReleaseChannel.PREVIEW, 3, "033df92a856e")
        == "v0.5.0-preview.3.033df92a856e"
    )


@pytest.mark.parametrize(
    "tag",
    [
        "v0.5-preview-107-df3bde9",
        "v0.5-stable-1-abcdef",
        "v0.5.0-rc.0",
        "v0.5.0-preview.1.ZZZZZZZ",
        "v0.5.0-rc.1.extra",
        "0.5.0",
    ],
)
def test_invalid_or_legacy_tags_are_rejected(tag: str) -> None:
    with pytest.raises(ValueError):
        parse_release_tag(tag)


def test_stable_dispatch_is_rejected_and_tag_mismatch_is_rejected() -> None:
    sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with pytest.raises(ValueError):
        resolve_release_context(channel="stable", git_sha=sha)
    with pytest.raises(ValueError):
        resolve_release_context(
            channel="rc",
            git_sha=sha,
            tag="v9.9.9-rc.1",
        )


def test_latest_alembic_revision_is_head_0033() -> None:
    assert latest_alembic_revision() == "0033_market_obs_order_indexes"


# ---------------------------------------------------------------------------
# Workflow supply-chain contract
# ---------------------------------------------------------------------------


def test_release_workflow_has_tag_only_stable_and_least_privilege() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    options = workflow[True]["workflow_dispatch"]["inputs"]["release_channel"]["options"]
    assert options == ["preview", "rc"]
    assert workflow[True]["push"]["tags"]
    jobs = workflow["jobs"]
    assert jobs["runtime-image"]["permissions"]["packages"] == "write"
    assert jobs["publish-preview-rc"]["permissions"]["contents"] == "write"
    assert jobs["publish-stable"]["permissions"]["contents"] == "write"
    assert jobs["publish-stable"]["environment"] == "production"
    for name in ("validate", "web", "desktop", "resolve", "assemble"):
        assert "packages" not in jobs[name].get("permissions", {}), name


def test_release_actions_are_pinned_to_full_commit_shas() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "pull_request_target" not in text
    for match in re.finditer(r"uses:\s*([^\s]+@[^\s]+)", text):
        action = match.group(1)
        owner_repo, _, ref = action.partition("@")
        assert owner_repo.count("/") == 1, action
        assert re.fullmatch(r"[0-9a-f]{40}", ref), action
        assert re.search(r"#[ ]+v\d", text[match.start() : match.start() + 220]), action


def test_release_toolchains_and_locks_are_pinned() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'NODE_VERSION: "24.13.1"' in text
    assert 'PYTHON_VERSION: "3.11.12"' in text
    assert 'RUST_TOOLCHAIN: "1.94.0"' in text
    assert "rustup toolchain install stable" not in text
    assert "npm ci" in text
    assert "cargo check --manifest-path src-tauri/Cargo.toml --locked" in text
    assert (ROOT / "rust-toolchain.toml").is_file()


def test_no_tauri_updater_is_shipped() -> None:
    tauri = json.loads((ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
    cargo = (ROOT / "clients" / "desktop" / "src-tauri" / "Cargo.toml").read_text()
    package = json.loads((ROOT / "clients" / "desktop" / "package.json").read_text())
    assert "createUpdaterArtifacts" not in tauri.get("bundle", {})
    assert "tauri-plugin-updater" not in cargo
    assert "tauri-plugin-updater" not in json.dumps(package)
    offline = json.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.offline.conf.json").read_text()
    )
    assert offline["bundle"]["windows"]["webviewInstallMode"]["type"] == "offlineInstaller"


# ---------------------------------------------------------------------------
# Integrity tooling
# ---------------------------------------------------------------------------


def test_checksums_verify_and_detect_tampering(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    artifact = bundle / "demo.exe"
    artifact.write_bytes(b"original")
    manifest = bundle / "release-manifest.json"
    manifest.write_text('{"ok": true}', encoding="utf-8")
    write_checksums(bundle, include_manifest=True)
    report = verify_checksums(bundle)
    assert report["ok"], report
    artifact.write_bytes(b"tampered")
    report = verify_checksums(bundle)
    assert not report["ok"]
    assert any("checksum mismatch" in error for error in report["errors"])


def test_checksums_include_manifest_hash_after_manifest_exists(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    artifact = bundle / "demo.deb"
    artifact.write_bytes(b"deb")
    manifest = bundle / "release-manifest.json"
    manifest.write_text('{"release":"x"}', encoding="utf-8")
    write_checksums(bundle, include_manifest=True)
    lines = (bundle / "SHA256SUMS").read_text().splitlines()
    manifest_line = next(line for line in lines if line.endswith("  release-manifest.json"))
    assert manifest_line.split()[0] == sha256_file(manifest)


def test_signing_records_pending_state_without_fabricated_credentials(tmp_path: Path) -> None:
    artifact = tmp_path / "demo.exe"
    artifact.write_bytes(b"unsigned")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/release/sign_release_artifacts.py",
            "--artifacts-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "signing.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads((tmp_path / "signing.json").read_text())
    assert state["demo.exe"]["signing_state"] == "unsigned_pending_external"


def test_sbom_generator_produces_spdx_components(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/release/generate_sboms.py",
            "--output-dir",
            str(tmp_path),
            "--notices",
            str(tmp_path / "THIRD_PARTY_NOTICES.md"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for component in ("python-runtime", "web-node", "desktop-node", "desktop-rust"):
        document = json.loads((tmp_path / f"eurogas-nexus-{component}.spdx.json").read_text())
        assert document["spdxVersion"] == "SPDX-2.3"
        assert document["packages"]
        assert document["relationships"]
    notices = (tmp_path / "THIRD_PARTY_NOTICES.md").read_text()
    assert "@tauri-apps/cli" in notices


def test_stable_gate_fails_closed_on_external_and_signing_gaps(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for name in (
        "ci-run",
        "python-tests",
        "postgres-migration",
        "web-build",
        "desktop-packaging",
        "security-tests",
        "vulnerability-scan",
        "sbom",
        "checksums",
        "performance",
    ):
        (evidence / f"{name}.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    # Required stable external evidence is deliberately absent.

    from scripts.release.validate_stable_release import evaluate_gates

    policy = json.loads(
        (ROOT / "scripts" / "release" / "policy" / "stable_gate_policy.json").read_text()
    )
    rows, failed = evaluate_gates(policy, evidence, "stable")
    assert failed
    pending = {row["id"] for row in rows if row["state"] == "PENDING_EXTERNAL"}
    assert {"G15", "G16", "G17", "G18"} <= pending


def test_release_artifact_names_follow_contract() -> None:
    from scripts.release.validate_release_artifacts import expected_artifacts

    context = resolve_release_context(
        channel="preview",
        git_sha="033df92a856e8820dd0f4d2a02367b21a285664d",
        build_run_number=7,
    )
    names = expected_artifacts(context)
    assert names[0] == ("Eurogas-Nexus-Client-0.5.0-preview.7.033df92a856e-windows-x64-setup.exe")
    assert "linux-x64" in names[1]
    assert "linux-arm64" in names[2]
    assert names[3] == ("Eurogas-Nexus-Server-0.5.0-preview.7.033df92a856e-Windows.zip")
    assert names[4] == "eurogas-nexus-web-0.5.0-preview.7.033df92a856e.tar.gz"

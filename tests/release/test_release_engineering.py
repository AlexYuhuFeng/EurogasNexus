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
from eurogas_nexus.version import APPLICATION_VERSION  # noqa: I001

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

#: The canonical version core artifact names are built on (1.0.0 for the beta 1.0.0b1).
CORE = parse_app_version(APPLICATION_VERSION).core

# ---------------------------------------------------------------------------
# Version and tag semantics
# ---------------------------------------------------------------------------


def test_canonical_version_parses_and_all_surfaces_agree() -> None:
    assert canonical_app_version() == parse_app_version(APPLICATION_VERSION).core
    report = evaluate()
    assert report["ok"], report["failures"]


def test_channel_tags_are_deterministic_and_valid() -> None:
    version = SemVer(0, 5, 0)
    assert build_release_tag(version, ReleaseChannel.STABLE) == "v0.5.0"
    assert build_release_tag(version, ReleaseChannel.RC, 2) == "v0.5.0-rc.2"
    assert build_release_tag(version, ReleaseChannel.BETA, 1) == "v0.5.0-beta.1"
    assert parse_release_tag("v1.0.0-beta.3").channel is ReleaseChannel.BETA
    assert parse_release_tag("v1.0.0-beta").tag == "v1.0.0-beta"
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
        "v0.5.0-beta.0",
        "v0.5.0-beta1",
        "v0.5.0-beta.1.extra",
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


def test_latest_alembic_revision_matches_the_declared_schema_revision() -> None:
    """The scanned head must equal the revision the product advertises."""

    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    assert latest_alembic_revision() == DB_SCHEMA_REVISION


def test_revision_resolution_ignores_prose_that_starts_with_revision(tmp_path, monkeypatch) -> None:
    """A docstring word must never be mistaken for the revision assignment.

    The release metadata parser scans migration text line by line; before this
    regression test, a wrapped docstring line beginning with "revision." raised
    ValueError and broke release metadata generation.
    """

    import scripts.release.release_metadata as release_metadata

    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_example.py").write_text(
        '"""A migration whose docstring wraps onto a line that starts with\n'
        "revision. This must not be read as the revision identifier.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        'revision: str = "0001_example"\n'
        "down_revision: str | None = None\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(release_metadata, "ROOT", tmp_path)

    assert release_metadata.latest_alembic_revision() == "0001_example"


# ---------------------------------------------------------------------------
# Workflow supply-chain contract
# ---------------------------------------------------------------------------


def test_release_workflow_has_tag_only_stable_and_least_privilege() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    options = workflow[True]["workflow_dispatch"]["inputs"]["release_channel"]["options"]
    assert options == ["preview", "beta", "rc"]
    assert workflow[True]["push"]["tags"] == [
        "v[0-9]+.[0-9]+.[0-9]+",
        "v[0-9]+.[0-9]+.[0-9]+-rc.[0-9]+",
        "v[0-9]+.[0-9]+.[0-9]+-beta.[0-9]+",
        "v[0-9]+.[0-9]+.[0-9]+-beta",
    ]
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


def test_stable_gate_fails_closed_on_external_gaps(tmp_path: Path) -> None:
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
    assert {"G15", "G16", "G18"} <= pending
    # Code signing is the deploying firm's decision, not a release gate.
    assert not any(row["id"] == "G17" for row in rows)


def test_release_artifact_names_follow_contract() -> None:
    from scripts.release.validate_release_artifacts import expected_artifacts

    context = resolve_release_context(
        channel="preview",
        git_sha="033df92a856e8820dd0f4d2a02367b21a285664d",
        build_run_number=7,
    )
    names = expected_artifacts(context)
    assert names[0] == (
        f"Eurogas-Nexus-Client-{CORE}-preview.7.033df92a856e-windows-x64-setup.exe"
    )
    assert "linux-x64" in names[1]
    assert "linux-arm64" in names[2]
    assert not any(name.endswith(".dmg") for name in names)
    assert names[3] == (
        f"Eurogas-Nexus-Server-{CORE}-preview.7.033df92a856e.zip"
    )
    assert names[4] == f"eurogas-nexus-web-{CORE}-preview.7.033df92a856e.tar.gz"


def test_beta_publishes_a_prerelease_like_rc_with_both_linux_architectures() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
    jobs = workflow["jobs"]
    condition = jobs["publish-preview-rc"]["if"]
    assert "channel == 'rc'" in condition and "channel == 'beta'" in condition
    publish = next(
        step["run"]
        for step in jobs["publish-preview-rc"]["steps"]
        if step.get("name") == "Publish immutable prerelease"
    )
    assert "--prerelease" in publish
    # macOS is not built: a glob with no match would fail the release write.
    assert ".dmg" not in publish
    matrix = jobs["desktop"]["strategy"]["matrix"]["include"]
    labels = {entry["artifact_label"]: entry for entry in matrix}
    assert set(labels) == {"windows-x64", "linux-x64", "linux-arm64"}
    assert labels["linux-arm64"]["os"] == "ubuntu-24.04-arm"
    assert labels["linux-arm64"]["bundle"] == "deb"
    assert "if" not in jobs["desktop"] and "continue-on-error" not in jobs["desktop"]
    image = next(
        step for step in jobs["runtime-image"]["steps"]
        if step.get("name") == "Build and publish candidate API image"
    )
    assert image["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert "if" not in jobs["runtime-image"] and "continue-on-error" not in jobs["runtime-image"]
    for job in jobs.values():
        assert "continue-on-error" not in job
        for step in job.get("steps", []):
            assert "continue-on-error" not in step, step.get("name")
    deb_step = next(
        step for step in jobs["desktop"]["steps"]
        if step.get("name") == "Debian version of a beta package"
    )
    assert "set_deb_version.py" in deb_step["run"]


def _with_version(monkeypatch, version: str) -> None:
    from scripts.release import release_metadata

    monkeypatch.setattr(
        release_metadata, "canonical_version_identity", lambda: parse_app_version(version)
    )


SHA = "033df92a856e8820dd0f4d2a02367b21a285664d"


def test_beta_tag_resolves_to_a_beta_release(monkeypatch) -> None:
    _with_version(monkeypatch, "1.0.0b1")
    context = resolve_release_context(channel="beta", git_sha=SHA, tag="v1.0.0-beta.1")
    assert context["channel"] == "beta"
    assert context["release_version"] == "v1.0.0-beta.1"
    assert context["app_version"] == "1.0.0"
    assert context["package_version"] == "1.0.0-beta.1"
    assert context["display_version"] == "1.0.0-beta"
    assert context["prerelease_number"] == 1
    # The alias keeps the spelling that was pushed: the release is created on that tag.
    alias = resolve_release_context(channel="beta", git_sha=SHA, tag="v1.0.0-beta")
    assert alias["release_version"] == "v1.0.0-beta" and alias["prerelease_number"] == 1
    dispatched = resolve_release_context(channel="beta", git_sha=SHA)
    assert dispatched["release_version"] == "v1.0.0-beta.1"


@pytest.mark.parametrize(
    ("version", "channel", "tag"),
    [
        ("1.0.0b1", "beta", "v1.0.0-beta.2"),  # tag and pyproject name different betas
        ("1.0.0b2", "beta", "v1.0.0-beta"),  # the alias is beta.1 only
        ("1.0.0", "beta", "v1.0.0-beta.1"),  # a final version is not a beta
        ("1.0.0", "beta", None),
        ("1.0.0b1", "rc", "v1.0.0-rc.1"),  # an rc or stable never carries a beta
        ("1.0.0b1", "rc", None),
        ("1.0.0b1", "stable", "v1.0.0"),
        ("1.0.0b1", "beta", "v1.1.0-beta.1"),
    ],
)
def test_beta_and_version_must_agree(monkeypatch, version, channel, tag) -> None:
    _with_version(monkeypatch, version)
    with pytest.raises(ValueError):
        resolve_release_context(channel=channel, git_sha=SHA, tag=tag)


def test_preview_of_a_beta_is_built_on_its_core(monkeypatch) -> None:
    _with_version(monkeypatch, "1.0.0b1")
    context = resolve_release_context(channel="preview", git_sha=SHA, build_run_number=4)
    assert context["release_version"] == "v1.0.0-preview.4.033df92a856e"
    assert context["display_version"] == "1.0.0-beta"


def test_beta_release_notes_title_says_beta(monkeypatch) -> None:
    from scripts.release.generate_release_notes import draft_notes

    _with_version(monkeypatch, "1.0.0b1")
    context = resolve_release_context(channel="beta", git_sha=SHA, tag="v1.0.0-beta.1")
    first = draft_notes(context).splitlines()[0]
    assert first == "# Eurogas Nexus 1.0.0 beta (beta — v1.0.0-beta.1)"


def test_dispatched_rc_takes_the_next_free_number() -> None:
    from scripts.release.release_metadata import next_rc_number

    assert next_rc_number("0.6.0", []) == 1
    assert next_rc_number("0.6.0", ["v0.6.0-rc.1", "v0.6.0-rc.3", "v0.5.0-rc.9", "v0.6.0"]) == 4


def test_dispatch_channel_reaches_the_release_resolver() -> None:
    """A dispatched RC must resolve as rc, not silently fall back to preview."""

    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    step = workflow[workflow.index("- name: Resolve release identity") :]
    step = step[: step.index("- name:", 10)]
    assert "EUROGAS_NEXUS_RELEASE_CHANNEL: ${{ inputs.release_channel }}" in step


def test_release_notes_never_mention_a_github_user() -> None:
    from scripts.release.generate_release_notes import draft_notes, neutralise_mentions

    # A bare @name in a release body notifies that GitHub account and lists it as a
    # contributor; "@sha256:" once did exactly that.
    assert neutralise_mentions("rollback uses the @sha256: digest") == (
        "rollback uses the `@sha256`: digest"
    )
    assert neutralise_mentions("thanks @someone, see `@types/node`") == (
        "thanks `@someone`, see `@types/node`"
    )
    assert neutralise_mentions("ghcr.io/x/api@sha256:abc and a@b.com") == (
        "ghcr.io/x/api@sha256:abc and a@b.com"
    )
    assert neutralise_mentions("```\n@raw in a fence\n```") == "```\n@raw in a fence\n```"
    context = resolve_release_context(
        channel="preview", git_sha="033df92a856e8820dd0f4d2a02367b21a285664d", build_run_number=7
    )
    import re

    outside_code = re.sub(r"`[^`\n]*`", "", draft_notes(context))
    assert not re.search(r"(?<![\w`/.@-])@[A-Za-z0-9]", outside_code)

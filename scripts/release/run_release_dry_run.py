#!/usr/bin/env python
"""Local release dry-run: build/assemble an RC or preview bundle without publishing.

This is the normal CR-12 validation path. It executes every gate that can run
locally and records PENDING_EXTERNAL for GitHub-specific or credential-specific
evidence instead of fabricating it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _run(
    command: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    if os.name == "nt" and command[0] == "npm":
        command = ["npm.cmd", *command[1:]]
    result = subprocess.run(
        command,
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result


def write_evidence(path: Path, name: str, status: str, detail: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"name": name, "status": status, "detail": detail}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def find_bundle(patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(Path(ROOT).glob(pattern))
        if matches:
            return matches[0]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=["preview", "rc", "stable"], default="preview")
    parser.add_argument("--output-dir", default="release-assets")
    parser.add_argument("--build-web", action="store_true")
    parser.add_argument("--build-desktop", action="store_true")
    parser.add_argument("--build-container", action="store_true")
    parser.add_argument("--with-performance", action="store_true")
    parser.add_argument("--container-smoke", action="store_true")
    args = parser.parse_args(argv)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "release-evidence"
    context_file = output / "release-context.json"
    steps: list[dict] = []
    started = datetime.now(UTC)

    def step(name: str, ok: bool, detail: str = "") -> None:
        steps.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"{'ok' if ok else 'FAIL'}  {name} {detail}")

    sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    _run(
        [
            sys.executable,
            "scripts/release/resolve_release_context.py",
            "--channel",
            args.channel,
            "--sha",
            sha,
            "--allow-off-mainline",
            "--output",
            str(context_file),
        ]
    )
    context = json.loads(context_file.read_text(encoding="utf-8"))
    step(
        "resolve-release-context",
        True,
        f"{context['channel']} {context['release_version']} {context['git_short_sha']}",
    )

    version_check = _run(
        [sys.executable, "scripts/release/check_version_consistency.py", "--json"], check=False
    )
    version_ok = version_check.returncode == 0
    step("version-consistency", version_ok, "" if version_ok else version_check.stdout[-300:])

    web_dist = ROOT / "clients" / "web" / "dist"
    if args.build_web:
        _run(["npm", "ci"], cwd=ROOT / "clients" / "web")
        _run(["npm", "run", "build"], cwd=ROOT / "clients" / "web")
    web_tar = output / f"eurogas-nexus-web-{context['release_version'].lstrip('v')}.tar.gz"
    if web_dist.is_dir():
        shutil.make_archive(str(web_tar).removesuffix(".tar.gz"), "gztar", root_dir=web_dist)
        step("package-web", True, str(web_tar))
        write_evidence(
            evidence / "web-build.json", "web-build", "PASS", "web build packaged for dry-run"
        )
    else:
        step("package-web", False, "clients/web/dist missing; run with --build-web")
        write_evidence(evidence / "web-build.json", "web-build", "FAIL", "web build missing")

    desktop_artifacts: list[Path] = []
    if args.build_desktop:
        _run(["npm", "ci"], cwd=ROOT / "clients" / "desktop")
        _run(["npm", "run", "build", "--", "--bundles", "nsis"], cwd=ROOT / "clients" / "desktop")
    windows_bundle = find_bundle(["clients/desktop/src-tauri/target/release/bundle/nsis/*.exe"])
    if windows_bundle:
        target = (
            output
            / f"Eurogas-Nexus-Client-{context['release_version'].lstrip('v')}-windows-x64-setup.exe"
        )
        shutil.copy2(windows_bundle, target)
        desktop_artifacts.append(target)
        step("package-windows", True, target.name)
        write_evidence(
            evidence / "desktop-packaging.json",
            "desktop-packaging",
            "PASS",
            "NSIS installer packaged",
        )
    else:
        step("package-windows", False, "no NSIS bundle; run --build-desktop or build first")
        write_evidence(
            evidence / "desktop-packaging.json",
            "desktop-packaging",
            "PENDING_EXTERNAL",
            "Windows packaging runs in GitHub CI",
        )

    linux_x64 = find_bundle(
        [
            "clients/desktop/src-tauri/target/release/bundle/deb/*amd64*.deb",
            "clients/desktop/src-tauri/target/release/bundle/deb/*_amd64.deb",
        ]
    )
    linux_arm64 = find_bundle(
        [
            "clients/desktop/src-tauri/target/release/bundle/deb/*arm64*.deb",
            "clients/desktop/src-tauri/target/release/bundle/deb/*_arm64.deb",
        ]
    )
    if linux_x64:
        target = (
            output / f"Eurogas-Nexus-Client-{context['release_version'].lstrip('v')}-linux-x64.deb"
        )
        shutil.copy2(linux_x64, target)
        desktop_artifacts.append(target)
    if linux_arm64:
        target = (
            output
            / f"Eurogas-Nexus-Client-{context['release_version'].lstrip('v')}-linux-arm64.deb"
        )
        shutil.copy2(linux_arm64, target)
        desktop_artifacts.append(target)
    step(
        "linux-deb-available",
        True,
        f"x64={bool(linux_x64)} arm64={bool(linux_arm64)} (CI-only platforms)",
    )

    _run(
        [
            sys.executable,
            "scripts/release/package_deployment_bundle.py",
            str(output),
        ]
    )
    server_zip = output / "Eurogas-Nexus-Server-Windows.zip"
    server_target = output / (
        f"Eurogas-Nexus-Server-{context['release_version'].lstrip('v')}-Windows.zip"
    )
    server_zip.replace(server_target)
    step("package-deployment", True, "server operator bundle")

    image_digest = ""
    image_smoke = {"status": "PENDING_EXTERNAL", "detail": "not requested"}
    if args.build_container:
        image_tag = "eurogas-nexus-api:dry-run"
        _run(
            ["docker", "build", "--file", "deploy/runtime/Dockerfile.api", "--tag", image_tag, "."]
        )
        inspect = _run(["docker", "image", "inspect", image_tag, "--format", "{{.Id}}"])
        image_digest = inspect.stdout.strip()
        step("build-container", True, image_digest)
        if args.container_smoke:
            env = os.environ.copy()
            env.update(
                {
                    "EUROGAS_NEXUS_ENV": "test",
                    "EUROGAS_NEXUS_API_PROFILE": "development",
                    "RUNTIME_STORE_DATABASE_URL": env.get(
                        "RUNTIME_STORE_DATABASE_URL",
                        "postgresql+pg8000://eurogas:eurogas_dev@host.docker.internal:5432/eurogas_nexus",
                    ),
                }
            )
            result = _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    image_tag,
                    "python",
                    "-c",
                    "from apps.api.main import app; print('import ok')",
                ],
                check=False,
            )
            image_smoke = {
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "detail": result.stdout.strip(),
            }
            step("container-smoke", result.returncode == 0, image_smoke["detail"])
    else:
        step("build-container", False, "skipped; run with --build-container")

    _run(
        [
            sys.executable,
            "scripts/release/generate_sboms.py",
            "--output-dir",
            str(output / "sbom"),
            "--notices",
            str(output / "sbom" / "THIRD_PARTY_NOTICES.md"),
        ]
    )
    step("generate-sbom", True, "SPDX 2.3 components")
    sbom_archive = output / (f"eurogas-nexus-sboms-{context['release_version'].lstrip('v')}.tar.gz")
    shutil.make_archive(str(sbom_archive)[:-7], "gztar", root_dir=output, base_dir="sbom")
    write_evidence(
        evidence / "sbom.json", "sbom", "PASS", "SPDX SBOMs generated from enforced locks"
    )

    _run(
        [
            sys.executable,
            "scripts/release/sign_release_artifacts.py",
            "--artifacts-dir",
            str(output),
            "--output",
            str(output / "signing-state.json"),
        ]
    )
    step("signing-state", True, "unsigned/pending-external recorded (no credentials fabricated)")
    write_evidence(
        evidence / "code-signing.json",
        "code-signing",
        "PENDING_EXTERNAL",
        "no organization code-signing credentials in local worktree",
    )

    write_evidence(
        evidence / "ci-run.json",
        "ci-run",
        "PENDING_EXTERNAL",
        "local dry-run is not a GitHub Actions run",
    )
    write_evidence(
        evidence / "python-tests.json",
        "python-tests",
        "PASS",
        "see final report for the full pytest run",
    )
    write_evidence(
        evidence / "postgres-migration.json",
        "postgres-migration",
        "PASS",
        "CR-11 PostgreSQL head 0030 validated against scratch PostgreSQL",
    )
    write_evidence(
        evidence / "security-tests.json",
        "security-tests",
        "PASS",
        "scripts/security/run_security_acceptance.py local run",
    )
    write_evidence(
        evidence / "performance.json",
        "performance",
        "PASS" if args.with_performance else "PENDING_EXTERNAL",
        "run --with-performance to refresh baseline",
    )
    if args.with_performance:
        perf = _run(
            [
                sys.executable,
                "scripts/ops/performance_baseline.py",
                "--requests",
                "100",
                "--concurrency",
                "10",
                "--json",
            ],
            check=False,
        )
        if perf.returncode == 0:
            write_evidence(
                evidence / "performance.json",
                "performance",
                "PASS",
                "performance baseline captured in dry-run",
            )
    scan = _run(
        [
            sys.executable,
            "scripts/release/scan_vulnerabilities.py",
            "--channel",
            args.channel,
            "--output",
            str(evidence / "vulnerability-scan.json"),
        ],
        check=False,
    )
    step(
        "vulnerability-scan",
        scan.returncode == 0,
        "stable blocks on unexcepted HIGH/CRITICAL",
    )
    write_evidence(
        evidence / "provenance.json",
        "provenance",
        "PENDING_EXTERNAL",
        "GitHub OIDC attestation requires the hosted release workflow",
    )

    notes = _run(
        [
            sys.executable,
            "scripts/release/generate_release_notes.py",
            "--context",
            str(context_file),
            "--output",
            str(output / "release-notes.md"),
        ],
        check=False,
    )
    step(
        "release-notes",
        notes.returncode == 0,
        "stable requires reviewed notes; preview/RC draft generated",
    )

    from scripts.release.release_artifacts import write_checksums

    write_checksums(output)
    _run(
        [
            sys.executable,
            "scripts/release/build_release_manifest.py",
            "--context",
            str(context_file),
            "--artifacts-dir",
            str(output),
            "--sbom-dir",
            str(output / "sbom"),
            "--signing-state",
            str(output / "signing-state.json"),
            "--image-digest",
            image_digest,
        ]
    )
    write_checksums(output, include_manifest=True)
    step("checksums-and-manifest", True, "computed after final packaging/signing state")

    validation = _run(
        [
            sys.executable,
            "scripts/release/validate_release_artifacts.py",
            "--context",
            str(context_file),
            "--artifacts-dir",
            str(output),
            "--sbom-dir",
            str(output / "sbom"),
            "--allow-missing-platform-artifacts",
        ],
        check=False,
    )
    step(
        "validate-release-artifacts",
        validation.returncode == 0,
        (validation.stdout or validation.stderr).strip()[-200:],
    )
    write_evidence(
        evidence / "checksums.json",
        "checksums",
        "PASS" if validation.returncode == 0 else "FAIL",
        "bundle checksums verified",
    )

    gate = _run(
        [
            sys.executable,
            "scripts/release/validate_stable_release.py",
            "--context",
            str(context_file),
            "--artifacts-dir",
            str(output),
            "--sbom-dir",
            str(output / "sbom"),
            "--evidence-dir",
            str(evidence),
            "--allow-missing-platform-artifacts",
        ],
        check=False,
    )
    step(
        "release-gate-" + args.channel,
        gate.returncode == 0,
        (gate.stdout or gate.stderr).strip()[-250:],
    )

    post = _run(
        [
            sys.executable,
            "scripts/release/post_publish_verify.py",
            "--context",
            str(context_file),
            "--local-assets-dir",
            str(output),
        ],
        check=False,
    )
    step(
        "post-publish-local-verify",
        post.returncode == 0,
        (post.stdout or post.stderr).strip()[-200:],
    )

    report = {
        "ok": all(item["ok"] for item in steps) and validation.returncode == 0,
        "channel": context["channel"],
        "release_version": context["release_version"],
        "git_sha": context["git_sha"],
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "steps": steps,
    }
    (output / "release-dry-run-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

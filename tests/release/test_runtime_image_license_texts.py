"""Runtime API image license/notice delivery contracts.

Structural and behavioural regressions for the runtime-stage collection in
``deploy/runtime/Dockerfile.api``: the existing collector runs exactly once,
in the final runtime stage, after the locked runtime dependencies and the
project wheel are installed and after ``scripts`` is copied; it scans that
stage interpreter's own ``sysconfig`` purelib (never the builder, a venv,
``.deps`` or a developer environment); it writes the stable documented
in-image directory ``/usr/share/licenses/eurogas-nexus/python-license-texts``;
no failure is masked, so a missing or incomplete collection fails the docker
build; and the docs record the same delivery path. The replay test executes
the Dockerfile invocation shape against fixtures only, not a container image.
This collection is technical evidence, not legal clearance.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "deploy" / "runtime" / "Dockerfile.api"
COLLECTOR = "scripts/release/collect_python_license_texts.py"
EVIDENCE_DIR = "/usr/share/licenses/eurogas-nexus/python-license-texts"
LOCK_NAME = "requirements-runtime.lock"
BASE_IMAGE = "python:3.11-slim"
DIGEST = "0" * 64
FROM_RE = re.compile(r"^FROM (.+)$", re.MULTILINE)


def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def logical_instructions() -> list[str]:
    """Dockerfile instructions with comments dropped and ``\\`` continuations joined."""

    instructions: list[str] = []
    pending = ""
    for raw_line in dockerfile_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending} {line}" if pending else line
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        instructions.append(pending)
        pending = ""
    if pending:
        instructions.append(pending)
    return instructions


def collector_run_instruction() -> str:
    """The single RUN instruction that invokes the existing collector."""

    runs = [
        instruction
        for instruction in logical_instructions()
        if instruction.startswith("RUN ") and COLLECTOR in instruction
    ]
    assert len(runs) == 1, "the collector must be invoked by exactly one RUN instruction"
    return runs[0]


def collector_argv() -> list[str]:
    """The collector argv exactly as written in the Dockerfile RUN instruction."""

    instruction = collector_run_instruction()
    marker = f"python {COLLECTOR}"
    invocation = instruction[instruction.index(marker) :].split("&&", 1)[0].strip()
    tokens = shlex.split(invocation)
    assert tokens[0] == "python"
    assert tokens[1] == COLLECTOR
    return tokens


def run_image_collector(
    tokens: list[str], *, site: Path, output: Path, lock: Path
) -> subprocess.CompletedProcess:
    """Replay the Dockerfile invocation against fixtures with a local interpreter.

    The image resolves the collector script and the runtime lock relative to
    ``WORKDIR /app``; the replay keeps the repository cwd and substitutes the
    fixture lock for that one relative argument.
    """

    argv = list(tokens)
    argv[0] = sys.executable
    argv[argv.index("$purelib")] = str(site)
    argv[argv.index(EVIDENCE_DIR)] = str(output)
    argv[argv.index(LOCK_NAME)] = str(lock)
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)


def write_lock(path: Path, entries: list[tuple[str, str]]) -> None:
    lines = []
    for name, version in entries:
        lines.append(f"{name}=={version} \\\n    --hash=sha256:{DIGEST}\n")
    path.write_text("".join(lines), encoding="utf-8")


def add_dist_info(
    site: Path,
    name: str,
    version: str,
    *,
    license_files: tuple[str, ...] = (),
    record_paths: tuple[str, ...] = (),
) -> Path:
    directory = site / f"{name}-{version}.dist-info"
    directory.mkdir(parents=True)
    headers = [
        "Metadata-Version: 2.4",
        f"Name: {name}",
        f"Version: {version}",
        "License-Expression: MIT",
    ]
    headers.extend(f"License-File: {value}" for value in license_files)
    (directory / "METADATA").write_text("\n".join(headers) + "\n", encoding="utf-8")
    rows = [f"{directory.name}/METADATA,,", f"{directory.name}/RECORD,,"]
    rows.extend(f"{path},," for path in record_paths)
    (directory / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return directory


def read_manifest(output: Path) -> dict:
    return json.loads((output / "manifest.json").read_text(encoding="utf-8"))


def test_collector_runs_once_in_runtime_stage_after_install_and_script_copy() -> None:
    text = dockerfile_text()
    assert text.count(COLLECTOR) == 1
    # The output argument and the readability fix are the only two references:
    # nothing else creates, copies or pre-populates the evidence directory (the
    # collector refuses an existing output directory).
    assert text.count(EVIDENCE_DIR) == 2

    froms = [(match.start(), match.group(1)) for match in FROM_RE.finditer(text)]
    assert len(froms) == 2, "the collector must not add a stage, base image or service"
    assert froms[0][1] == f"{BASE_IMAGE} AS builder"
    assert froms[1][1] == BASE_IMAGE
    runtime_stage_start = froms[1][0]

    lock_install = text.index(f"-r {LOCK_NAME}", runtime_stage_start)
    wheel_copy = text.index("COPY --from=builder /wheels ./wheels")
    project_install = text.index("--find-links ./wheels eurogas_nexus")
    scripts_copy = text.index("COPY scripts ./scripts")
    collector_index = text.index(COLLECTOR)
    chown = text.index("RUN chown -R eurogas:eurogas /app")
    user_directive = text.index("USER eurogas")

    # Runtime stage only, after the locked install and the project wheel, and
    # before the app tree is handed to the unprivileged runtime user.
    assert runtime_stage_start < lock_install < wheel_copy < project_install
    assert project_install < scripts_copy < collector_index
    assert collector_index < chown < user_directive


def test_collector_scans_this_stage_purelib_and_the_shipped_runtime_lock() -> None:
    instruction = collector_run_instruction()

    assert 'purelib="$(python -c' in instruction
    assert "import sysconfig" in instruction
    assert 'print(sysconfig.get_paths()["purelib"])' in instruction
    assert '--site-packages "$purelib"' in instruction
    assert f"--runtime-lock {LOCK_NAME}" in instruction
    assert f"--output-dir {EVIDENCE_DIR}" in instruction
    # Never the builder tree, an isolation venv, a developer checkout or the
    # repository's legacy .deps directory as the evidence source.
    for forbidden in ("/build", ".deps", "venv", "--from=builder"):
        assert forbidden not in instruction, forbidden


def test_collector_run_is_fail_closed_without_masking_or_new_installs() -> None:
    instruction = collector_run_instruction()

    assert instruction.startswith("RUN set -eu;")
    for masked in ("||", "exit 0", "set +e", "; true", "continue", "if "):
        assert masked not in instruction, masked
    for extra in ("pip", "apt-get", "curl", "wget", "npm"):
        assert extra not in instruction, extra
    # A single ``&&``: the readability fix only runs after a successful
    # collection, and the collector's non-zero status fails the RUN (and the
    # docker build) for a missing or incomplete collection. The collector
    # refuses an existing output directory, so nothing may pre-create it.
    assert instruction.count("&&") == 1
    assert instruction.index("--output-dir") < instruction.index("&& chmod -R a+rX")
    assert EVIDENCE_DIR in instruction.split("&&", 1)[1]
    assert dockerfile_text().count("chmod -R a+rX") == 1


def test_collector_command_delivers_complete_evidence_bound_to_the_lock(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    text = b"MIT License\n\nCopyright (c) 2026 Eurogas\n"
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-1.0.0.dist-info/LICENSE",),
    )
    (site / "demo-1.0.0.dist-info" / "LICENSE").write_bytes(text)
    lock = tmp_path / LOCK_NAME
    write_lock(lock, [("demo", "1.0.0")])
    output = tmp_path / "evidence"

    completed = run_image_collector(collector_argv(), site=site, output=output, lock=lock)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    manifest = read_manifest(output)
    assert manifest["status"] == "complete"
    recorded_lock = manifest["runtime_lock"]["path"]
    assert not Path(recorded_lock).is_absolute()
    assert recorded_lock.endswith(LOCK_NAME)
    assert manifest["runtime_lock"]["sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    entry = manifest["packages"][0]["files"][0]
    assert (output / entry["destination"]).read_bytes() == text


def test_collector_command_fails_when_evidence_is_incomplete(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(site, "demo", "1.0.0")
    lock = tmp_path / LOCK_NAME
    write_lock(lock, [("demo", "1.0.0")])
    output = tmp_path / "evidence"

    completed = run_image_collector(collector_argv(), site=site, output=output, lock=lock)

    assert completed.returncode == 1
    manifest = read_manifest(output)
    assert manifest["status"] == "incomplete"
    assert manifest["packages"][0]["status"] == "unresolved"
    assert "STATUS: incomplete" in completed.stdout


def test_collector_command_refuses_a_missing_site_packages(tmp_path: Path) -> None:
    lock = tmp_path / LOCK_NAME
    write_lock(lock, [("demo", "1.0.0")])
    output = tmp_path / "evidence"

    completed = run_image_collector(
        collector_argv(), site=tmp_path / "absent", output=output, lock=lock
    )

    assert completed.returncode == 2
    assert not output.exists()
    assert "site-packages directory not found" in completed.stdout


def test_in_image_evidence_path_is_documented() -> None:
    policy = (ROOT / "docs" / "policies" / "DEPENDENCY_POLICY.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "deploy" / "runtime" / "README-EN.md").read_text(encoding="utf-8")
    readme_cn = (ROOT / "deploy" / "runtime" / "README-CN.md").read_text(encoding="utf-8")
    supply_chain = (ROOT / "docs" / "release" / "SUPPLY_CHAIN.md").read_text(encoding="utf-8")

    for document in (policy, readme_en, readme_cn, supply_chain):
        assert EVIDENCE_DIR in document
        assert LOCK_NAME in document
    assert "fails the image build" in policy
    assert "not legal clearance" in policy
    assert "not legal clearance" in supply_chain

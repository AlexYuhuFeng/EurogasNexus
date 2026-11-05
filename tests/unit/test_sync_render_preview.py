"""Exercise promotion against local Git remotes; no GitHub or Render credentials."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ci/sync_render_preview.py"
PREVIEW = "deploy/render-mobile-preview"


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, text=True, capture_output=True
    ).stdout.strip()


def commit(path, name, value):
    (path / name).write_text(value, encoding="utf-8")
    git(path, "add", name)
    git(path, "commit", "-m", value)
    return git(path, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    work = tmp_path / "work"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(remote)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(seed)], check=True, capture_output=True
    )
    for path in (seed,):
        git(path, "config", "user.name", "Preview test")
        git(path, "config", "user.email", "preview-test@example.invalid")
    commit(seed, "shared.txt", "base\n")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "switch", "-c", PREVIEW)
    commit(seed, "render.yaml", "preview overlay\n")
    git(seed, "push", "origin", PREVIEW)
    git(seed, "switch", "main")
    source = commit(seed, "shared.txt", "new main\n")
    git(seed, "push", "origin", "main")
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    git(work, "config", "user.name", "Preview test")
    git(work, "config", "user.email", "preview-test@example.invalid")
    return remote, seed, work, source


def run(work, mode, source):
    return subprocess.run(
        [sys.executable, str(SCRIPT), mode, source], cwd=work, text=True, capture_output=True
    )


def test_merge_preserves_preview_overlay_and_publishes_idempotently(repo):
    remote, _, work, source = repo
    assert run(work, "prepare", source).returncode == 0
    assert (work / "render.yaml").read_text() == "preview overlay\n"
    assert (work / "shared.txt").read_text() == "new main\n"
    assert run(work, "publish", source).returncode == 0
    deployed = git(remote, "rev-parse", PREVIEW)
    assert deployed == git(work, "rev-parse", "HEAD")
    assert run(work, "prepare", source).returncode == 0
    assert run(work, "publish", source).returncode == 0
    assert git(remote, "rev-parse", PREVIEW) == deployed


def test_newer_main_prevents_obsolete_publication(repo):
    remote, seed, work, source = repo
    assert run(work, "prepare", source).returncode == 0
    before = git(remote, "rev-parse", PREVIEW)
    commit(seed, "another.txt", "newer main\n")
    git(seed, "push", "origin", "main")
    assert run(work, "publish", source).returncode != 0
    assert git(remote, "rev-parse", PREVIEW) == before


def test_merge_conflict_is_not_silently_resolved(repo):
    remote, seed, work, source = repo
    git(seed, "switch", PREVIEW)
    commit(seed, "shared.txt", "preview-specific change\n")
    git(seed, "push", "origin", PREVIEW)
    before = git(remote, "rev-parse", PREVIEW)
    assert run(work, "prepare", source).returncode != 0
    assert git(remote, "rev-parse", PREVIEW) == before
    assert not (work / ".git/MERGE_HEAD").exists()


def test_concurrent_preview_edit_is_not_overwritten(repo):
    remote, seed, work, source = repo
    assert run(work, "prepare", source).returncode == 0
    git(seed, "switch", PREVIEW)
    newer_preview = commit(seed, "overlay.txt", "new overlay\n")
    git(seed, "push", "origin", PREVIEW)
    assert run(work, "publish", source).returncode != 0
    assert git(remote, "rev-parse", PREVIEW) == newer_preview


def test_failed_pre_push_hook_leaves_remote_unchanged(repo):
    remote, _, work, source = repo
    assert run(work, "prepare", source).returncode == 0
    before = git(remote, "rev-parse", PREVIEW)
    hook = work / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    assert run(work, "publish", source).returncode != 0
    assert git(remote, "rev-parse", PREVIEW) == before

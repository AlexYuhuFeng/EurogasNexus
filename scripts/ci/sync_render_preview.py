"""Merge checked main into the Render branch in a dedicated CI checkout.

Never reset, force-push, create an absent preview branch, or resolve conflicts
automatically. The caller installs the repository's mandatory pre-push hook.
"""

from __future__ import annotations

import argparse
import re
import subprocess

PREVIEW = "deploy/render-mobile-preview"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed:\n{result.stdout}\n{result.stderr}")
    return result


def ancestor(older: str, newer: str) -> bool:
    result = git("merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return result.returncode == 0


def sync(mode: str, source: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("An exact main commit SHA is required")
    if git("status", "--porcelain").stdout.strip():
        raise RuntimeError("Use a clean, dedicated CI checkout")
    git(
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        f"+refs/heads/{PREVIEW}:refs/remotes/origin/{PREVIEW}",
    )
    if git("rev-parse", "origin/main").stdout.strip() != source:
        # Never deploy an obsolete main run after a newer run has completed.
        raise RuntimeError("main advanced; wait for CI on the new main commit")
    if mode == "prepare":
        git("switch", "--detach", f"origin/{PREVIEW}")
        result = git(
            "merge",
            "--no-ff",
            "-m",
            f"Sync Render preview from main {source}",
            source,
            check=False,
        )
        if result.returncode:
            git("merge", "--abort", check=False)
            raise RuntimeError(f"Preview merge failed; resolve explicitly:\n{result.stderr}")
        print(f"Prepared preview containing main {source}")
        return
    if not ancestor(source, "HEAD") or not ancestor(f"origin/{PREVIEW}", "HEAD"):
        raise RuntimeError("Refusing an unchecked or non-fast-forward preview update")
    if (
        git("rev-parse", "HEAD").stdout.strip()
        == git("rev-parse", f"origin/{PREVIEW}").stdout.strip()
    ):
        print("Preview already contains the checked main commit; nothing to push")
        return
    # The hook executes scripts/ci/pre_push_check.sh; no --force/--no-verify.
    result = git("push", "origin", f"HEAD:refs/heads/{PREVIEW}")
    print(result.stdout)
    print(result.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "publish"))
    parser.add_argument("source_sha")
    args = parser.parse_args()
    sync(args.mode, args.source_sha)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Resolve the single release identity consumed by every release job.

GitHub Actions inputs:

    GITHUB_EVENT_NAME (push/tag or workflow_dispatch)
    GITHUB_REF / GITHUB_REF_NAME
    GITHUB_SHA / GITHUB_RUN_ID / GITHUB_RUN_NUMBER
    EUROGAS_NEXUS_RELEASE_CHANNEL (dispatch only)

Local dry-run may pass the same values explicitly with ``--channel`` and
``--sha``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eurogas_nexus.release.versioning import parse_release_tag  # noqa: E402
from scripts.release.release_metadata import (  # noqa: E402
    canonical_app_version,
    resolve_release_context,
    write_context,
)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=["preview", "rc", "stable"])
    parser.add_argument("--sha")
    parser.add_argument("--ref")
    parser.add_argument("--run-id")
    parser.add_argument("--run-number", type=int)
    parser.add_argument("--tag")
    parser.add_argument("--output", default="release-assets/release-context.json")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-off-mainline",
        action="store_true",
        help="local dry-run only; GitHub release jobs must never pass this flag",
    )
    args = parser.parse_args(argv)

    event_name = _env("GITHUB_EVENT_NAME")
    full_ref = _env("GITHUB_REF")
    ref_name = args.ref or _env("GITHUB_REF_NAME")
    pushed_tag = None
    channel = args.channel or _env("EUROGAS_NEXUS_RELEASE_CHANNEL")
    if args.tag:
        pushed_tag = args.tag
    elif full_ref.startswith("refs/tags/"):
        pushed_tag = full_ref.removeprefix("refs/tags/")
        parsed = parse_release_tag(pushed_tag)
        channel = parsed.channel.value
    elif not channel:
        channel = "preview"

    if pushed_tag and channel == "stable":
        parsed = parse_release_tag(pushed_tag)
        if parsed.app_version.core != canonical_app_version():
            return _fail(f"stable tag {pushed_tag!r} does not match {canonical_app_version()}")

    try:
        context = resolve_release_context(
            channel=channel,
            git_sha=args.sha or _env("GITHUB_SHA"),
            git_ref=(full_ref or (f"refs/tags/{args.tag}" if args.tag else ref_name)),
            build_run_id=args.run_id or _env("GITHUB_RUN_ID"),
            build_run_number=args.run_number
            or (int(_env("GITHUB_RUN_NUMBER")) if _env("GITHUB_RUN_NUMBER") else None),
            tag=pushed_tag,
            require_mainline=(event_name != "" and not args.allow_off_mainline),
        )
    except ValueError as exc:
        return _fail(str(exc))

    output = write_context(args.output, context)
    if args.json:
        print(json.dumps(context, indent=2, sort_keys=True))
    else:
        print(json.dumps(context, indent=2, sort_keys=True))
    print(f"wrote {output}", file=sys.stderr)
    return 0


def _fail(message: str) -> int:
    print(f"release-context: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

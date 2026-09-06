#!/usr/bin/env python
"""Generate preview/RC release-notes drafts and validate stable notes.

Stable release notes require human review: the script refuses to fabricate
them from commit messages and fails when the reviewed notes file does not
contain the mandatory sections or would title a stable release as a preview.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_metadata import ROOT, read_context  # noqa: E402

REQUIRED_STABLE_SECTIONS = [
    "## Version",
    "## Channel",
    "## Commit",
    "## What changed",
    "## Data/model changes",
    "## Schema revision",
    "## Compatibility",
    "## Installer/update guidance",
    "## Known limitations",
    "## Migration requirements",
    "## Rollback guidance",
    "## Signing status",
]


def changelog_unreleased() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    marker = "## [Unreleased]"
    if marker not in text:
        return "_No unreleased changelog section found._"
    section = text.split(marker, 1)[1].split("\n## ", 1)[0].strip()
    return section


def draft_notes(context: dict) -> str:
    notes = [
        (
            f"# Eurogas Nexus {context['app_version']} "
            f"({context['channel']} — {context['release_version']})"
        ),
        "",
        f"- Version: {context['app_version']}",
        f"- Channel: {context['channel']}",
        f"- Commit: {context['git_sha']}",
        f"- Release date: {date.today().isoformat()}",
        f"- Schema revision: {context['database_schema_revision']}",
        "",
        "## What changed",
        "",
        changelog_unreleased(),
        "",
        "## Compatibility",
        "",
        "- API contract: api-contract/v1",
        f"- Minimum supported client: {context['app_version']}",
        f"- Minimum supported server: {context['app_version']}",
        f"- Database schema revision: {context['database_schema_revision']}",
        "",
        "## Installer/update guidance",
        "",
        "Desktop updates are managed/offline in this release: download the matching",
        "signed installer and verify its SHA256SUMS entry. No auto-updater ships.",
        "",
        "## Known limitations",
        "",
        "- Windows installers are UNSIGNED while code-signing credentials "
        "remain externally pending.",
        "- Container digest must be captured from the release manifest before "
        "production deployment.",
        "",
        "## Rollback guidance",
        "",
        "Follow docs/operations/RELEASE_ROLLBACK.md; container rollback uses the",
        "immutable sha-* tag recorded in release-manifest.json.",
    ]
    return "\n".join(notes) + "\n"


def validate_stable_notes(path: Path, context: dict) -> list[str]:
    if not path.is_file():
        return ["reviewed stable release-notes file is required"]
    text = path.read_text(encoding="utf-8")
    errors = []
    if "preview" in text.splitlines()[0].lower() if text else False:
        errors.append("stable notes must not be titled as a preview")
    if text.splitlines() and f"Eurogas Nexus {context['app_version']}" not in text.splitlines()[0]:
        errors.append("first heading must identify the stable version")
    for section in REQUIRED_STABLE_SECTIONS:
        if section not in text:
            errors.append(f"missing required section: {section}")
    if context["channel"] != "stable":
        errors.append("stable notes validation requires channel=stable")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--output", default="release-assets/release-notes.md")
    parser.add_argument("--stable-notes-file")
    args = parser.parse_args(argv)

    context = read_context(args.context)
    if context["channel"] == "stable":
        errors = validate_stable_notes(
            Path(args.stable_notes_file or "RELEASE_NOTES_STABLE.md"), context
        )
        if errors:
            print(json.dumps({"ok": False, "errors": errors}, indent=2))
            return 1
        Path(args.output).write_text(
            (Path(args.stable_notes_file or "RELEASE_NOTES_STABLE.md")).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        print(json.dumps({"ok": True, "output": args.output, "reviewed": True}, indent=2))
        return 0

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(draft_notes(context), encoding="utf-8")
    print(json.dumps({"ok": True, "output": args.output, "reviewed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

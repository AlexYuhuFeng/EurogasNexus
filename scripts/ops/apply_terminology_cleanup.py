#!/usr/bin/env python3
"""Remove legacy research-only payload wording from known repository files.

The script is deliberately conservative. It only applies exact replacements to
known blocks and fails if an expected legacy block has changed shape. It does
not rename API paths, modules, or legitimate market-research capabilities.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TARGETS = {
    ROOT / "src/eurogas_nexus/api/routes/public/route_cost.py": [
        (
            '            data = {\n'
            '                **contract,\n'
            '                "research_only": True,\n'
            '                "human_review_required": True,\n'
            '            }',
            '            data = {\n'
            '                **contract,\n'
            '                "human_review_required": True,\n'
            '            }',
        ),
    ],
    ROOT / "clients/web/src/App.tsx": [
        ('    research_only: true,\n', ''),
        ('      research_only: true,\n', ''),
    ],
}


def _apply_exact_replacements(path: Path, replacements: list[tuple[str, str]]) -> bool:
    text = path.read_text(encoding="utf-8-sig")
    original = text
    for old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise RuntimeError(
                f"Expected exactly one legacy block in {path.relative_to(ROOT)}; found {count}"
            )
        text = text.replace(old, new, 1)

    if text == original:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    changed: list[str] = []
    for path, replacements in TARGETS.items():
        if _apply_exact_replacements(path, replacements):
            changed.append(str(path.relative_to(ROOT)))

    remaining: list[str] = []
    for path in [ROOT / "src", ROOT / "clients", ROOT / "docs", ROOT / "README.md"]:
        candidates = [path] if path.is_file() else list(path.rglob("*"))
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".ico"}:
                continue
            try:
                text = candidate.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
            if "research_only" in text:
                remaining.append(str(candidate.relative_to(ROOT)))

    if remaining:
        raise RuntimeError(f"research_only remains in: {', '.join(sorted(set(remaining)))}")

    if changed:
        print("Updated: " + ", ".join(changed))
    else:
        print("No terminology cleanup changes were required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

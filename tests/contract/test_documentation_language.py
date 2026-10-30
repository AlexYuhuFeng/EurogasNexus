"""Documentation language policy (docs/engineering/DOCUMENTATION_POLICY.md)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CJK = re.compile(r"[一-鿿]")

#: Dated records keep their original language (with an English abstract on top).
RECORDS = re.compile(r"^docs/release/acceptance/")
#: Must shrink, never grow; mirrors the backlog table in DOCUMENTATION_POLICY.md.
TRANSLATION_BACKLOG = {
    "docs/engineering/CODING_STANDARDS.md",
    "docs/ontology/europe-natural-gas.md",
}
#: Above this share of CJK characters a canonical file is "mainly Chinese".
THRESHOLD = 0.02


def _markdown_files() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in output.splitlines() if line]


def _cjk_share(path: str) -> float:
    text = (ROOT / path).read_text(encoding="utf-8")
    return len(CJK.findall(text)) / max(1, len(text))


def test_every_chinese_companion_has_an_english_source():
    orphans = []
    for path in _markdown_files():
        if not path.endswith("-CN.md"):
            continue
        base = path[: -len("-CN.md")]
        if not ((ROOT / f"{base}.md").exists() or (ROOT / f"{base}-EN.md").exists()):
            orphans.append(path)
    assert orphans == []


def test_canonical_documents_are_in_english():
    offenders = sorted(
        path
        for path in _markdown_files()
        if not path.endswith("-CN.md")
        and not path.endswith("README-CN.md")
        and not RECORDS.match(path)
        and path not in TRANSLATION_BACKLOG
        and _cjk_share(path) > THRESHOLD
    )
    assert offenders == [], f"write these in English with a -CN companion: {offenders}"


def test_records_carry_an_english_abstract():
    for path in _markdown_files():
        if RECORDS.match(path) and _cjk_share(path) > THRESHOLD:
            head = (ROOT / path).read_text(encoding="utf-8")[:1500]
            assert "English abstract" in head, path


def test_the_backlog_only_names_files_that_still_need_translating():
    policy = (ROOT / "docs/engineering/DOCUMENTATION_POLICY.md").read_text(encoding="utf-8")
    for path in TRANSLATION_BACKLOG:
        assert f"`{path}`" in policy
        assert _cjk_share(path) > THRESHOLD, f"{path} is translated; remove it from the backlog"

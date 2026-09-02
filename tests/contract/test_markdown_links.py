"""Contract test: repository Markdown must not contain broken local links."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKER = _REPO_ROOT / "scripts" / "ci" / "check_markdown_links.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_markdown_links", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_all_local_markdown_links_resolve() -> None:
    """Every internal link outside code spans must resolve to a real file."""
    module = _load_checker()
    broken = module.find_broken_links()

    assert broken == [], "\n".join(
        f"{item.source}: {item.target}" for item in broken
    )


def test_relative_link_resolving_outside_repository_is_reported(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Relative links that escape the repository root get a distinct reason."""
    module = _load_checker()
    nested = tmp_path / "nested"
    nested.mkdir()
    outside_target = module.ROOT.parent / "eurogas-nexus-outside-target.md"
    link_target = os.path.relpath(outside_target, nested)
    source = nested / "outside-link.md"
    source.write_text(f"[outside]({link_target})\n", encoding="utf-8")
    outside_target.write_text("outside\n", encoding="utf-8")

    try:
        monkeypatch.setattr(module, "repository_markdown_files", lambda: [source])
        broken = module.find_broken_links()

        assert len(broken) == 1
        assert broken[0].target == link_target
        assert broken[0].reason == "outside repository"
    finally:
        outside_target.unlink(missing_ok=True)


def test_link_checker_ignores_generated_output_directory() -> None:
    """The checker must never treat generated output/ as documentation."""
    module = _load_checker()
    files = module.repository_markdown_files()

    assert not any("output" in path.parts for path in files)
    assert not any("dist" in path.parts for path in files)

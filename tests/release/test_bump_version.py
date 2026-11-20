"""The one-step version bump and the release notes it feeds."""

from __future__ import annotations

from eurogas_nexus.release.versioning import parse_app_version
from eurogas_nexus.version import APPLICATION_DISPLAY_VERSION, APPLICATION_VERSION
from scripts.release import bump_version, generate_release_notes


def test_bump_refuses_a_version_that_is_not_later(capsys):
    assert bump_version.main([APPLICATION_VERSION]) == 2
    assert bump_version.main([bump_version._current()]) == 2
    assert bump_version.main(["0.0.1"]) == 2
    assert "not later" in capsys.readouterr().err


def test_bump_dry_run_names_every_surface_and_writes_nothing(capsys):
    current = parse_app_version(APPLICATION_VERSION)
    assert bump_version.main([f"{current.major}.{current.minor + 1}.0", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "README.md" in out and "README-CN.md" in out and "CHANGELOG.md" in out
    assert bump_version._current() == current.pep440


def test_a_beta_sorts_before_its_final_version_and_after_the_previous_one():
    beta = parse_app_version("1.0.0b1")
    assert parse_app_version("0.8.0") < beta < parse_app_version("1.0.0b2")
    assert beta < parse_app_version("1.0.0")
    assert (beta.pep440, beta.semver, beta.display, beta.debian) == (
        "1.0.0b1",
        "1.0.0-beta.1",
        "1.0.0-beta",
        "1.0.0~beta1",
    )
    assert parse_app_version("1.0.0-beta.1") == beta


def test_release_notes_use_the_release_section_of_the_changelog():
    section = generate_release_notes.changelog_section(APPLICATION_DISPLAY_VERSION)
    assert section.startswith("### ")
    assert "_No changelog entries" not in section
    assert generate_release_notes.changelog_section("99.0.0")  # falls back, never empty

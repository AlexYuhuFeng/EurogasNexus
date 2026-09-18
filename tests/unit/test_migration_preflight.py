"""Migration preflight script (the operator's step before applying a migration).

The preflight is the script an operator runs *before* upgrading a deployment, so a crash in
it is worse than a wrong number: it is the difference between a report and a traceback at the
moment the deployment is about to change. It carried a second, private copy of the migration
scan that `scripts/release/release_metadata.py` had already fixed, and that copy kept the bug -
a wrapped docstring line beginning with the word "revision" was read as the identifier
assignment, which crashed on the tree containing `0035_decision_cases` (its docstring wraps
exactly there).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_the_preflight_reports_the_head_instead_of_crashing(monkeypatch, capsys) -> None:
    """The head resolves on the real tree, prose and all."""

    import scripts.ops.migration_preflight as preflight

    assert preflight.alembic_head() == "0036_job_records"

    # A docstring line that starts with "revision" must not be read as the assignment: this is
    # the exact shape that used to raise IndexError.
    source = (
        Path(preflight.ROOT) / "alembic" / "versions" / "0035_decision_cases.py"
    ).read_text(encoding="utf-8")
    assert any(
        line.strip().startswith("revision.") for line in source.splitlines()
    ), "the regression fixture moved: no docstring line starts with 'revision.' any more"


def test_the_preflight_without_a_database_reports_rather_than_fails(monkeypatch, capsys) -> None:
    import scripts.ops.migration_preflight as preflight

    for name in ("RUNTIME_STORE_DATABASE_URL", "DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)

    status = preflight.main(["--json"])

    report = json.loads(capsys.readouterr().out)
    assert status == 1, "a deployment with no store is not ready to migrate"
    assert report["source_head"] == "0036_job_records"
    assert report["database_url_present"] is False
    assert report["ok"] is False
    assert "RUNTIME_STORE_DATABASE_URL is not configured." in report["warnings"]


def test_the_preflight_resolves_the_head_by_the_chain_not_by_the_filename(
    tmp_path, monkeypatch
) -> None:
    """A migration named out of order cannot be mistaken for the head.

    The chain is what Alembic follows, so the head is the revision no other migration
    declares as its parent - not the highest filename, which is what an earlier scan assumed.
    """

    import scripts.release.release_metadata as release_metadata

    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_first.py").write_text(
        '"""First migration.\n\nRevision ID: 0001_first\n"""\n'
        'revision: str = "0001_first"\n'
        "down_revision: str | None = None\n",
        encoding="utf-8",
    )
    # Named *before* its parent, so sorting identifiers would pick the wrong one.
    (versions / "0000_second.py").write_text(
        '"""Second migration.\n\nThe chain is what decides the head.\nrevision. (prose)\n"""\n'
        'revision: str = "0000_second"\n'
        'down_revision: str | None = "0001_first"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(release_metadata, "ROOT", tmp_path)

    assert release_metadata.latest_alembic_revision() == "0000_second"


def test_a_branched_history_is_refused_rather_than_guessed(tmp_path, monkeypatch) -> None:
    import scripts.release.release_metadata as release_metadata

    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_root.py").write_text(
        'revision = "0001_root"\ndown_revision = None\n', encoding="utf-8"
    )
    for name in ("0002_left", "0003_right"):
        (versions / f"{name}.py").write_text(
            f'revision = "{name}"\ndown_revision = "0001_root"\n', encoding="utf-8"
        )
    monkeypatch.setattr(release_metadata, "ROOT", tmp_path)

    # An expand-only chain must have exactly one leaf; two heads is a migration mistake, and
    # naming both is more useful than silently picking one.
    with pytest.raises(RuntimeError, match="exactly one migration head"):
        release_metadata.latest_alembic_revision()

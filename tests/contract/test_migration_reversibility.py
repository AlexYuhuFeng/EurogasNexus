"""Every migration says whether it can be undone, and large tables are indexed without a lock.

Plan section 3.10 (change discipline). Two rules:

1. **Reversibility.** Each migration declares ``reversibility`` (``reversible``,
   ``conditional``, ``no-op`` or ``irreversible``) and, unless reversible, a
   ``reversibility_note``. The gated upgrade prints them before anything runs, so the
   operator knows which pending revisions can be rolled back and which need the backup. The
   declaration must agree with what ``downgrade()`` does, or the printout would mislead.
2. **Non-blocking indexes.** ``CREATE INDEX`` on a table in ``LARGE_TABLES`` blocks every
   write to it until the build ends. A migration after ``RULES_FROM_REVISION`` builds such an
   index with ``create_index_nonblocking`` (``CREATE INDEX CONCURRENTLY`` on PostgreSQL) or
   passes ``postgresql_concurrently=True`` itself. An index on a table the same migration
   creates is exempt (the table is empty). A table name the test cannot read statically
   counts as large: name it, or use the helper.

Older migrations are not rewritten. Those that built an index on a large table inside the
transaction are listed in ``BLOCKING_BEFORE_THE_RULE``; on a large installation an upgrade
across them blocks ingestion for the length of the build (the upgrade runbook says so).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from eurogas_nexus.db.migration_rules import (
    LARGE_TABLES,
    REVERSIBILITY_VALUES,
    RULES_FROM_REVISION,
)
from scripts.dev.declare_migration_reversibility import classify

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "alembic" / "versions"
MIGRATIONS = sorted(VERSIONS.glob("*.py"))

#: Built an index on a large (or unresolvable) table inside the migration transaction.
BLOCKING_BEFORE_THE_RULE = frozenset(
    {
        "0010_source_observation_metadata",
        "0030_reliability_indexes",
        "0033_market_obs_order_indexes",
        "0044_entsog_native_rates",
        "0048_observation_time_indexes",
        "0061_audit_keyset_index",
        "0082_data1_integration",
    }
)

_SQL_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?P<concurrently>CONCURRENTLY\s+)?"
    r"(?:IF\s+NOT\s+EXISTS\s+)?\S+\s+ON\s+(?:ONLY\s+)?\"?(?P<table>\w+)",
    re.IGNORECASE,
)


def _module_values(tree: ast.Module) -> dict[str, object]:
    out: dict[str, object] = {}
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    continue
    return out


def _revision(path: Path) -> str:
    return str(_module_values(ast.parse(path.read_text(encoding="utf-8")))["revision"])


def _after_rule(path: Path) -> bool:
    return path.stem.split("_", 1)[0] > RULES_FROM_REVISION.split("_", 1)[0]


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda path: path.stem)
def test_migration_declares_its_reversibility(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    values = _module_values(ast.parse(source))
    declared = values.get("reversibility")
    assert declared in REVERSIBILITY_VALUES, (
        f"{path.name} must declare reversibility = one of {REVERSIBILITY_VALUES} "
        "(scripts/dev/declare_migration_reversibility.py explains the values)"
    )
    if declared != "reversible":
        note = values.get("reversibility_note")
        assert isinstance(note, str) and len(note.strip()) >= 20, (
            f"{path.name}: a {declared!r} migration explains itself in reversibility_note"
        )
    assert classify(source) == declared, (
        f"{path.name} declares {declared!r} but its downgrade() reads as "
        f"{classify(source)!r}; fix the declaration or the downgrade"
    )


def _string_value(node: ast.AST | None, constants: dict[str, object]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and isinstance(constants.get(node.id), str):
        return str(constants[node.id])
    return None


def blocking_index_builds(source: str) -> list[str]:
    """Large (or unresolvable) tables indexed without the non-blocking form in upgrade()."""

    tree = ast.parse(source)
    constants = _module_values(tree)
    upgrade = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None
    )
    if upgrade is None:
        return []
    # upgrade() and the module's helpers it calls (transitively): an index built in a helper
    # is still built by the upgrade.
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    reached = {"upgrade"}
    pending = [upgrade]
    while pending:
        for node in ast.walk(pending.pop()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in functions
                and node.func.id not in reached | {"downgrade"}
            ):
                reached.add(node.func.id)
                pending.append(functions[node.func.id])
    bodies = [functions[name] for name in sorted(reached)]
    created = {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "create_table"
        and node.args
        and (name := _string_value(node.args[0], constants))
    }
    batch_tables: dict[str, str | None] = {}
    for node in (node for body in bodies for node in ast.walk(body)):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if (
                    isinstance(call, ast.Call)
                    and getattr(call.func, "attr", None) == "batch_alter_table"
                    and isinstance(item.optional_vars, ast.Name)
                ):
                    batch_tables[item.optional_vars.id] = _string_value(
                        call.args[0] if call.args else None, constants
                    )
    problems: list[str] = []
    for node in (node for body in bodies for node in ast.walk(body)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "create_index":
            receiver = getattr(node.func, "value", None)
            if isinstance(receiver, ast.Name) and receiver.id in batch_tables:
                table = batch_tables[receiver.id]
            else:
                table = _string_value(node.args[1] if len(node.args) > 1 else None, constants)
                for keyword in node.keywords:
                    if keyword.arg == "table_name":
                        table = _string_value(keyword.value, constants)
            concurrent = any(
                keyword.arg == "postgresql_concurrently" for keyword in node.keywords
            )
            if table in created or concurrent:
                continue
            if table is None or table in LARGE_TABLES:
                problems.append(table or "<table name not readable>")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for match in _SQL_INDEX.finditer(node.value):
                table = match.group("table")
                if table in LARGE_TABLES and table not in created and not match.group(
                    "concurrently"
                ):
                    problems.append(table)
    return problems


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda path: path.stem)
def test_large_tables_are_indexed_without_blocking_writes(path: Path) -> None:
    problems = blocking_index_builds(path.read_text(encoding="utf-8"))
    if not _after_rule(path):
        if problems:
            assert _revision(path) in BLOCKING_BEFORE_THE_RULE, (
                f"{path.name} builds a blocking index on {problems}; list it in "
                "BLOCKING_BEFORE_THE_RULE only if it predates the rule"
            )
        return
    assert not problems, (
        f"{path.name} builds an index on {problems} inside the migration transaction, which "
        "blocks every write until it finishes; use "
        "eurogas_nexus.db.migration_rules.create_index_nonblocking"
    )


def test_the_grandfathered_list_holds_only_real_blocking_builds() -> None:
    """A name stays on the list only while that migration really does it."""

    found = {
        _revision(path)
        for path in MIGRATIONS
        if not _after_rule(path) and blocking_index_builds(path.read_text(encoding="utf-8"))
    }
    assert found == BLOCKING_BEFORE_THE_RULE


def test_the_rule_catches_a_blocking_build_and_accepts_the_helper() -> None:
    blocking = (
        "from alembic import op\n"
        "def upgrade():\n"
        "    op.create_index('ix_q', 'market_quotes', ['hub'])\n"
        "    op.execute('CREATE INDEX ix_f ON flow_observations (gas_day)')\n"
    )
    assert blocking_index_builds(blocking) == ["market_quotes", "flow_observations"]
    fine = (
        "from alembic import op\n"
        "from eurogas_nexus.db.migration_rules import create_index_nonblocking\n"
        "def upgrade():\n"
        "    create_index_nonblocking('ix_q', 'market_quotes', ['hub'])\n"
        "    op.create_index('ix_s', 'small_table', ['a'])\n"
        "    op.create_index('ix_c', 'market_trades', ['a'], postgresql_concurrently=True)\n"
        "    op.execute('CREATE INDEX CONCURRENTLY ix_f ON flow_observations (gas_day)')\n"
    )
    assert blocking_index_builds(fine) == []


def test_new_migrations_start_from_a_declared_template() -> None:
    template = (ROOT / "alembic" / "script.py.mako").read_text(encoding="utf-8")
    assert 'reversibility = "reversible"' in template
    assert "create_index_nonblocking" in template

#!/usr/bin/env python
"""Write each migration's reversibility declaration from what its ``downgrade()`` does.

Every Alembic migration declares, as module constants beside ``revision``::

    reversibility = "reversible" | "conditional" | "no-op" | "irreversible"
    reversibility_note = "..."   # required unless "reversible"

* ``reversible``: the downgrade undoes the upgrade.
* ``conditional``: the downgrade undoes it, but refuses when data recorded since would be
  lost (it raises with the reason; the operator exports or restores a backup).
* ``no-op``: the downgrade deliberately does nothing; the previous code works on the
  upgraded schema (a data correction, an optional extension, the empty baseline).
* ``irreversible``: the downgrade refuses; going back means restoring the pre-upgrade
  backup.

The gated upgrade (``scripts/ops/upgrade_database.py``) prints the declaration of each
pending revision, and ``tests/contract/test_migration_reversibility.py`` fails when a
migration lacks one or its declaration contradicts its ``downgrade()``.

This script filled the declarations of the 94 migrations that existed when the rule was
introduced (2026-11-26) by classifying each ``downgrade()`` body: raise only ->
irreversible; code and a raise -> conditional; code -> reversible; empty -> no-op with a
note from ``NO_OP_NOTES``. It changes no migration's behaviour; it only adds the two
constants after the revision identifiers. Files that already declare are left alone, so it
is safe to run again. A new migration declares by hand (``alembic/script.py.mako`` has the
lines).

Usage:
    python scripts/dev/declare_migration_reversibility.py [--check]
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "alembic" / "versions"
VALUES = ("reversible", "conditional", "no-op", "irreversible")

#: Why an empty downgrade is safe, for the migrations that had one when the rule came in.
NO_OP_NOTES = {
    "0001_m2_baseline": "Empty baseline: there is no schema below it to return to.",
    "0091_hub_one_identity": (
        "Data correction: which rows were written GTF or VTP is not kept, and the previous "
        "code reads the hub codes the rows now carry."
    ),
    "0093_timescale_optional": (
        "Converted hypertables stay hypertables; returning them to plain tables is an "
        "operator task (docs/deployment/TIMESCALEDB.md), not a migration step."
    ),
}


def _downgrade(tree: ast.Module) -> ast.FunctionDef | None:
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
        ),
        None,
    )


def _statements(function: ast.FunctionDef) -> list[ast.stmt]:
    return [
        node
        for node in function.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        and not isinstance(node, ast.Pass)
    ]


def _raises(function: ast.FunctionDef) -> list[ast.Raise]:
    return [node for node in ast.walk(function) if isinstance(node, ast.Raise)]


def classify(source: str) -> str:
    """What the downgrade does: one of :data:`VALUES`."""

    tree = ast.parse(source)
    function = _downgrade(tree)
    if function is None:
        return "irreversible"
    statements = _statements(function)
    raises = _raises(function)
    if not statements:
        return "no-op"
    if len(statements) == 1 and isinstance(statements[0], ast.Raise):
        return "irreversible"
    if raises:
        return "conditional"
    return "reversible"


CONDITIONAL_NOTE = (
    "The downgrade refuses while data recorded since this revision would be lost (its error "
    "says which); export that data first or restore the pre-upgrade backup."
)


def _raise_message(function: ast.FunctionDef) -> str:
    """The first raise's message when it is plain text (an f-string's fragments would not
    read as a sentence, so those get the generic refusal note)."""

    for node in _raises(function):
        if any(isinstance(item, ast.JoinedStr) for item in ast.walk(node)):
            continue
        parts = [
            item.value
            for item in ast.walk(node)
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        ]
        if parts:
            return " ".join(" ".join(parts).split())
    return "The downgrade refuses; restore the pre-upgrade backup."


def _wrapped(name: str, text: str, width: int = 88) -> list[str]:
    """``name = (...)`` as implicit concatenation, each line within the line limit."""

    words = text.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if len(candidate) > width and current:
            chunks.append(current + " ")
            current = word
        else:
            current = candidate
    chunks.append(current)
    if len(chunks) == 1:
        return [f"{name} = {chunks[0]!r}"]
    return [f"{name} = ("] + [f"    {chunk!r}" for chunk in chunks] + [")"]


def declared(module: ast.Module) -> dict[str, object]:
    out: dict[str, object] = {}
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {
                "reversibility",
                "reversibility_note",
                "revision",
            }:
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    out[target.id] = None
    return out


def declaration_lines(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    kind = classify(source)
    revision = str(declared(tree).get("revision") or path.stem)
    function = _downgrade(tree)
    note: str | None = None
    if kind == "no-op":
        note = NO_OP_NOTES.get(revision)
        if note is None:
            raise SystemExit(
                f"{path.name}: empty downgrade; add its reason to NO_OP_NOTES or declare by hand"
            )
    elif kind == "conditional":
        note = CONDITIONAL_NOTE
    elif kind == "irreversible" and function is not None:
        note = _raise_message(function)
    lines = [
        "# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).",
        f'reversibility = "{kind}"',
    ]
    if note:
        lines.extend(_wrapped("reversibility_note", note))
    return lines


def insert(path: Path) -> bool:
    """Add the declaration after the revision identifiers; False when already declared."""

    source = path.read_text(encoding="utf-8")
    if "reversibility" in declared(ast.parse(source)):
        return False
    lines = source.splitlines(keepends=True)
    anchor = None
    for index, line in enumerate(lines):
        if line.startswith(("depends_on", "branch_labels", "down_revision", "revision")):
            anchor = index
    if anchor is None:
        raise SystemExit(f"{path.name}: no revision identifiers found")
    # A multi-line assignment: move to its last line.
    while anchor + 1 < len(lines) and lines[anchor + 1].startswith((" ", ")")):
        anchor += 1
    block = "".join(f"{line}\n" for line in declaration_lines(path))
    lines.insert(anchor + 1, block)
    path.write_text("".join(lines), encoding="utf-8")
    ast.parse(path.read_text(encoding="utf-8"))
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    args = parser.parse_args(argv)
    missing = []
    written = 0
    for path in sorted(VERSIONS.glob("*.py")):
        if "reversibility" in declared(ast.parse(path.read_text(encoding="utf-8"))):
            continue
        missing.append(path.name)
        if not args.check and insert(path):
            written += 1
    if args.check:
        for name in missing:
            print(f"undeclared: {name}")
        return 1 if missing else 0
    print(f"declared {written} migration(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Declared notes (domain/ontology/notes.py): one mechanism, both languages, same parameters.

Every module that declares notes is imported so the catalogue is whole; each note's English
template and its ``warning.<code>`` lines in the client's locale files use the same parameter
names, so a translated sentence is never missing a figure the English one has.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

from eurogas_nexus.domain.ontology import notes

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "clients" / "web" / "src" / "i18n"
SERVER = ROOT / "src" / "eurogas_nexus"


def _declaring_modules() -> list[str]:
    out = []
    for path in SERVER.rglob("*.py"):
        if path.name == "notes.py":
            continue
        if re.search(r"\bdeclare\(\s*\"[A-Z]", path.read_text(encoding="utf-8")):
            out.append(".".join(path.relative_to(SERVER.parent).with_suffix("").parts))
    return out


def test_every_declared_note_has_both_languages_with_the_same_parameters() -> None:
    for module in _declaring_modules():
        importlib.import_module(module)
    assert notes.CATALOGUE, "no notes declared"
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((LOCALES / "zh.json").read_text(encoding="utf-8"))
    for code in notes.CATALOGUE:
        key = f"warning.{code.lower()}"
        fields = set(notes.template_fields(code))
        for name, table in (("en", en), ("zh", zh)):
            assert key in table, f"{name} {key}"
            used = set(re.findall(r"\{\{(\w+)\}\}", table[key]))
            # A record parameter may be said by its name: {{ref}} is filled from ref_name.
            assert used <= fields | {"ref"}, f"{name} {key} uses {used - fields}"


def test_a_note_carries_code_params_and_text_and_refuses_what_is_not_declared() -> None:
    code = notes.declare("TEST_NOTE_EXAMPLE", "{count} things at {hub}")
    item = notes.note(code, count=2, hub="TTF").as_dict()
    assert item == {"code": "TEST_NOTE_EXAMPLE", "params": {"count": 2, "hub": "TTF"},
                    "text": "2 things at TTF"}
    with pytest.raises(KeyError):
        notes.note(code, count=2)
    with pytest.raises(KeyError):
        notes.note("NOT_DECLARED")
    with pytest.raises(ValueError):
        notes.declare("TEST_NOTE_EXAMPLE", "other text")
    with pytest.raises(ValueError):
        notes.declare("lower_case", "x")
    del notes.CATALOGUE["TEST_NOTE_EXAMPLE"]


def test_an_envelope_says_every_warning_as_a_note() -> None:
    importlib.import_module("eurogas_nexus.api.routes.public.risk")
    importlib.import_module("eurogas_nexus.application.lng_disruption")
    produced = notes.note("NO_TERMINAL_TERMS")
    lines, items = notes.split_notes([
        produced,
        produced.text,  # the same warning appended twice (a note and its text): said once
        "ROUTE_COST_MISSING:R-2",  # an older coded line: its code, detail as parameter
        "slot S-1: no hub or send-out rate; left out",  # a declared template read back
        "Something new happened.",  # anything else: said as sent
    ])
    assert lines == [produced.text, "ROUTE_COST_MISSING:R-2",
                     "slot S-1: no hub or send-out rate; left out", "Something new happened."]
    assert [item["code"] for item in items] == [
        "NO_TERMINAL_TERMS", "ROUTE_COST_MISSING", "SLOT_LEFT_OUT", "TEXT"]
    assert items[1]["params"] == {"detail": "R-2"}
    assert items[2]["params"] == {"slot": "S-1"}

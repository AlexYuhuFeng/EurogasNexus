"""Notes and warnings the server shows a person: a stable code, its parameters and English text.

One mechanism for every server-produced sentence a screen renders (review 2026-11-26): the
server declares each note once, here or in the module that raises it, with an English template;
a payload carries ``{"code", "params", "text"}``. The client says the note in the reader's
language through ``warning.<code>`` with the same parameters (``serverWarningText`` in
``clients/web/src/app/warningLabel.ts``) and falls back to ``text``. The client test
``serverWarningCodes.test.ts`` reads every ``declare(<code>, <template>)`` in the server and
requires both languages for it.

A parameter that names a record carries the name a person knows (``ref_name``) beside the id
(``ref``), so no screen needs a second read to avoid showing an identifier.
"""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

#: Every declared note: code -> English template (``str.format`` fields).
CATALOGUE: dict[str, str] = {}

_FORMATTER = string.Formatter()


def declare(code: str, template: str) -> str:
    """Declare a note once; returns the code. A second, different template is an error."""

    if not code or not code.replace("_", "").isalnum() or code.upper() != code:
        raise ValueError(f"a note code is UPPER_SNAKE_CASE: {code!r}")
    known = CATALOGUE.get(code)
    if known is not None and known != template:
        raise ValueError(f"note {code} is declared twice with different text")
    CATALOGUE[code] = template
    return code


def template_fields(code: str) -> list[str]:
    """The parameter names a note's template uses."""

    return [name for _, name, _, _ in _FORMATTER.parse(CATALOGUE[code]) if name]


@dataclass(frozen=True)
class Note:
    code: str
    params: Mapping[str, object] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return CATALOGUE[self.code].format(**self.params)

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "params": dict(self.params), "text": self.text}


def note(code: str, **params: object) -> Note:
    """A declared note with its parameters; an undeclared code or a missing field fails."""

    if code not in CATALOGUE:
        raise KeyError(f"note {code} is not declared")
    missing = [name for name in template_fields(code) if name not in params]
    if missing:
        raise KeyError(f"note {code} needs {', '.join(missing)}")
    return Note(code, params)


# --------------------------------------------------------------------------- envelopes


#: A stable ``CODE`` or ``CODE:detail`` line (the older coded warnings).
_CODED_LINE = re.compile(r"^([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?::(.*))?$")


def _pattern(template: str) -> re.Pattern[str]:
    """A declared template as a pattern that reads its parameters back from the text."""

    out = []
    for literal, name, _spec, _conv in _FORMATTER.parse(template):
        out.append(re.escape(literal))
        if name:
            out.append(f"(?P<{name}>.+?)")
    return re.compile("^" + "".join(out) + "$")


def as_note(item: Note | Mapping[str, object] | str) -> dict[str, object]:
    """Any warning as ``{code, params, text}``.

    A note as it is; a ``CODE:detail`` line by its code (``detail`` as its parameter); an English
    line a producer still appends as text is recognised from the declared templates (a module
    that declares a note can keep appending ``note(...).text``); any other line keeps code
    ``TEXT`` and is said as sent.
    """

    if isinstance(item, Note):
        return item.as_dict()
    if isinstance(item, Mapping):
        return {
            "code": str(item.get("code") or "TEXT"),
            "params": dict(item.get("params") or {}),  # type: ignore[arg-type]
            "text": str(item.get("text") or ""),
        }
    text = str(item).strip()
    coded = _CODED_LINE.match(text)
    if coded:
        detail = (coded.group(2) or "").strip()
        params = {"detail": detail} if detail else {}
        return {"code": coded.group(1), "params": params, "text": text}
    for code, template in CATALOGUE.items():
        match = _pattern(template).match(text)
        if match:
            return {"code": code, "params": match.groupdict(), "text": text}
    return {"code": "TEXT", "params": {}, "text": text}


def split_notes(items: Iterable[Note | str]) -> tuple[list[str], list[dict[str, object]]]:
    """``(warnings, notes)`` for an envelope's meta: the English lines once each (older
    clients) and the same warnings as notes."""

    seen: dict[str, dict[str, object]] = {}
    for item in items:
        found = as_note(item)
        seen.setdefault(str(found["text"]), found)
    return list(seen), list(seen.values())

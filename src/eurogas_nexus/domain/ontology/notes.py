"""Notes and warnings the server shows a person: a stable code, its parameters and English text.

One mechanism for every server-produced sentence a screen renders (review 2026-11-26): the
server declares each note once, here or in the module that raises it, with an English template;
a payload carries ``{"code", "params", "text"}``. The client says the note in the reader's
language through ``warning.<code>`` with the same parameters (``serverWarningText`` in
``clients/web/src/app/warningLabel.ts``) and falls back to ``text``. The client test
``serverWarningCodes.test.ts`` reads every ``declare(<code>, <template>)`` in the server and requires
both languages for it.

A parameter that names a record carries the name a person knows (``ref_name``) beside the id
(``ref``), so no screen needs a second read to avoid showing an identifier.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
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

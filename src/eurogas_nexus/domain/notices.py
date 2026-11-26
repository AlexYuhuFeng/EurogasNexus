"""Server notices a client says in its own language: ``{code, params, text}``.

A response's ``meta.warnings`` has always been a list of English lines, some of them stable
``CODE:detail`` strings, most of them sentences. A client could only show them as sent (English
on a Chinese screen) or guess at them with patterns. A notice carries what the line says as data:

- ``code``: the stable key (``no_cash_out_assumption``, ``contract_floating``, or an upper-case
  ``CODE`` from a ``CODE:detail`` line), rendered by the client as ``server.sentence.<code>`` or
  ``warning.<code>`` (both languages);
- ``params``: the values the sentence names (a contract id, an index, a date), plain text;
- ``text``: the English sentence, the fallback for a client that does not know the code.

A producer either appends a :class:`Notice` (preferred: the code is chosen where the fact is
known) or keeps appending an English line, which :func:`as_notice` recognises from
:data:`SENTENCES` (the one catalogue; ``tests/unit/test_notices.py`` keeps every code in both
locale files). An envelope publishes ``warnings`` (English lines, for older clients) and
``notices`` side by side through :func:`split_warnings`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Notice:
    """One server notice: its code, the values it names and its English sentence."""

    code: str
    text: str
    params: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Serialised form."""

        return {"code": self.code, "params": dict(self.params), "text": self.text}

    def __str__(self) -> str:  # an English line wherever a string is still expected
        return self.text


def notice(code: str, text: str, **params: object) -> Notice:
    """A notice with its params as plain text."""

    return Notice(code=code, text=text, params={key: str(value) for key, value in params.items()})


#: code -> (pattern, param names): the English sentences producers still append as text. The
#: codes are the client's ``server.sentence.<code>`` keys.
SENTENCES: dict[str, tuple[re.Pattern[str], tuple[str, ...]]] = {
    name: (re.compile(pattern), params)
    for name, pattern, params in (
        (
            "simulated_marks",
            r"^(?:DEMO: marks are simulated demo prices, not market prices\.?"
            r"|Marks are simulated prices, not market prices\.?)$",
            (),
        ),
        (
            "contract_floating",
            r"^contract (\S+): price floats with (.+); volume only on the ladder$",
            ("contract", "index"),
        ),
        (
            "contract_fob",
            r"^contract (\S+): an FOB cargo is not on a European hub until it is sold or "
            r"discharged$",
            ("contract",),
        ),
        ("contract_gas_year", r"^contract (\S+): gas year '?(.+?)'? not understood$",
         ("contract", "year")),
        (
            "contract_no_hub",
            r"^contract (\S+): delivery point '?(.+?)'? does not name a hub; .+$",
            ("contract", "point"),
        ),
        (
            "no_cash_out_assumption",
            r"^No approved cash-out premium or discount for this hub's books: the cost is not "
            r"estimated on the days marked\.$",
            (),
        ),
        (
            "no_delivery_history",
            r"^No delivery history for these contracts; the nomination tolerance stands in for "
            r"the measured volatility\. Load allocations to sharpen the plan\.$",
            (),
        ),
        ("slot_left_out", r"^slot (\S+): no hub or send-out rate; left out$", ("slot",)),
        ("no_terminal_terms", r"^No terminal terms yet; the LNG desk enters them per terminal\.$",
         ()),
        ("simulated_not_for_bids", r"^Simulated prices are never used to price a bid\.$", ()),
        (
            "nomination_windows_unavailable",
            r"^Nomination windows are unavailable until a runtime DB is configured and its "
            r"window masters are declared\.$",
            (),
        ),
    )
}

#: A stable ``CODE`` or ``CODE:detail`` line.
_CODED = re.compile(r"^([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?::(.*))?$")


def as_notice(item: str | Notice | Mapping[str, Any]) -> Notice:
    """Any warning as a notice: a notice as it is, a coded line by its code, a known sentence
    by its template; any other line keeps code ``text`` (said as sent)."""

    if isinstance(item, Notice):
        return item
    if isinstance(item, Mapping):
        return Notice(
            code=str(item.get("code") or "text"),
            text=str(item.get("text") or ""),
            params={k: str(v) for k, v in dict(item.get("params") or {}).items()},
        )
    text = str(item).strip()
    coded = _CODED.match(text)
    if coded:
        detail = (coded.group(2) or "").strip()
        return Notice(code=coded.group(1), text=text, params={"detail": detail} if detail else {})
    for code, (pattern, names) in SENTENCES.items():
        match = pattern.match(text)
        if match:
            params = dict(zip(names, match.groups(), strict=True))
            return Notice(code=code, text=text, params=params)
    return Notice(code="text", text=text)


def split_warnings(items: Iterable[str | Notice]) -> tuple[list[str], list[dict[str, Any]]]:
    """``(warnings, notices)`` for an envelope: the English lines once each, and the notices."""

    seen: dict[str, Notice] = {}
    for item in items:
        found = as_notice(item)
        seen.setdefault(found.text, found)
    return list(seen), [item.to_json() for item in seen.values()]

"""Server text the web client says in the reader's language: the server side of the check.

A client source may not reference the backend (architecture fitness FF1), so the checks that
read both sides live here. Every code the server writes into a warnings / blockers / missing
list, or declares as a note (``domain/ontology/notes.py``), has ``warning.<code>`` in both
locale files; the English sentences the client still recognises (``limitBreaches.ts``,
``serverSentences.ts``) are still the ones the server writes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "src" / "eurogas_nexus"
LOCALES = ROOT / "clients" / "web" / "src" / "i18n"

_APPENDED = re.compile(
    r"(?:warning|blocker|missing|issue)s?\w*\.(?:append|add)\(\s*f?\"([A-Z][A-Z0-9_]{3,})(?=[:\"{])"
)
_DECLARED = re.compile(r"\bdeclare\(\s*\"([A-Z][A-Z0-9_]+)\"")


def _server_codes() -> set[str]:
    codes: set[str] = set()
    for path in SERVER.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        codes.update(_APPENDED.findall(text))
        codes.update(_DECLARED.findall(text))
    # ``TARIFF_STATUS_{status}``: every non-final tariff status (domain/ontology/vocabulary.py).
    codes.discard("TARIFF_STATUS_")
    codes.update(
        f"TARIFF_STATUS_{status}"
        for status in ("INDICATIVE", "PROVISIONAL", "DRAFT", "SIMULATOR_ONLY")
    )
    codes.add("TARIFF_APPLICABILITY_NOT_ASSESSED")
    return codes


def test_every_server_warning_code_has_english_and_chinese_words() -> None:
    codes = _server_codes()
    assert len(codes) > 50, f"found only {len(codes)} codes; the pattern no longer matches"
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((LOCALES / "zh.json").read_text(encoding="utf-8"))
    missing = []
    for code in sorted(codes):
        key = f"warning.{code.lower()}"
        if not en.get(key):
            missing.append(f"en {key}")
        if not zh.get(key):
            missing.append(f"zh {key}")
        elif not re.search(r"[一-鿿]", zh[key]):
            missing.append(f"zh {key} is not Chinese")
    assert missing == []


def test_the_sentences_the_client_recognises_are_still_written() -> None:
    def read(relative: str) -> str:
        return (SERVER / relative).read_text(encoding="utf-8")

    expected = {
        "domain/risk/limits.py": (
            "is outside the mandate (", "physical supply is not allowed (",
            "financial trades are not allowed (", "is not an allowed instrument (",
            "is beyond ", " is over ", "%, above ", "%, below ", "over the approved",
            "under the approved",
        ),
        "application/position_inputs.py": (
            "price floats with ", "; volume only on the ladder",
            "; volume on the ladder, its price exposure on that index",
            "an FOB cargo is not on a European hub until it is sold or ",
            "Marks are simulated prices, not market prices.",
            "cargo(es) on the ladder from their plans and recorded ",
        ),
        "domain/market/fx_forward.py": ('f"derived (interest parity from {names}, flat rate)"',),
        "domain/risk/delivery.py": (
            "deviates from nominations on more than 1 day in 5", "% against DCQ",
            "volatile delivery (CV above 15%)",
        ),
    }
    for relative, fragments in expected.items():
        text = read(relative)
        for fragment in fragments:
            assert fragment in text, f"{relative} no longer writes {fragment!r}"

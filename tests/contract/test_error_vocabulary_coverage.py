"""The error vocabulary gate (Architecture V2 Wave 8).

The backend's taxonomy names a translation key per catalogued code
(`errors.<code>.message` / `errors.<code>.action`) and, for a code it does not
catalogue, the family's own keys - so a client always has text to render instead of a
missing-key placeholder. That promise only holds if the client's locales define every
key the catalogue can emit: this gate fails when a catalogued code has no text in either
locale, which is exactly how 46 codes once reached users as raw `errors.…` strings.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from eurogas_nexus.domain.operations.error_taxonomy import (
    ERROR_CATALOGUE,
    ErrorFamily,
    error_definition,
    error_payload,
)

ROOT = Path(__file__).resolve().parents[2]
LOCALES = {
    "en": ROOT / "clients" / "web" / "src" / "i18n" / "en.json",
    "zh": ROOT / "clients" / "web" / "src" / "i18n" / "zh.json",
}


def _locale(name: str) -> dict[str, str]:
    return json.loads(LOCALES[name].read_text(encoding="utf-8-sig"))


def test_every_catalogued_code_has_message_and_action_text() -> None:
    """A catalogued code must never reach a user as an unresolved key."""

    missing: list[str] = []
    for code in sorted(ERROR_CATALOGUE):
        for name in LOCALES:
            strings = _locale(name)
            for suffix in ("message", "action"):
                key = f"errors.{code}.{suffix}"
                if not (strings.get(key) or "").strip():
                    missing.append(f"{name}:{key}")
    assert missing == []


def test_the_locale_text_for_a_code_differs_between_locales() -> None:
    """Two locales that render the same sentence are a copy, not a translation."""

    en = _locale("en")
    zh = _locale("zh")
    identical = [
        code
        for code in sorted(ERROR_CATALOGUE)
        for suffix in ("message", "action")
        if en[f"errors.{code}.{suffix}"] == zh[f"errors.{code}.{suffix}"]
    ]
    assert identical == []


def test_the_payload_keys_the_taxonomy_emits_are_the_ones_the_locales_define() -> None:
    """The gate follows the taxonomy's own output rather than a hand-kept code list."""

    for code in sorted(ERROR_CATALOGUE):
        payload = error_payload(code)
        en = _locale("en")
        assert en[payload["message_key"]] .strip(), code
        assert en[payload["action_key"]].strip(), code


def test_the_client_reads_the_field_names_the_envelope_writes() -> None:
    """The envelope's field names are pinned across the language boundary.

    The backend writes the taxonomy at the top level of the response body; the client
    reads the same names off `ApiErrorBody`. Renaming one side without the other would
    leave every failure presented as an unclassified SYSTEM fault, so the two are held
    together here rather than by eye.
    """

    source = (ROOT / "clients" / "web" / "src" / "app" / "experience" / "errorPresentation.ts").read_text(
        encoding="utf-8-sig"
    )
    body = source.split("export interface ApiErrorBody {", 1)[1].split("}", 1)[0]
    read_fields = set(re.findall(r"readonly (\w+)\??:", body))

    written = set(
        error_payload(
            "internal",
            correlation_id="c-1",
            operator=True,
            operator_detail="ConnectionResetError",
        )
    ) | {"message"}
    assert read_fields <= written, sorted(read_fields - written)
    # The client reads the code under the name the envelope writes it.
    assert "error" in read_fields
    assert "correlation_id" in read_fields
    # And the envelope writes one field a business surface deliberately does not read:
    # `operator_detail` exists for an operator reading the raw body, and is only ever
    # written for an operator identity.
    assert written - read_fields == {"operator_detail"}

    """A code the catalogue does not know borrows the family's words, never a raw key.

    Two shapes, both pinned in `tests/unit/test_error_taxonomy.py`: a code that matches a
    family rule keeps its own name and takes that family's keys; a code that matches no
    rule is reported as `UNCLASSIFIED_ERROR` under SYSTEM, because a code the taxonomy
    cannot classify is not evidence of what happened. The endpoint's own `detail` is
    passed through unchanged either way, so the caller's real string is not lost.
    """

    classified = error_definition("portfolio_export_denied")
    assert classified.code == "portfolio_export_denied"
    assert classified.family is ErrorFamily.ENTITLEMENT
    assert classified.message_key == "errors.family.ENTITLEMENT.title"
    assert classified.action_key == "errors.family.ENTITLEMENT.action"

    unknown = error_payload("some_new_failure")
    assert unknown["error"] == "UNCLASSIFIED_ERROR"
    assert unknown["message_key"] == "errors.unclassified.message"
    assert unknown["action_key"] == "errors.unclassified.action"

    en = _locale("en")
    for payload in (error_payload(classified.code), unknown):
        assert en[payload["message_key"]].strip()
        assert en[payload["action_key"]].strip()

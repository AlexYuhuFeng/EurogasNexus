"""Server notices (``domain/notices.py``): every code a client can say in both languages.

A notice is ``{code, params, text}``. The client renders ``server.sentence.<code>`` (or
``warning.<code>`` for an upper-case ``CODE:detail`` line); this test keeps the server's
sentence catalogue and the two locale files in step, so a new code never reaches a screen raw.
"""

from __future__ import annotations

import json
from pathlib import Path

from eurogas_nexus.domain.notices import SENTENCES, Notice, as_notice, notice, split_warnings

LOCALES = Path(__file__).resolve().parents[2] / "clients" / "web" / "src" / "i18n"


def test_every_sentence_code_is_said_in_both_languages() -> None:
    for language in ("en", "zh"):
        keys = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
        missing = [code for code in SENTENCES if f"server.sentence.{code}" not in keys]
        assert not missing, f"{language}: {missing}"


def test_a_known_sentence_becomes_its_code_and_params() -> None:
    found = as_notice("contract demo-x: price floats with NBP day-ahead; volume only on the ladder")
    assert found.code == "contract_floating"
    assert dict(found.params) == {"contract": "demo-x", "index": "NBP day-ahead"}
    assert as_notice("slot S-1: no hub or send-out rate; left out").params == {"slot": "S-1"}


def test_a_coded_line_keeps_its_code_and_detail() -> None:
    found = as_notice("LLM_PAYLOAD_FILTERED:contract_prices")
    assert found.code == "LLM_PAYLOAD_FILTERED"
    assert dict(found.params) == {"detail": "contract_prices"}
    assert as_notice("ROUTE_COST_MISSING").params == {}


def test_an_unknown_line_is_said_as_sent() -> None:
    found = as_notice("Something new happened.")
    assert (found.code, found.text) == ("text", "Something new happened.")


def test_an_envelope_publishes_lines_and_notices_once_each() -> None:
    produced = notice(
        "no_terminal_terms", "No terminal terms yet; the LNG desk enters them per terminal."
    )
    lines, notices = split_warnings([produced, produced.text, "ROUTE_COST_MISSING:R-2"])
    assert lines == [produced.text, "ROUTE_COST_MISSING:R-2"]
    assert notices[0] == {"code": "no_terminal_terms", "params": {}, "text": produced.text}
    assert notices[1]["params"] == {"detail": "R-2"}
    assert isinstance(as_notice(notices[0]), Notice)

"""Model text stays inside the evidence: hubs, units, directions, superlatives, names."""

from __future__ import annotations

import json

import pytest

from eurogas_nexus.application.ai_style import checked_note
from eurogas_nexus.application.grounding import check_grounding

EVIDENCE = (
    "Demo Haldor field (NBP): 563 GWh/d unavailable (74% of technical capacity), "
    "07 Nov 05:43 to 10 Nov 05:43 UTC. Unplanned outage; reason: compressor trip. "
    "The desk is long 28,000 MWh/d at NBP today. "
    "Net exposure €4.88m against a €4.25m limit (115%). Rhinmark Handel GmbH credit breach. "
    "NBP front month 34.64 GBP/MWh, down 0.51 on the day; price fell from 35.15 GBP/MWh. "
    "Headroom £5.21m before the limit, exposure is above the limit."
)
ZH_EVIDENCE = "交易台在 NBP 多头 28,000 MWh/d。Haldor 气田停运 563 GWh/d。价格下跌 0.51。"

GOOD = [
    "Haldor is out 563 GWh/d, 74% of capacity, and the desk is long 28,000 MWh/d at NBP.",
    "The outage is unplanned: compressor trip. NBP front month is 34.64 GBP/MWh.",
    "Net exposure is €4.88m against a €4.25m limit, 115% used.",
    "Rhinmark Handel GmbH is in breach; exposure is above the limit.",
    "NBP fell 0.51 on the day to 34.64 GBP/MWh.",
    "Headroom is £5.21m before the limit.",
    "The desk is long at NBP while 563 GWh/d is unavailable until 10 Nov.",
    "Check the outage end time and the credit line.",
    "Exposure at 115% of the limit needs attention today.",
    "563 GWh/d of supply is out; the price is down 0.51.",
]

BAD = [
    # wrong hub
    ("Haldor is out 563 GWh/d and the desk is long at TTF.", "hub"),
    ("The desk is long 28,000 MWh/d at THE today.", "hub"),
    ("PEG front month is 34.64 GBP/MWh.", "hub"),
    ("Exposure matters for PSV and NBP.", "hub"),
    # right number, wrong unit
    ("Haldor is out 563 MWh/d.", "unit"),
    ("The desk is long 28,000 GWh/d at NBP.", "unit"),
    ("NBP front month is 34.64 EUR/MWh.", "unit"),
    ("Haldor is out 563 mcm.", "unit"),
    ("Net exposure is £4.88m against the limit.", "unit"),
    ("Net exposure is €4.88k against a €4.25m limit.", "unit"),
    ("Headroom is €5.21m.", "unit"),
    ("NBP is 34.64 p/th.", "unit"),
    ("The price is 34.64 USD/MMBtu.", "unit"),
    ("74 GWh/d of capacity is out.", "unit"),
    # flipped or invented direction
    ("The desk is short 28,000 MWh/d at NBP.", "direction"),
    ("Exposure is below the limit.", "direction"),
    ("NBP rose 0.51 on the day.", "direction"),
    ("NBP is up 0.51 on the day.", "direction"),
    ("The market is in surplus after the outage.", "direction"),
    ("There is a deficit of 563 GWh/d.", "direction"),
    ("The price increased to 34.64 GBP/MWh.", "direction"),
    # unsupported superlative
    ("This is the largest outage at NBP, 563 GWh/d.", "superlative"),
    ("Exposure is at a record 115%.", "superlative"),
    ("The highest exposure of the year, €4.88m.", "superlative"),
    ("An unprecedented outage of 563 GWh/d.", "superlative"),
    ("The worst breach so far, 115%.", "superlative"),
    # invented name
    ("The outage follows trouble at Equinor, with 563 GWh/d out.", "name"),
    ("Exposure to Nordvik Petroleum is €4.88m.", "name"),
    ("The breach is with Aldermoor Energy, at 115%.", "name"),
    ("The outage at the Troll field removes 563 GWh/d.", "name"),
]


@pytest.mark.parametrize("note", GOOD)
def test_a_faithful_note_passes(note):
    result = check_grounding(note, EVIDENCE)
    assert result.ok, result.reason


@pytest.mark.parametrize(("note", "kind"), BAD)
def test_each_kind_of_error_is_rejected(note, kind):
    result = check_grounding(note, EVIDENCE)
    assert not result.ok, f"accepted a {kind} error: {note}"


def test_chinese_notes_are_checked_the_same_way():
    assert check_grounding("交易台在 NBP 多头 28,000 MWh/d。", ZH_EVIDENCE).ok
    assert not check_grounding("交易台在 NBP 空头 28,000 MWh/d。", ZH_EVIDENCE).ok
    assert not check_grounding("交易台在 TTF 多头 28,000 MWh/d。", ZH_EVIDENCE).ok
    assert not check_grounding("价格上涨 0.51。", ZH_EVIDENCE).ok
    assert not check_grounding("创纪录的停运 563 GWh/d。", ZH_EVIDENCE).ok


def test_the_note_checker_applies_grounding_after_its_own_checks():
    sources = ["remit:demo-umm-1:v1"]

    def note(text):
        return json.dumps({"text": text, "cites": sources})

    assert checked_note(note(GOOD[0]), evidence_text=EVIDENCE, sources=sources)
    for text, _kind in BAD:
        assert checked_note(note(text), evidence_text=EVIDENCE, sources=sources) is None, text

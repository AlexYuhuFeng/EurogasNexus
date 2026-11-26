"""Server text a client renders in its own language (review 2026-11-26).

A blocker carries code, subject and detail, so the client can build the sentence; an
assumption input is named by its catalogue label, never its key; a ladder method note is told
apart from a failure, so Today lists only what failed.
"""

from __future__ import annotations

from eurogas_nexus.application.position_inputs import is_method_note
from eurogas_nexus.application.valuation_snapshot import assumption_label
from eurogas_nexus.domain.opportunities.controls import _blocked
from eurogas_nexus.domain.valuation.assumptions import ASSUMPTION_CATALOGUE


def test_a_blocker_carries_its_detail_for_the_client() -> None:
    assessment = _blocked("input_stale", "ESTR fixing of 2026-11-24", "as of 2026-11-24")
    payload = assessment.blocker.to_json()
    assert payload["code"] == "input_stale"
    assert payload["subject"] == "ESTR fixing of 2026-11-24"
    assert payload["detail"] == "as of 2026-11-24"
    assert payload["text"] == (
        "Cannot evaluate: ESTR fixing of 2026-11-24 is stale (as of 2026-11-24)."
    )


def test_an_assumption_is_named_by_its_label() -> None:
    assert assumption_label("balancing.long_discount") == (
        "Cash-out discount when long (under day-ahead)"
    )
    assert assumption_label("not.in_catalogue") == "not.in_catalogue"
    assert all(assumption_label(key) != key for key in ASSUMPTION_CATALOGUE)


def test_method_notes_are_not_failures() -> None:
    assert is_method_note(
        "contract c1: price floats with NBP day-ahead; volume only on the ladder"
    )
    assert is_method_note(
        "contract c2: an FOB cargo is not on a European hub until it is sold or discharged"
    )
    assert not is_method_note("contract c3: gas year '2025' not understood")


def test_every_claim_template_is_said_in_both_languages_with_the_same_fields() -> None:
    import json
    import re
    from pathlib import Path

    from eurogas_nexus.domain.opportunities.claims import CLAIM_TEMPLATES

    root = Path(__file__).resolve().parents[2] / "clients" / "web" / "src" / "i18n"
    locales = {
        language: json.loads((root / f"{language}.json").read_text(encoding="utf-8"))
        for language in ("en", "zh")
    }
    for key, template in CLAIM_TEMPLATES.items():
        if key.startswith(("blocked.", "harness.")):
            continue  # blockers render through opportunities.blocked.*; the harness is a test
        fields = set(re.findall(r"\{(\w+)\}", template))
        for language, keys in locales.items():
            said = keys.get(f"claim.{key}")
            assert said, f"claim.{key} missing in {language}"
            assert set(re.findall(r"\{\{(\w+)\}\}", said)) == fields, (language, key)


def test_a_leg_carries_the_values_its_label_names() -> None:
    from decimal import Decimal

    from eurogas_nexus.domain.opportunities.model import Leg, LegKind, Measure

    leg = Leg(
        LegKind.VOLUME,
        "locational.volume",
        "Volume 1,000 MWh/d x 30 d",
        quantity=Measure(Decimal(30000), "MWh"),
        label_params={"mwh_d": "1,000", "days": "30"},
    )
    payload = leg.to_json()
    assert payload["label_key"] == "locational.volume"
    assert payload["label_params"] == {"mwh_d": "1,000", "days": "30"}
    assert payload["label"] == "Volume 1,000 MWh/d x 30 d"

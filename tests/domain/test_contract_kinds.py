"""Contract kinds: golden cases per kind, base-column derivation and the consumers' rules."""

from __future__ import annotations

from datetime import date

import pytest

from eurogas_nexus.domain.contracts import kinds
from eurogas_nexus.domain.contracts.examples import cargo_terms, mspa_terms, tender_terms
from eurogas_nexus.domain.route_cost.contract_revision import (
    CONTRACT_REVISION_SCHEMA_VERSION,
    CONTRACT_REVISION_SCHEMA_VERSION_V5,
    UpstreamContractEconomicSnapshot,
    map_legacy_contract_payload,
)

TODAY = date(2026, 11, 19)


def test_vocabulary_names_every_kind_and_only_four_are_authorable() -> None:
    assert len(kinds.CONTRACT_KINDS) == 9
    assert kinds.AUTHORABLE_KINDS == {"SUPPLY_GSA", "UPSTREAM_TENDER", "LNG_MSPA", "LNG_CARGO"}
    assert kinds.validate_kind("lng_mspa") == "LNG_MSPA"
    with pytest.raises(kinds.ContractKindError) as refused:
        kinds.validate_kind("SPOT")
    assert refused.value.code == "contract_kind_unknown"


def test_tender_golden_case_derives_the_base_columns() -> None:
    terms = kinds.parse_terms("UPSTREAM_TENDER", tender_terms(TODAY))
    base = kinds.derive_base_fields("UPSTREAM_TENDER", terms)
    assert base["delivery_point_name"] == "NBP"
    assert base["gas_year"] == "2026-12..2027-02"
    # Written in th/d as an NBP tender is: 170,000 th/d is 4,982.21 MWh/d (exact factors).
    assert base["delivery_quantity_mwh_per_day"] == pytest.approx(170000 * 0.0293071, rel=1e-6)
    # Swing 4,000-6,000 around 5,000: 20 % up, 20 % down.
    assert base["nomination_tolerance_pct"] == 20.0
    assert base["delivery_tolerance_pct"] == 20.0
    # -0.40 p/th is -0.1365 GBP/MWh (1 MWh = 34.12 th): the differential, in GBP.
    assert base["contract_price_currency"] == "GBP"
    assert base["contract_price_gbp_mwh"] == pytest.approx(-0.4 * 34.1214 / 100, abs=1e-4)
    assert base["notes_fields"]["index_basis"] == "NBP day-ahead"
    assert base["notes_fields"]["price_basis"] == "index"
    assert kinds.position_window("UPSTREAM_TENDER", terms) == (
        date(2026, 12, 1),
        date(2027, 2, 28),
    )
    assert kinds.headline("UPSTREAM_TENDER", terms) == {
        "key": "swing", "value": 170000.0, "min": 136000.0, "max": 204000.0, "unit": "th/d",
    }
    assert kinds.counterparty_id_of(terms) == "DEMO-NORDVIK"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"min_dcq": 180000.0}, "min DCQ <= DCQ <= max DCQ"),
        ({"period_end": "2026-11-01"}, "before period_start"),
        ({"index": None}, "names its index"),
        ({"price_type": "fixed"}, "states its price"),
        ({"price_unit": "p/th"}, "price_unit"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_tender_refusals_say_what_is_wrong(change: dict, message: str) -> None:
    with pytest.raises(kinds.ContractKindError) as refused:
        kinds.parse_terms("UPSTREAM_TENDER", {**tender_terms(TODAY), **change})
    assert refused.value.code == "contract_kind_terms_invalid"
    assert message in refused.value.detail


def test_master_feeds_no_book_and_needs_consistent_credit_support() -> None:
    terms = kinds.parse_terms("LNG_MSPA", mspa_terms(TODAY))
    base = kinds.derive_base_fields("LNG_MSPA", terms)
    assert base["delivery_quantity_mwh_per_day"] == 0.0
    assert base["gas_year"] == "2025+"
    assert not kinds.feeds_book("LNG_MSPA", terms)
    with pytest.raises(kinds.ContractKindError):
        kinds.parse_terms(
            "LNG_MSPA", {**mspa_terms(TODAY), "credit_support_currency": None}
        )
    with pytest.raises(kinds.ContractKindError):
        kinds.parse_terms("LNG_MSPA", {**mspa_terms(TODAY), "delivery_terms": []})


def test_des_cargo_is_a_position_at_its_terminal_hub_and_fob_is_not() -> None:
    master = kinds.parse_terms("LNG_MSPA", mspa_terms(TODAY))
    terms = kinds.parse_terms("LNG_CARGO", cargo_terms(TODAY))
    base = kinds.derive_base_fields("LNG_CARGO", terms, master=master)
    energy = 3_600_000 * 0.29307107
    assert base["delivery_point_name"] == "Gate terminal"
    assert base["delivery_quantity_mwh_per_day"] == pytest.approx(energy / 5, rel=1e-6)
    assert base["notes_fields"]["counterparty"] == "Atlantic LNG Marketing"
    assert base["notes_fields"]["price_basis"] == "formula"
    assert base["upstream_payment_lag_days"] == 20
    assert kinds.feeds_book("LNG_CARGO", terms)
    assert kinds.position_hub_text("LNG_CARGO", terms, "Gate terminal") == "TTF"
    assert kinds.counterparty_id_of(terms, master) == "DEMO-ATLANTIC-LNG"
    assert kinds.headline("LNG_CARGO", terms)["value"] == 3.6
    fob = kinds.parse_terms(
        "LNG_CARGO",
        {**cargo_terms(TODAY), "delivery_term": "FOB", "discharge_terminal": None},
    )
    assert not kinds.feeds_book("LNG_CARGO", fob)


def test_narrowed_window_replaces_the_delivery_window() -> None:
    raw = cargo_terms(TODAY)
    narrowed = kinds.parse_terms(
        "LNG_CARGO",
        {**raw, "narrowed_start": raw["window_start"], "narrowed_end": raw["window_start"]},
    )
    first, last = kinds.position_window("LNG_CARGO", narrowed)
    assert first == last
    with pytest.raises(kinds.ContractKindError):
        kinds.parse_terms(
            "LNG_CARGO", {**raw, "narrowed_start": "2020-01-01", "narrowed_end": "2020-01-02"}
        )


def test_confirmation_needs_an_mspa_that_allows_its_term() -> None:
    master = kinds.parse_terms("LNG_MSPA", {**mspa_terms(TODAY), "delivery_terms": ["FOB"]})
    cargo = kinds.parse_terms("LNG_CARGO", cargo_terms(TODAY))
    for master_kind, code in [
        (None, "contract_master_required"),
        ("SUPPLY_GSA", "contract_master_kind"),
        ("LNG_MSPA", "contract_master_term"),
    ]:
        with pytest.raises(kinds.ContractKindError) as refused:
            kinds.check_confirmation("LNG_CARGO", cargo, master_kind, master)
        assert refused.value.code == code
    with pytest.raises(kinds.ContractKindError):
        kinds.check_confirmation("UPSTREAM_TENDER", None, "LNG_MSPA", master)


def test_gsa_has_no_typed_block_and_migrated_rows_stay_gsa() -> None:
    assert kinds.parse_terms("SUPPLY_GSA", None) is None
    # A supply agreement's block is optional and strict.
    with pytest.raises(kinds.ContractKindError) as refused:
        kinds.parse_terms("SUPPLY_GSA", {"schema": "supply-gsa/v1", "anything": 1})
    assert refused.value.code == "contract_kind_terms_invalid"
    with pytest.raises(kinds.ContractKindError) as refused:
        kinds.parse_terms("HUB_TRADE", {"anything": 1})
    assert refused.value.code == "contract_kind_terms_unexpected"
    assert kinds.infer_kind("LNG_REGAS", {"contract_type": "LNG MSPA"}) == "SUPPLY_GSA"
    assert kinds.derive_base_fields("SUPPLY_GSA", None) == {}


def _payload(**extra) -> dict:
    return {
        "contract_id": "c-1",
        "contract_name": "C",
        "resource_type": "BEACH_DELIVERY",
        "delivery_point_name": "NBP",
        "gas_year": "2026-12..2027-02",
        "delivery_quantity_mwh_per_day": 5000.0,
        "contract_price_gbp_mwh": -0.1365,
        "contract_price_currency": "GBP",
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 20.0,
        "nomination_tolerance_pct": 20.0,
        "annual_financing_rate_pct": 5.0,
        "allowed_exit_points": ["NBP"],
        "eligible_sale_modes": [],
        **extra,
    }


def test_revision_v5_records_the_kind_and_round_trips() -> None:
    plain = map_legacy_contract_payload(_payload()).economic_snapshot
    assert plain.schema_version == CONTRACT_REVISION_SCHEMA_VERSION
    terms = kinds.canonical_terms(kinds.parse_terms("UPSTREAM_TENDER", tender_terms(TODAY)))
    typed = map_legacy_contract_payload(
        _payload(contract_kind="UPSTREAM_TENDER", kind_terms=terms, unmodelled_terms="FM: field")
    ).economic_snapshot
    assert typed.schema_version == CONTRACT_REVISION_SCHEMA_VERSION_V5
    document = typed.canonical_document()
    assert document["kind_terms"]["seller_name"] == "Nordvik Energy"
    rebuilt = UpstreamContractEconomicSnapshot.from_canonical_document(document)
    assert rebuilt.content_hash() == typed.content_hash()
    changed = map_legacy_contract_payload(
        _payload(
            contract_kind="UPSTREAM_TENDER",
            kind_terms={**terms, "max_dcq_mwh_per_day": 6500.0},
            unmodelled_terms="FM: field",
        )
    ).economic_snapshot
    assert changed.content_hash() != typed.content_hash()


def test_a_stored_v1_tender_reads_as_v2_in_mwh():
    v1 = {**tender_terms(TODAY), "schema": "upstream-tender/v1"}
    for key in ("quantity_unit", "dcq", "min_dcq", "max_dcq"):
        v1.pop(key)
    v1.update(dcq_mwh_per_day=5000.0, min_dcq_mwh_per_day=4000.0, max_dcq_mwh_per_day=6000.0)
    terms = kinds.parse_terms("UPSTREAM_TENDER", v1)
    assert terms.quantity_unit == "MWh/d" and terms.dcq_mwh() == 5000.0
    assert kinds.canonical_terms(terms)["schema"] == "upstream-tender/v2"


def test_a_supply_agreement_block_states_its_quantity_and_price_as_written():
    terms = kinds.parse_terms(
        "SUPPLY_GSA",
        {
            "schema": "supply-gsa/v1",
            "quantity": 800000,
            "quantity_unit": "th/d",
            "price_terms": {
                "basis": "index",
                "unit": "GBp/th",
                "index": {"index": "NBP", "product": "month_ahead"},
                "premium": 1.5,
            },
        },
    )
    out = kinds.gsa_overrides(terms)
    assert out["delivery_quantity_mwh_per_day"] == pytest.approx(800000 * 0.0293071, rel=1e-6)
    assert out["contract_price_currency"] == "GBP"
    assert out["notes_fields"]["price_basis"] == "index"
    price, note = kinds.price_terms_for("SUPPLY_GSA", terms)
    assert price.premium == 1.5 and note is None
    # Without a block: fixed per MWh, unless an index is named and the formula is missing.
    fixed, _ = kinds.price_terms_for("SUPPLY_GSA", None, contract_price=30.0, currency="EUR")
    assert fixed.words() == "fixed 30 EUR/MWh"
    none, note = kinds.price_terms_for(
        "SUPPLY_GSA", None, contract_price=30.0, currency="EUR", index_basis="TTF month-ahead"
    )
    assert none is None and "formula is not recorded" in note


def test_each_kind_reads_as_price_terms():
    tender = kinds.parse_terms("UPSTREAM_TENDER", tender_terms(TODAY))
    price, _ = kinds.price_terms_for("UPSTREAM_TENDER", tender)
    assert price.basis == "index" and price.index.index == "NBP" and price.premium == -0.4
    cargo = kinds.parse_terms("LNG_CARGO", cargo_terms(TODAY))
    price, _ = kinds.price_terms_for("LNG_CARGO", cargo)
    assert price.words() == "1.15 × Henry Hub settlement of the pricing month + 2.5 USD/MMBtu"
    master = kinds.parse_terms("LNG_MSPA", mspa_terms(TODAY))
    assert kinds.price_terms_for("LNG_MSPA", master)[0] is None

"""Focused tests for the S2a explicit payment-terms typed foundation.

These tests lock the typed contract of
``docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md`` sections 2.4/2.6/3
without touching persistence, routes or clients: every accepted date shape,
the explicit per-item flow direction (independent of the cash-flow category),
the strict canonical JSON roundtrip, evidence preservation, the sanitized
refusal codes for unknown/mixed/oversized/invalid input (no refusal may echo
an untrusted value, field name or repr), frozen value semantics, and the
unchanged S1a revision-v1 golden bytes/hash. No payment workflow is claimed by
passing these tests.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from dataclasses import MISSING, FrozenInstanceError, fields
from datetime import date, datetime
from decimal import Decimal

import pytest

from eurogas_nexus.domain.ontology.vocabulary import (
    BusinessDayConvention,
    PaymentAnchorEvent,
    PaymentDateSpecificationKind,
    PaymentFlowDirection,
    PaymentOffsetDayKind,
)
from eurogas_nexus.domain.research.cash_valuation import CashFlowLegCategory
from eurogas_nexus.domain.route_cost import contract_revision, payment_terms
from eurogas_nexus.domain.route_cost.contract_revision import (
    SOURCE_PRECISION_EXACT_DECIMAL,
    UpstreamContractEconomicSnapshot,
)
from eurogas_nexus.domain.route_cost.payment_terms import (
    CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION,
    MAX_ANCHOR_OFFSET_DAYS,
    MAX_PAYMENT_SCHEDULE_ITEMS,
    MAX_PAYMENT_TERMS_TEXT_LENGTH,
    AnchoredPaymentRule,
    ContractPaymentTerms,
    ContractPaymentTermsError,
    ExplicitPaymentDate,
    PaymentScheduleItem,
)

_ROLL_CONVENTIONS = (
    BusinessDayConvention.FOLLOWING,
    BusinessDayConvention.MODIFIED_FOLLOWING,
    BusinessDayConvention.PRECEDING,
)


@pytest.mark.parametrize("field_name", ["item_id", "source_reference"])
def test_payment_text_rejects_unpaired_surrogates(field_name: str) -> None:
    with pytest.raises(ContractPaymentTermsError) as caught:
        _item(**{field_name: "sensitive-value-\ud800"})
    assert caught.value.code == "text_not_utf8"
    assert "sensitive-value" not in str(caught.value)


def test_payment_canonical_decoder_rejects_unpaired_surrogates() -> None:
    document = ContractPaymentTerms(
        quantity_basis_reference="declared-quantity", items=(_item(),)
    ).canonical_document()
    document["quantity_basis_reference"] = "sensitive-value-\udfff"
    with pytest.raises(ContractPaymentTermsError) as caught:
        ContractPaymentTerms.from_canonical_document(document)
    assert caught.value.code == "text_not_utf8"
    assert "sensitive-value" not in str(caught.value)

#: Golden S1a canonical bytes: ``upstream-contract-revision/v1`` documents
#: always carry ``payment_terms: null`` and their hashes stay readable. Any
#: change to this literal means the v1 schema was silently altered.
_REVISION_V1_GOLDEN_JSON = (
    '{"allowed_exit_points":["NBP","TTF"],"annual_financing_rate_pct":"6",'
    '"contract_id":"ttf-supply-2025","contract_price_gbp_mwh":"29.75",'
    '"delivery_point_name":"TTF","delivery_quantity_mwh_per_day":"125.5",'
    '"delivery_tolerance_pct":"2","eligible_sale_modes":["TARGET_MARKET_SALE",'
    '"LOCAL_MARKET_SALE"],"fuel_loss_allowance_pct":null,"gas_year":"2025+",'
    '"mapping_issues":[],"nomination_tolerance_pct":"1",'
    '"numeric_source_precision":"exact_decimal",'
    '"owned_entry_capacity_mwh_per_day":null,'
    '"owned_exit_capacity_mwh_per_day":null,"payment_terms":null,'
    '"regas_fee_gbp_mwh":null,"resource_type":"PIPELINE_IMPORT",'
    '"schema_version":"upstream-contract-revision/v1",'
    '"screen_sale_cash_lag_days":1,"settlement_frequency":"monthly",'
    '"tolerance_risk_allowance_gbp_mwh":null,"upstream_payment_lag_days":20,'
    '"variable_cost_gbp_mwh":null}'
)
_REVISION_V1_GOLDEN_HASH = (
    "sha256:0da96e194d9ed9028ece91da0be5df11b6cea640225934e63160c59013b136a2"
)


def _explicit_spec(**overrides: object) -> ExplicitPaymentDate:
    """Build one valid explicit-date specification (valid unless overridden)."""

    values: dict[str, object] = {
        "final_payable_date": date(2026, 11, 30),
        "source_reference": "invoice INV-2026-0042",
    }
    values.update(overrides)
    return ExplicitPaymentDate(**values)  # type: ignore[arg-type]


def _anchored_spec(**overrides: object) -> AnchoredPaymentRule:
    """Build one valid anchored rule (valid unless overridden)."""

    values: dict[str, object] = {
        "anchor_event": PaymentAnchorEvent.INVOICE_DATE,
        "anchor_offset_days": 20,
        "offset_day_kind": PaymentOffsetDayKind.CALENDAR_DAYS,
        "business_day_convention": BusinessDayConvention.NONE,
        "source_reference": "contract clause 7.2",
    }
    values.update(overrides)
    return AnchoredPaymentRule(**values)  # type: ignore[arg-type]


def _item(**overrides: object) -> PaymentScheduleItem:
    """Build one valid schedule item (valid unless overridden)."""

    values: dict[str, object] = {
        "item_id": "item-1",
        "cash_flow_category": CashFlowLegCategory.CARGO_PURCHASE,
        "flow_direction": PaymentFlowDirection.OUTFLOW,
        "source_reference": "contract schedule 1",
        "date_specification": _explicit_spec(),
    }
    values.update(overrides)
    return PaymentScheduleItem(**values)  # type: ignore[arg-type]


def _terms(**overrides: object) -> ContractPaymentTerms:
    """Build one valid schedule (valid unless overridden)."""

    values: dict[str, object] = {
        "quantity_basis_reference": "invoice_quantity",
        "items": (_item(),),
    }
    values.update(overrides)
    return ContractPaymentTerms(**values)  # type: ignore[arg-type]


def _refusal(callable_) -> str:
    """Run one refused construction/decode and return its stable code."""

    with pytest.raises(ContractPaymentTermsError) as excinfo:
        callable_()
    return excinfo.value.code


def _revision_v1_snapshot() -> UpstreamContractEconomicSnapshot:
    """Build one exact-decimal v1 economic snapshot (golden fixture)."""

    return UpstreamContractEconomicSnapshot(
        contract_id="ttf-supply-2025",
        resource_type="PIPELINE_IMPORT",
        delivery_point_name="TTF",
        gas_year="2025+",
        delivery_quantity_mwh_per_day=Decimal("125.5"),
        contract_price_gbp_mwh=Decimal("29.75"),
        settlement_frequency="monthly",
        upstream_payment_lag_days=20,
        screen_sale_cash_lag_days=1,
        delivery_tolerance_pct=Decimal("2"),
        nomination_tolerance_pct=Decimal("1"),
        annual_financing_rate_pct=Decimal("6"),
        allowed_exit_points=("NBP", "TTF"),
        eligible_sale_modes=("TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"),
        numeric_source_precision=SOURCE_PRECISION_EXACT_DECIMAL,
    )


# ---------------------------------------------------------------------------
# Accepted date shapes
# ---------------------------------------------------------------------------


def test_explicit_date_shape_roundtrips_with_its_evidence() -> None:
    terms = _terms()
    document = terms.canonical_document()

    assert document == {
        "schema_version": CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION,
        "quantity_basis_reference": "invoice_quantity",
        "items": [
            {
                "item_id": "item-1",
                "cash_flow_category": "cargo_purchase",
                "flow_direction": "OUTFLOW",
                "source_reference": "contract schedule 1",
                "date_specification": {
                    "kind": "EXPLICIT_DATE",
                    "final_payable_date": "2026-11-30",
                    "source_reference": "invoice INV-2026-0042",
                },
            }
        ],
    }
    rebuilt = ContractPaymentTerms.from_canonical_document(
        json.loads(terms.canonical_json())
    )

    assert rebuilt == terms
    assert rebuilt.items[0].date_specification == _explicit_spec()


def test_anchored_rule_with_calendar_days_and_no_roll_keeps_calendar_null() -> None:
    rule = _anchored_spec()
    terms = _terms(items=(_item(date_specification=rule),))
    specification = terms.canonical_document()["items"][0]["date_specification"]  # type: ignore[index]

    assert specification == {
        "kind": "ANCHORED_RULE",
        "anchor_event": "INVOICE_DATE",
        "anchor_offset_days": 20,
        "offset_day_kind": "CALENDAR_DAYS",
        "business_day_convention": "NONE",
        "calendar_reference": None,
        "source_reference": "contract clause 7.2",
    }
    assert (
        ContractPaymentTerms.from_canonical_document(
            json.loads(terms.canonical_json())
        )
        == terms
    )


def test_anchored_rule_with_business_days_requires_and_keeps_calendar() -> None:
    rule = _anchored_spec(
        offset_day_kind=PaymentOffsetDayKind.BUSINESS_DAYS,
        business_day_convention=BusinessDayConvention.MODIFIED_FOLLOWING,
        calendar_reference="TARGET2",
    )
    rebuilt = ContractPaymentTerms.from_canonical_document(
        json.loads(_terms(items=(_item(date_specification=rule),)).canonical_json())
    )

    assert rebuilt.items[0].date_specification == rule
    assert rebuilt.items[0].date_specification.calendar_reference == "TARGET2"


@pytest.mark.parametrize("anchor_event", list(PaymentAnchorEvent))
def test_every_reviewed_anchor_event_is_accepted(anchor_event: PaymentAnchorEvent) -> None:
    rule = _anchored_spec(anchor_event=anchor_event)

    assert rule.anchor_event is anchor_event
    assert (
        ContractPaymentTerms.from_canonical_document(
            json.loads(_terms(items=(_item(date_specification=rule),)).canonical_json())
        )
        .items[0]
        .date_specification
        == rule
    )


@pytest.mark.parametrize(
    "convention",
    [
        BusinessDayConvention.NONE,
        *tuple(_ROLL_CONVENTIONS),
    ],
)
def test_every_reviewed_convention_is_accepted(
    convention: BusinessDayConvention,
) -> None:
    overrides: dict[str, object] = {"business_day_convention": convention}
    if convention is not BusinessDayConvention.NONE:
        overrides["calendar_reference"] = "TARGET2"
    rule = _anchored_spec(**overrides)

    assert rule.business_day_convention is convention
    assert (
        ContractPaymentTerms.from_canonical_document(
            json.loads(_terms(items=(_item(date_specification=rule),)).canonical_json())
        )
        .items[0]
        .date_specification
        == rule
    )


def test_zero_offset_is_declared_explicitly_and_roll_needs_a_calendar() -> None:
    rule = _anchored_spec(
        anchor_offset_days=0,
        business_day_convention=BusinessDayConvention.FOLLOWING,
        calendar_reference="TARGET2",
    )

    assert rule.anchor_offset_days == 0
    assert (
        _terms(items=(_item(date_specification=rule),)).canonical_document()["items"][0][
            "date_specification"
        ]["anchor_offset_days"]
        == 0
    )


# ---------------------------------------------------------------------------
# Canonical determinism, order, strings and scope
# ---------------------------------------------------------------------------


def test_schedule_preserves_order_and_purchase_versus_sale_categories() -> None:
    purchase = _item(
        item_id="purchase-1",
        cash_flow_category=CashFlowLegCategory.CARGO_PURCHASE,
        date_specification=_explicit_spec(),
    )
    sale = _item(
        item_id="sale-1",
        cash_flow_category=CashFlowLegCategory.CARGO_SALE,
        date_specification=_anchored_spec(
            anchor_event=PaymentAnchorEvent.DELIVERY_PERIOD_END,
            anchor_offset_days=30,
        ),
    )
    terms = _terms(items=(purchase, sale))
    reversed_terms = _terms(items=(sale, purchase))

    document_items = terms.canonical_document()["items"]
    assert [entry["item_id"] for entry in document_items] == ["purchase-1", "sale-1"]
    assert [entry["cash_flow_category"] for entry in document_items] == [
        "cargo_purchase",
        "cargo_sale",
    ]
    assert [entry["flow_direction"] for entry in document_items] == [
        "OUTFLOW",
        "OUTFLOW",
    ]
    assert terms.canonical_json() != reversed_terms.canonical_json()
    assert (
        ContractPaymentTerms.from_canonical_document(
            json.loads(terms.canonical_json())
        ).items[0].cash_flow_category
        is CashFlowLegCategory.CARGO_PURCHASE
    )


@pytest.mark.parametrize("category", list(CashFlowLegCategory))
@pytest.mark.parametrize("direction", list(PaymentFlowDirection))
def test_any_category_accepts_either_declared_direction(
    category: CashFlowLegCategory, direction: PaymentFlowDirection
) -> None:
    """No category implies a sign: every category accepts either direction."""

    item = _item(cash_flow_category=category, flow_direction=direction)
    terms = _terms(items=(item,))

    assert item.flow_direction is direction
    assert terms.canonical_document()["items"][0]["flow_direction"] == direction.value
    assert (
        ContractPaymentTerms.from_canonical_document(
            json.loads(terms.canonical_json())
        )
        == terms
    )


def test_purchase_sale_and_refund_items_declare_direction_explicitly() -> None:
    """A refund reverses the usual sign, so only the declaration can say so."""

    purchase = _item(
        item_id="purchase-1",
        cash_flow_category=CashFlowLegCategory.CARGO_PURCHASE,
        flow_direction=PaymentFlowDirection.OUTFLOW,
    )
    purchase_refund = _item(
        item_id="purchase-refund-1",
        cash_flow_category=CashFlowLegCategory.CARGO_PURCHASE,
        flow_direction=PaymentFlowDirection.INFLOW,
        source_reference="supplier credit note CN-7",
    )
    sale = _item(
        item_id="sale-1",
        cash_flow_category=CashFlowLegCategory.CARGO_SALE,
        flow_direction=PaymentFlowDirection.INFLOW,
    )
    sale_refund = _item(
        item_id="sale-refund-1",
        cash_flow_category=CashFlowLegCategory.CARGO_SALE,
        flow_direction=PaymentFlowDirection.OUTFLOW,
        source_reference="customer refund clause 4.3",
    )
    terms = _terms(items=(purchase, purchase_refund, sale, sale_refund))
    document_items = terms.canonical_document()["items"]

    assert [
        (entry["cash_flow_category"], entry["flow_direction"])
        for entry in document_items
    ] == [
        ("cargo_purchase", "OUTFLOW"),
        ("cargo_purchase", "INFLOW"),
        ("cargo_sale", "INFLOW"),
        ("cargo_sale", "OUTFLOW"),
    ]
    rebuilt = ContractPaymentTerms.from_canonical_document(
        json.loads(terms.canonical_json())
    )
    assert rebuilt == terms
    assert rebuilt.items[1].flow_direction is PaymentFlowDirection.INFLOW
    assert rebuilt.items[3].flow_direction is PaymentFlowDirection.OUTFLOW


def test_flow_direction_is_mandatory_with_no_default() -> None:
    flow_field = next(
        field for field in fields(PaymentScheduleItem) if field.name == "flow_direction"
    )
    assert flow_field.default is MISSING
    assert flow_field.default_factory is MISSING
    with pytest.raises(TypeError):
        PaymentScheduleItem(  # type: ignore[call-arg]
            item_id="item-1",
            cash_flow_category=CashFlowLegCategory.CARGO_PURCHASE,
            source_reference="contract schedule 1",
            date_specification=_explicit_spec(),
        )

    document = _terms().canonical_document()
    del document["items"][0]["flow_direction"]  # type: ignore[index]
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(document)
    ) == "canonical_field_set_mismatch"


def test_flow_direction_refuses_raw_strings_and_unknown_values() -> None:
    assert _refusal(lambda: _item(flow_direction="INFLOW")) == "flow_direction_unknown"
    assert _refusal(lambda: _item(flow_direction="OUTFLOW")) == "flow_direction_unknown"
    assert _refusal(lambda: _item(flow_direction="SIDEWAYS")) == "flow_direction_unknown"

    broken = _terms().canonical_document()
    broken["items"][0]["flow_direction"] = "sideways"  # type: ignore[index]
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(broken)
    ) == "canonical_flow_direction_unknown"

    not_text = _terms().canonical_document()
    not_text["items"][0]["flow_direction"] = 1  # type: ignore[index]
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(not_text)
    ) == "canonical_flow_direction_unknown"


def test_schedule_items_are_frozen_values_with_fresh_documents() -> None:
    item = _item()
    terms = _terms(items=(item,))

    with pytest.raises(FrozenInstanceError):
        item.flow_direction = PaymentFlowDirection.INFLOW  # type: ignore[misc]
    assert hash(item) == hash(_item())
    assert hash(terms) == hash(_terms())

    first_document = terms.canonical_document()
    first_document["items"][0]["flow_direction"] = "SIDEWAYS"  # type: ignore[index]
    assert terms.canonical_document()["items"][0]["flow_direction"] == "OUTFLOW"
    assert terms.canonical_json() == _terms().canonical_json()


def test_terms_materialize_any_sequence_into_a_frozen_tuple() -> None:
    source = [_item()]
    terms = _terms(items=source)

    assert isinstance(terms.items, tuple)
    source.append(_item(item_id="item-2", flow_direction=PaymentFlowDirection.INFLOW))
    assert [item.item_id for item in terms.items] == ["item-1"]


def test_canonical_json_is_deterministic_and_strings_are_never_rewritten() -> None:
    terms = _terms(
        quantity_basis_reference=" invoiced quantity — 计量基准 ",
        items=(
            _item(
                item_id="item 1",
                source_reference="contract §7.2 — annex B",
                date_specification=_explicit_spec(
                    source_reference="发票 INV-2026-0042"
                ),
            ),
        ),
    )
    again = _terms(
        quantity_basis_reference=" invoiced quantity — 计量基准 ",
        items=(
            _item(
                item_id="item 1",
                source_reference="contract §7.2 — annex B",
                date_specification=_explicit_spec(
                    source_reference="发票 INV-2026-0042"
                ),
            ),
        ),
    )

    assert terms.canonical_json() == again.canonical_json()
    assert terms.canonical_json() == terms.canonical_json()
    text = terms.canonical_json()
    assert "计量基准" in text and "发票" in text  # ensure_ascii=False
    assert "item 1" in text and "contract §7.2" in text
    rebuilt = ContractPaymentTerms.from_canonical_document(json.loads(text))
    assert rebuilt.quantity_basis_reference == " invoiced quantity — 计量基准 "
    assert rebuilt.items[0].source_reference == "contract §7.2 — annex B"


def test_kind_is_a_class_discriminator_not_a_forgeable_field() -> None:
    assert ExplicitPaymentDate.kind is PaymentDateSpecificationKind.EXPLICIT_DATE
    assert AnchoredPaymentRule.kind is PaymentDateSpecificationKind.ANCHORED_RULE
    assert "kind" not in {field.name for field in fields(ExplicitPaymentDate)}
    assert "kind" not in {field.name for field in fields(AnchoredPaymentRule)}


def test_payment_terms_consume_the_reviewed_vocabulary_and_shared_cash_enum() -> None:
    """No parallel taxonomy: the domain model reuses the reviewed vocabularies."""

    assert payment_terms.PaymentAnchorEvent is PaymentAnchorEvent
    assert payment_terms.PaymentOffsetDayKind is PaymentOffsetDayKind
    assert payment_terms.BusinessDayConvention is BusinessDayConvention
    assert payment_terms.PaymentFlowDirection is PaymentFlowDirection
    assert payment_terms.CashFlowLegCategory is CashFlowLegCategory
    assert {member.value for member in PaymentAnchorEvent} == {
        "INVOICE_DATE",
        "DELIVERY_PERIOD_START",
        "DELIVERY_PERIOD_END",
        "METER_READ_DATE",
    }
    assert {member.value for member in PaymentFlowDirection} == {"INFLOW", "OUTFLOW"}
    assert {member.value for member in PaymentOffsetDayKind} == {
        "CALENDAR_DAYS",
        "BUSINESS_DAYS",
    }
    assert {member.value for member in BusinessDayConvention} == {
        "NONE",
        "FOLLOWING",
        "MODIFIED_FOLLOWING",
        "PRECEDING",
    }


def test_schema_carries_no_amount_rate_or_day_count_field() -> None:
    forbidden_fragments = (
        "amount",
        "rate",
        "fx",
        "discount",
        "day_count",
        "accrual",
        "sign",
    )
    schedule_types = (
        ContractPaymentTerms,
        PaymentScheduleItem,
        ExplicitPaymentDate,
        AnchoredPaymentRule,
    )
    for dataclass_ in schedule_types:
        for field in fields(dataclass_):
            assert not any(fragment in field.name for fragment in forbidden_fragments), (
                dataclass_.__name__,
                field.name,
            )
    # No date resolution exists here either: the module never imports timedelta.
    assert "timedelta" not in inspect.getsource(payment_terms)
    assert not hasattr(_anchored_spec(), "payment_date")


# ---------------------------------------------------------------------------
# Refusals: invalid values, unknown enums, empty evidence, duplicates, bounds
# ---------------------------------------------------------------------------


def test_unknown_or_untyped_rule_vocabulary_is_refused() -> None:
    assert _refusal(lambda: _anchored_spec(anchor_event="INVOICE_DATE")) == (
        "anchor_event_unknown"
    )
    assert _refusal(lambda: _anchored_spec(anchor_event="invoice_date")) == (
        "anchor_event_unknown"
    )
    assert _refusal(lambda: _anchored_spec(offset_day_kind="CALENDAR_DAYS")) == (
        "offset_day_kind_unknown"
    )
    assert _refusal(
        lambda: _anchored_spec(business_day_convention="NONE")
    ) == "business_day_convention_unknown"
    assert _refusal(
        lambda: _item(cash_flow_category="cargo_purchase")
    ) == "cash_flow_category_unknown"
    assert _refusal(lambda: _item(flow_direction="INFLOW")) == "flow_direction_unknown"
    assert _refusal(
        lambda: _item(date_specification="EXPLICIT_DATE")
    ) == "date_specification_not_recognized"


def test_offset_must_be_an_explicit_nonnegative_integral_offset() -> None:
    assert _refusal(lambda: _anchored_spec(anchor_offset_days=True)) == (
        "offset_not_int"
    )
    assert _refusal(lambda: _anchored_spec(anchor_offset_days=20.0)) == (
        "offset_not_int"
    )
    assert _refusal(lambda: _anchored_spec(anchor_offset_days="20")) == (
        "offset_not_int"
    )
    assert _refusal(lambda: _anchored_spec(anchor_offset_days=-1)) == (
        "offset_negative"
    )
    assert _refusal(
        lambda: _anchored_spec(anchor_offset_days=MAX_ANCHOR_OFFSET_DAYS + 1)
    ) == "offset_bounds_exceeded"
    assert (
        _anchored_spec(anchor_offset_days=MAX_ANCHOR_OFFSET_DAYS).anchor_offset_days
        == MAX_ANCHOR_OFFSET_DAYS
    )


def test_calendar_is_required_when_a_count_or_roll_needs_it() -> None:
    assert _refusal(
        lambda: _anchored_spec(offset_day_kind=PaymentOffsetDayKind.BUSINESS_DAYS)
    ) == "reference_missing"
    for convention in _ROLL_CONVENTIONS:
        assert _refusal(
            lambda convention=convention: _anchored_spec(
                business_day_convention=convention
            )
        ) == "reference_missing"
    assert _refusal(
        lambda: _anchored_spec(
            offset_day_kind=PaymentOffsetDayKind.BUSINESS_DAYS,
            calendar_reference="   ",
        )
    ) == "reference_blank"
    assert _refusal(
        lambda: _anchored_spec(
            business_day_convention=BusinessDayConvention.FOLLOWING,
            calendar_reference=" ",
        )
    ) == "reference_blank"


def test_calendar_is_refused_when_nothing_needs_it() -> None:
    assert _refusal(
        lambda: _anchored_spec(calendar_reference="TARGET2")
    ) == "calendar_reference_not_applicable"
    assert _refusal(
        lambda: _anchored_spec(
            offset_day_kind=PaymentOffsetDayKind.CALENDAR_DAYS,
            business_day_convention=BusinessDayConvention.NONE,
            calendar_reference="",
        )
    ) == "calendar_reference_not_applicable"
    # A blank reference with no count/roll need is still an unused declaration.
    assert _refusal(lambda: _anchored_spec(calendar_reference="   ")) == (
        "calendar_reference_not_applicable"
    )


def test_dates_refuse_datetimes_and_non_dates() -> None:
    assert _refusal(
        lambda: _explicit_spec(final_payable_date=datetime(2026, 11, 30, 12, 0))
    ) == "date_is_datetime"
    assert _refusal(
        lambda: _explicit_spec(final_payable_date="2026-11-30")
    ) == "date_not_date"
    assert _refusal(lambda: _explicit_spec(final_payable_date=None)) == (
        "date_not_date"
    )


def test_evidence_is_mandatory_at_item_and_specification_level() -> None:
    assert _refusal(lambda: _item(source_reference=None)) == "reference_missing"
    assert _refusal(lambda: _item(source_reference="   ")) == "reference_blank"
    assert _refusal(lambda: _item(source_reference=42)) == "reference_not_string"
    assert _refusal(lambda: _explicit_spec(source_reference=None)) == (
        "reference_missing"
    )
    assert _refusal(lambda: _explicit_spec(source_reference="")) == "reference_blank"
    assert _refusal(lambda: _anchored_spec(source_reference=" ")) == "reference_blank"


def test_identity_and_evidence_size_guards_refuse_oversized_text() -> None:
    oversized = "x" * (MAX_PAYMENT_TERMS_TEXT_LENGTH + 1)

    assert _refusal(lambda: _item(item_id=oversized)) == (
        "item_id_storage_bounds_exceeded"
    )
    assert _refusal(lambda: _item(source_reference=oversized)) == (
        "reference_storage_bounds_exceeded"
    )
    assert _refusal(lambda: _explicit_spec(source_reference=oversized)) == (
        "reference_storage_bounds_exceeded"
    )
    assert _refusal(
        lambda: _terms(quantity_basis_reference=oversized)
    ) == "reference_storage_bounds_exceeded"


def test_item_identity_refusals() -> None:
    assert _refusal(lambda: _item(item_id=None)) == "item_id_missing"
    assert _refusal(lambda: _item(item_id="  ")) == "item_id_blank"
    assert _refusal(lambda: _item(item_id=7)) == "item_id_not_string"
    duplicate_schedule = (
        _item(item_id="dup"),
        _item(item_id="dup", date_specification=_anchored_spec()),
    )
    assert _refusal(
        lambda: _terms(items=duplicate_schedule)
    ) == "item_id_duplicate"


def test_schedule_container_refusals_and_bounds() -> None:
    assert _refusal(lambda: _terms(items=())) == "schedule_empty"
    assert _refusal(lambda: _terms(items="item-1")) == "items_not_sequence"
    assert _refusal(lambda: _terms(items=(entry for entry in ()))) == (
        "items_not_sequence"
    )
    assert _refusal(lambda: _terms(items=({"item_id": "x"},))) == (
        "item_not_recognized"
    )
    too_many = tuple(_item(item_id=f"item-{index}") for index in range(
        MAX_PAYMENT_SCHEDULE_ITEMS + 1
    ))
    assert _refusal(lambda: _terms(items=too_many)) == "schedule_bounds_exceeded"


def test_unsupported_schema_version_is_refused() -> None:
    assert _refusal(lambda: _terms(schema_version="contract-payment-terms/v2")) == (
        "schema_version_mismatch"
    )
    document = _terms().canonical_document()
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(
            {**document, "schema_version": "contract-payment-terms/v2"}
        )
    ) == "canonical_schema_version_mismatch"


# ---------------------------------------------------------------------------
# Canonical decode strictness
# ---------------------------------------------------------------------------


def test_canonical_decode_rejects_unknown_extra_and_mixed_fields() -> None:
    document = _terms().canonical_document()

    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document([document])
    ) == "canonical_not_mapping"
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(
            {**document, "unexpected": 1}
        )
    ) == "canonical_field_set_mismatch"
    missing_basis = {
        key: value
        for key, value in document.items()
        if key != "quantity_basis_reference"
    }
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(missing_basis)
    ) == "canonical_field_set_mismatch"

    mixed = _terms().canonical_document()
    mixed["items"][0]["date_specification"] = {
        **_explicit_spec_document(),
        "anchor_event": "INVOICE_DATE",
    }
    assert _refusal(lambda: ContractPaymentTerms.from_canonical_document(mixed)) == (
        "canonical_field_set_mismatch"
    )

    anchored_missing_calendar = _terms().canonical_document()
    anchored_missing_calendar["items"][0]["date_specification"] = {
        key: value
        for key, value in _anchored_spec_document().items()
        if key != "calendar_reference"
    }
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(anchored_missing_calendar)
    ) == "canonical_field_set_mismatch"


def test_canonical_decode_rejects_unknown_discriminator_and_enum_values() -> None:
    unknown_kind = _terms().canonical_document()
    unknown_kind["items"][0]["date_specification"] = {
        **_explicit_spec_document(),
        "kind": "INFERRED_DATE",
    }
    assert _refusal(lambda: ContractPaymentTerms.from_canonical_document(unknown_kind)) == (
        "canonical_kind_unknown"
    )

    missing_kind = _terms().canonical_document()
    missing_kind["items"][0]["date_specification"] = {
        "final_payable_date": "2026-11-30",
        "source_reference": "invoice INV-2026-0042",
    }
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(missing_kind)
    ) == "canonical_kind_missing"

    for field_name, value in (
        ("anchor_event", "INVOICE_DATES"),
        ("offset_day_kind", "WEEKDAYS"),
        ("business_day_convention", "NEAREST"),
    ):
        broken = _terms().canonical_document()
        broken["items"][0]["date_specification"] = {
            **_anchored_spec_document(),
            field_name: value,
        }
        assert _refusal(
            lambda broken=broken: ContractPaymentTerms.from_canonical_document(broken)
        ) == f"canonical_{field_name}_unknown"

    broken_category = _terms().canonical_document()
    broken_category["items"][0]["cash_flow_category"] = "nomination_fee"
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(broken_category)
    ) == "canonical_cash_flow_category_unknown"


def test_canonical_decode_refuses_boolean_offsets_and_invalid_dates() -> None:
    boolean_offset = _terms().canonical_document()
    boolean_offset["items"][0]["date_specification"] = {
        **_anchored_spec_document(),
        "anchor_offset_days": True,
    }
    assert _refusal(lambda: ContractPaymentTerms.from_canonical_document(boolean_offset)) == (
        "canonical_offset_not_int"
    )

    negative_offset = _terms().canonical_document()
    negative_offset["items"][0]["date_specification"] = {
        **_anchored_spec_document(),
        "anchor_offset_days": -5,
    }
    assert _refusal(lambda: ContractPaymentTerms.from_canonical_document(negative_offset)) == (
        "offset_negative"
    )

    for spelling in ("2026-11-30T00:00:00", "2026-1-2", "2026-02-30", "not-a-date", ""):
        broken = _terms().canonical_document()
        broken["items"][0]["date_specification"] = {
            **_explicit_spec_document(),
            "final_payable_date": spelling,
        }
        assert _refusal(
            lambda broken=broken: ContractPaymentTerms.from_canonical_document(broken)
        ) == "canonical_date_invalid", spelling

    for spelling in ("20261130", "2026-W48-1"):
        noncanonical = _terms().canonical_document()
        noncanonical["items"][0]["date_specification"] = {
            **_explicit_spec_document(),
            "final_payable_date": spelling,
        }
        assert _refusal(
            lambda noncanonical=noncanonical: ContractPaymentTerms.from_canonical_document(
                noncanonical
            )
        ) == "canonical_date_not_plain_iso", spelling

    number_date = _terms().canonical_document()
    number_date["items"][0]["date_specification"] = {
        **_explicit_spec_document(),
        "final_payable_date": 20261130,
    }
    assert _refusal(lambda: ContractPaymentTerms.from_canonical_document(number_date)) == (
        "canonical_date_not_string"
    )


def test_canonical_decode_refuses_empty_evidence_and_noncanonical_items() -> None:
    empty_evidence = _terms().canonical_document()
    empty_evidence["items"][0]["source_reference"] = " "
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(empty_evidence)
    ) == "reference_blank"

    empty_spec_evidence = _terms().canonical_document()
    empty_spec_evidence["items"][0]["date_specification"] = {
        **_explicit_spec_document(),
        "source_reference": "",
    }
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(empty_spec_evidence)
    ) == "reference_blank"

    duplicate = _terms().canonical_document()
    duplicate["items"] = [duplicate["items"][0], duplicate["items"][0]]
    assert _refusal(lambda: ContractPaymentTerms.from_canonical_document(duplicate)) == (
        "item_id_duplicate"
    )

    blank_calendar = _terms().canonical_document()
    blank_calendar["items"][0]["date_specification"] = {
        **_anchored_spec_document(
            offset_day_kind="BUSINESS_DAYS", calendar_reference=" "
        ),
    }
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(blank_calendar)
    ) == "reference_blank"

    not_a_mapping_item = _terms().canonical_document()
    not_a_mapping_item["items"] = ["item-1"]
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(not_a_mapping_item)
    ) == "canonical_item_not_mapping"

    not_an_array = _terms().canonical_document()
    not_an_array["items"] = {"item-1": {}}
    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(not_an_array)
    ) == "canonical_items_not_sequence"


# ---------------------------------------------------------------------------
# Sanitized refusals: no untrusted value, key or repr may be echoed
# ---------------------------------------------------------------------------

_SENTINEL = "sentinel-untrusted-7f31c2"

#: A class whose *name* is the sentinel: a type label that must not be echoed.
_SENTINEL_CLASS = type(_SENTINEL, (), {})


def _assert_sanitized_refusal(
    excinfo: pytest.ExceptionInfo[ContractPaymentTermsError],
) -> None:
    """Assert neither the message nor the detail contains the sentinel."""

    assert _SENTINEL not in str(excinfo.value)
    assert _SENTINEL not in excinfo.value.detail


def test_constructor_refusals_never_echo_untrusted_values_or_type_names() -> None:
    cases: list[tuple[str, object, str]] = [
        (
            "flow direction value",
            lambda: _item(flow_direction=_SENTINEL),
            "flow_direction_unknown",
        ),
        (
            "cash-flow category value",
            lambda: _item(cash_flow_category=_SENTINEL),
            "cash_flow_category_unknown",
        ),
        (
            "anchor event value",
            lambda: _anchored_spec(anchor_event=_SENTINEL),
            "anchor_event_unknown",
        ),
        (
            "offset day kind value",
            lambda: _anchored_spec(offset_day_kind=_SENTINEL),
            "offset_day_kind_unknown",
        ),
        (
            "business-day convention value",
            lambda: _anchored_spec(business_day_convention=_SENTINEL),
            "business_day_convention_unknown",
        ),
        (
            "class name of a wrong-typed value",
            lambda: _item(flow_direction=_SENTINEL_CLASS()),
            "flow_direction_unknown",
        ),
        (
            "directed date value",
            lambda: _explicit_spec(final_payable_date=_SENTINEL),
            "date_not_date",
        ),
        (
            "schema version value",
            lambda: _terms(schema_version=_SENTINEL),
            "schema_version_mismatch",
        ),
    ]

    for label, call, expected_code in cases:
        with pytest.raises(ContractPaymentTermsError) as excinfo:
            call()
        assert excinfo.value.code == expected_code, label
        _assert_sanitized_refusal(excinfo)


def test_decode_refusals_never_echo_untrusted_values_or_field_names() -> None:
    def bad_flow(value: object) -> dict[str, object]:
        document = _terms().canonical_document()
        document["items"][0]["flow_direction"] = value  # type: ignore[index]
        return document

    def bad_item_field(field_name: object, value: object) -> dict[str, object]:
        document = _terms().canonical_document()
        document["items"][0][field_name] = value  # type: ignore[index]
        return document

    def bad_document_field(field_name: object, value: object) -> dict[str, object]:
        document = _terms().canonical_document()
        document[field_name] = value  # type: ignore[index]
        return document

    def bad_specification(specification: dict[str, object]) -> dict[str, object]:
        document = _terms().canonical_document()
        document["items"][0]["date_specification"] = specification  # type: ignore[index]
        return document

    duplicate = _terms().canonical_document()
    duplicate["items"] = [duplicate["items"][0], duplicate["items"][0]]  # type: ignore[list-item]
    duplicate["items"][0]["item_id"] = _SENTINEL  # type: ignore[index]

    cases: list[tuple[str, dict[str, object], str]] = [
        (
            "flow direction value",
            bad_flow(_SENTINEL),
            "canonical_flow_direction_unknown",
        ),
        (
            "cash-flow category value",
            bad_item_field("cash_flow_category", _SENTINEL),
            "canonical_cash_flow_category_unknown",
        ),
        (
            "date-specification kind",
            bad_specification({**_explicit_spec_document(), "kind": _SENTINEL}),
            "canonical_kind_unknown",
        ),
        (
            "anchor event value",
            bad_specification({**_anchored_spec_document(), "anchor_event": _SENTINEL}),
            "canonical_anchor_event_unknown",
        ),
        (
            "offset day kind value",
            bad_specification(
                {**_anchored_spec_document(), "offset_day_kind": _SENTINEL}
            ),
            "canonical_offset_day_kind_unknown",
        ),
        (
            "business-day convention value",
            bad_specification(
                {**_anchored_spec_document(), "business_day_convention": _SENTINEL}
            ),
            "canonical_business_day_convention_unknown",
        ),
        (
            "date spelling",
            bad_specification(
                {**_explicit_spec_document(), "final_payable_date": _SENTINEL}
            ),
            "canonical_date_invalid",
        ),
        (
            "schema version",
            bad_document_field("schema_version", _SENTINEL),
            "canonical_schema_version_mismatch",
        ),
        (
            "unexpected document field name",
            bad_document_field(_SENTINEL, 1),
            "canonical_field_set_mismatch",
        ),
        (
            "unexpected item field name",
            bad_item_field(_SENTINEL, 1),
            "canonical_field_set_mismatch",
        ),
        (
            "unexpected date-specification field name",
            bad_specification({**_explicit_spec_document(), _SENTINEL: 1}),
            "canonical_field_set_mismatch",
        ),
        ("duplicate item id", duplicate, "item_id_duplicate"),
    ]

    for label, document, expected_code in cases:
        with pytest.raises(ContractPaymentTermsError) as excinfo:
            ContractPaymentTerms.from_canonical_document(document)
        assert excinfo.value.code == expected_code, label
        _assert_sanitized_refusal(excinfo)


class _UncollectableKeysMapping(Mapping):
    """Mapping whose keys cannot be collected as a set (unhashable keys)."""

    def __getitem__(self, key: object) -> object:
        raise KeyError(key)

    def __iter__(self):
        return iter([["schema_version"]])

    def __len__(self) -> int:
        return 1


class _ExplodingKey:
    """Non-string field name whose str/repr a refusal must never touch."""

    def __hash__(self) -> int:
        return -819855292

    def __repr__(self) -> str:
        raise AssertionError("repr must not be called on a caller field name")

    def __str__(self) -> str:
        raise AssertionError("str must not be called on a caller field name")


def test_malformed_mappings_and_non_string_keys_refuse_without_crashing() -> None:
    with pytest.raises(ContractPaymentTermsError) as excinfo:
        ContractPaymentTerms.from_canonical_document(_UncollectableKeysMapping())
    assert excinfo.value.code == "canonical_field_set_mismatch"

    non_string_keys = {
        _ExplodingKey(): 1,
        "quantity_basis_reference": "invoice_quantity",
        "items": [],
    }
    with pytest.raises(ContractPaymentTermsError) as excinfo:
        ContractPaymentTerms.from_canonical_document(non_string_keys)
    assert excinfo.value.code == "canonical_field_set_mismatch"

    item_with_key = _terms().canonical_document()
    item_with_key["items"][0][_ExplodingKey()] = 1  # type: ignore[index]
    with pytest.raises(ContractPaymentTermsError) as excinfo:
        ContractPaymentTerms.from_canonical_document(item_with_key)
    assert excinfo.value.code == "canonical_field_set_mismatch"

    specification_with_key = _terms().canonical_document()
    specification_with_key["items"][0]["date_specification"][_ExplodingKey()] = 1  # type: ignore[index]
    with pytest.raises(ContractPaymentTermsError) as excinfo:
        ContractPaymentTerms.from_canonical_document(specification_with_key)
    assert excinfo.value.code == "canonical_field_set_mismatch"


def test_decode_refuses_oversized_item_arrays_before_decoding() -> None:
    document = _terms().canonical_document()
    document["items"] = [document["items"][0]] * (MAX_PAYMENT_SCHEDULE_ITEMS + 1)  # type: ignore[index]

    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(document)
    ) == "schedule_bounds_exceeded"


def test_decode_checks_the_field_set_before_reading_the_schema_version() -> None:
    document = _terms().canonical_document()
    document["unexpected_extra"] = 1
    document["schema_version"] = "contract-payment-terms/v2"

    assert _refusal(
        lambda: ContractPaymentTerms.from_canonical_document(document)
    ) == "canonical_field_set_mismatch"


def _explicit_spec_document(**overrides: object) -> dict[str, object]:
    """Canonical explicit-date document for decode tests."""

    values: dict[str, object] = {
        "kind": "EXPLICIT_DATE",
        "final_payable_date": "2026-11-30",
        "source_reference": "invoice INV-2026-0042",
    }
    values.update(overrides)
    return values


def _anchored_spec_document(**overrides: object) -> dict[str, object]:
    """Canonical anchored-rule document for decode tests."""

    values: dict[str, object] = {
        "kind": "ANCHORED_RULE",
        "anchor_event": "INVOICE_DATE",
        "anchor_offset_days": 20,
        "offset_day_kind": "CALENDAR_DAYS",
        "business_day_convention": "NONE",
        "calendar_reference": None,
        "source_reference": "contract clause 7.2",
    }
    values.update(overrides)
    return values


# ---------------------------------------------------------------------------
# Existing S1a revision-v1 golden behaviour
# ---------------------------------------------------------------------------


def test_revision_v1_golden_bytes_and_hash_are_unchanged() -> None:
    snapshot = _revision_v1_snapshot()

    assert snapshot.canonical_json() == _REVISION_V1_GOLDEN_JSON
    assert snapshot.content_hash() == _REVISION_V1_GOLDEN_HASH
    assert snapshot.payment_terms is None
    assert json.loads(_REVISION_V1_GOLDEN_JSON)["payment_terms"] is None
    assert (
        UpstreamContractEconomicSnapshot.from_canonical_document(
            json.loads(_REVISION_V1_GOLDEN_JSON)
        )
        == snapshot
    )


def test_payment_terms_schema_is_separate_from_revision_v1() -> None:
    terms = _terms()
    document = terms.canonical_document()

    assert contract_revision.CONTRACT_REVISION_SCHEMA_VERSION == (
        "upstream-contract-revision/v1"
    )
    assert CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION == "contract-payment-terms/v1"
    assert document["schema_version"] != contract_revision.CONTRACT_REVISION_SCHEMA_VERSION
    # The S2a document is a self-contained value; it never mutates or extends a
    # v1 revision document, whose payment_terms stays null.
    assert _revision_v1_snapshot().canonical_document()["payment_terms"] is None
    revision_fields = {
        field.name for field in fields(UpstreamContractEconomicSnapshot)
    }
    assert "quantity_basis_reference" not in revision_fields
    assert "items" not in revision_fields

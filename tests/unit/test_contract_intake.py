"""Contract PDF intake: text layer, term recognition with evidence, conversions, refusals."""

from __future__ import annotations

import pytest

from eurogas_nexus.application.contract_intake import (
    IntakeError,
    extract_terms,
    intake_pdf,
    read_pdf,
)
from eurogas_nexus.core.report_files import pdf_bytes

CONFIRMATION = [
    "INDIVIDUAL CONTRACT under the EFET General Agreement Concerning the Delivery and "
    "Acceptance of Natural Gas, Version 2.0/2007",
    "Contract Reference: NOR-2026-0142",
    "Seller: Nordic Upstream AS",
    "Buyer: Example Energy Trading Ltd",
    "Delivery Point: Title Transfer Facility (TTF) virtual trading point",
    "Delivery Period: from 01.10.2026 to 30.09.2027",
    "Daily Contract Quantity: 1.200.000 kWh/h",
    "Contract Price: 34,25 EUR/MWh",
    "Delivery tolerance: the Seller may deliver within plus or minus 5 % of the DCQ",
    "Nomination tolerance: 2 per cent",
    "Payment: invoices are payable on the 20th business day of the month",
    "This contract is governed by the laws of England and Wales.",
]


def _pdf(lines):
    return pdf_bytes([{"Clause": line} for line in lines], title="Confirmation")


def test_text_layer_is_read_page_by_page():
    texts, text_pages, ocr_pages = read_pdf(_pdf(CONFIRMATION))
    assert text_pages == 1 and ocr_pages == 0
    assert "NOR-2026-0142" in texts[0]


def test_terms_are_recognised_with_page_and_evidence():
    result = intake_pdf(
        _pdf(CONFIRMATION), file_name="Nordic conf.pdf", own_names={"example energy trading"}
    )
    terms = result.terms
    assert terms["contract_id"].value == "NOR-2026-0142"
    assert terms["counterparty"].value == "Nordic Upstream AS"  # the side that is not us
    assert terms["delivery_point_name"].value == "TTF"
    assert terms["gas_year"].value == "2026"
    assert terms["delivery_quantity_mwh_per_day"].value == pytest.approx(28_800.0)
    assert "kWh/h" in terms["delivery_quantity_mwh_per_day"].note
    assert terms["_contract_price"].value == 34.25 and terms["_contract_price"].unit == "EUR/MWh"
    assert "contract_price_gbp_mwh" not in terms  # a EUR price never lands in the GBP field
    assert terms["delivery_tolerance_pct"].value == 5.0
    assert terms["nomination_tolerance_pct"].value == 2.0
    assert "England" in terms["governing_law"].value
    assert terms["contract_id"].page == 1 and "NOR-2026-0142" in terms["contract_id"].evidence
    record = result.record()
    assert record["document_status"] == "PDF_EXTRACTED_REVIEW_REQUIRED"
    assert not any(key.startswith("_") for key in record)
    assert any("EUR/MWh" in warning for warning in result.warnings)


def test_pence_per_therm_and_therms_are_converted_to_mwh():
    terms = extract_terms(
        [
            "Seller: North Sea Gas Ltd\nBuyer: Example Energy Trading Ltd\n"
            "Delivery Point: NBP\nContract Quantity: 500,000 therms per day\n"
            "Contract Price: 85.50 p/therm\n"
        ],
        own_names={"example energy trading"},
    )
    assert terms["delivery_quantity_mwh_per_day"].value == pytest.approx(14_653.554, rel=1e-6)
    assert terms["contract_price_gbp_mwh"].value == pytest.approx(0.855 / 0.029307107, rel=1e-4)
    assert terms["counterparty"].value == "North Sea Gas Ltd"


def test_index_price_and_missing_terms_are_reported_not_guessed():
    result = intake_pdf(
        _pdf(["Seller: A", "Contract Price: TTF month-ahead index (ICIS Heren) plus 0.15 EUR/MWh"]),
        file_name="x.pdf",
        own_names=set(),
    )
    assert "TTF month-ahead index" in result.terms["index_basis"].value
    assert any("Not found" in w and "daily quantity" in w for w in result.warnings)
    assert "gas_year" not in result.terms


def test_refusals():
    with pytest.raises(IntakeError, match="not a PDF"):
        intake_pdf(b"hello", file_name="x.pdf")
    with pytest.raises(IntakeError):
        intake_pdf(b"%PDF-1.4 broken", file_name="x.pdf")

"""GB demand for a gas day: staged D+1 publications, confirmation and D+6.

Shapes are the provider's own (National Gas data portal, CSV ``latestFlag=N``):
gas day 12 Nov 2026 was published 0 at 10:20, 24.9298 at 11:20, 242.622 at 12:20,
239.619 at 14:20 and 239.595 at 17:20 on 13 Nov, all received by one download.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from eurogas_nexus.application.gb_demand import (
    D1Stage,
    DemandStatus,
    classify_d1_publications,
    demand_by_gas_day,
    demand_for_gas_day,
)
from eurogas_nexus.application.research.demand_target_inputs import (
    DEFAULT_REVISION_ORDER_POLICY,
    DemandTargetAmbiguityError,
    DemandTargetDiagnosticCode,
    RevisionOrderPolicy,
    build_demand_target_rows,
)
from eurogas_nexus.domain.research.weather_demand import _resolve_targets

DAY = date(2026, 11, 12)
ONE_DOWNLOAD = datetime(2026, 11, 14, 6, 33, 56, tzinfo=UTC)


def pub(
    record_id: str,
    value: str,
    applicable: datetime,
    *,
    gas_day: date = DAY,
    term: str = "D+1",
    generated: datetime | None = None,
    received: datetime = ONE_DOWNLOAD,
) -> SimpleNamespace:
    item = "PUBOB637" if term == "D+1" else "PUBOB652"
    return SimpleNamespace(
        record_id=record_id,
        source_publication_id=f"pub-{record_id}",
        provider_item_id=item,
        series_key=f"national-gas:actual:GB_NTS:{term}:CSV",
        region="GB_NTS",
        term=term,
        label=f"Demand Actual, NTS, {term}",
        gas_day=gas_day,
        value_text=value,
        value_is_blank=value == "",
        unit="mscm",
        received_at_utc=received,
        available_at_utc=received,
        ingested_at_utc=received,
        published_at_utc=None,
        applicable_at_raw=applicable.strftime("%d/%m/%Y %H:%M:%S"),
        generated_at_raw=(generated or applicable).strftime("%d/%m/%Y %H:%M:%S"),
        applicable_at_naive=applicable,
        generated_at_naive=generated or applicable,
        quality_indicator=None,
        provisional_status="PROVISIONAL_INITIAL" if term == "D+1" else "UNRESOLVED_D_PLUS_6",
        is_provisional=True if term == "D+1" else None,
        raw_sha256="a" * 64,
        source_url="https://data.nationalgas.com/api/find-gas-data-download",
        hash_schema="national_gas_actual_demand.v1",
        source_format="CSV",
        rest_provenance=None,
    )


def live_12_nov(received: datetime = ONE_DOWNLOAD) -> list[SimpleNamespace]:
    at = lambda h, m, s: datetime(2026, 11, 13, h, m, s)  # noqa: E731
    return [
        pub("hash-ffff", "0", at(10, 20, 0), received=received),
        pub("hash-0000", "24.9298", at(11, 20, 0), received=received),
        pub("hash-9999", "242.622", at(12, 20, 2), received=received),
        pub("hash-1111", "239.619", at(14, 20, 1), received=received),
        pub("hash-5555", "239.595", at(17, 20, 1), received=received),
    ]


def test_stages_of_the_live_shape_are_classified():
    stages = classify_d1_publications(live_12_nov())
    assert stages == {
        "hash-ffff": D1Stage.BUILD_UP,
        "hash-0000": D1Stage.BUILD_UP,
        "hash-9999": D1Stage.UNCONFIRMED,
        "hash-1111": D1Stage.CONFIRMED,
        "hash-5555": D1Stage.CONFIRMED,
    }


def test_rows_received_together_resolve_to_the_latest_provider_publication():
    # Record ids sort the partial stages last; the provider clock decides.
    result = demand_for_gas_day(live_12_nov(), gas_day=DAY, as_of=ONE_DOWNLOAD)
    assert result.status is DemandStatus.PROVISIONAL
    assert result.value_text == "239.595"
    assert result.available_at_utc == ONE_DOWNLOAD


def test_availability_stays_the_local_receipt():
    before_receipt = ONE_DOWNLOAD - timedelta(seconds=1)
    result = demand_for_gas_day(live_12_nov(), gas_day=DAY, as_of=before_receipt)
    assert result.status is DemandStatus.NOT_PUBLISHED
    assert result.value is None


@pytest.mark.parametrize(
    ("published_by", "status", "value"),
    [
        (datetime(2026, 11, 13, 10, 25, tzinfo=UTC), DemandStatus.BUILDING, None),
        (datetime(2026, 11, 13, 11, 25, tzinfo=UTC), DemandStatus.BUILDING, None),
        (
            datetime(2026, 11, 13, 12, 30, tzinfo=UTC),
            DemandStatus.AWAITING_CONFIRMATION,
            None,
        ),
        (datetime(2026, 11, 13, 14, 30, tzinfo=UTC), DemandStatus.PROVISIONAL, "239.619"),
    ],
)
def test_a_reader_polling_through_the_morning_never_sees_a_partial(published_by, status, value):
    # Each publication received five minutes after it was made.
    rows = [
        row
        for row in live_12_nov()
        if row.applicable_at_naive.replace(tzinfo=UTC) + timedelta(minutes=5) <= published_by
    ]
    for row in rows:
        row.available_at_utc = row.applicable_at_naive.replace(tzinfo=UTC) + timedelta(minutes=5)
        row.received_at_utc = row.available_at_utc
    result = demand_for_gas_day(rows, gas_day=DAY, as_of=published_by)
    assert result.status is status
    assert result.value_text == value


def test_wrong_value_at_1220_is_withheld_until_confirmed():
    # Gas day 28 Aug 2026: 999150 at 12:20 on 29 Aug, 151.026 on 30 Aug, 151.015 on 1 Sep.
    gd = date(2026, 8, 28)
    rows = [
        pub("a", "0.0206", datetime(2026, 8, 29, 10, 20, 1), gas_day=gd),
        pub("b", "999150", datetime(2026, 8, 29, 12, 20, 2), gas_day=gd),
        pub("c", "151.026", datetime(2026, 8, 30, 12, 20, 1), gas_day=gd),
    ]
    assert demand_for_gas_day(rows, gas_day=gd, as_of=ONE_DOWNLOAD).status is (
        DemandStatus.REVISION_UNCONFIRMED
    )
    rows.append(pub("d", "151.015", datetime(2026, 9, 1, 11, 20, 1), gas_day=gd))
    result = demand_for_gas_day(rows, gas_day=gd, as_of=ONE_DOWNLOAD)
    assert (result.status, result.value_text) == (DemandStatus.PROVISIONAL, "151.015")


def test_partial_published_after_noon_is_not_confirmed_by_itself():
    # Gas day 7 May 2026: 37.89 at 12:20, 93.08 at 14:20, 100.85 next day, then 180.4.
    gd = date(2026, 5, 7)
    rows = [
        pub("a", "37.8867", datetime(2026, 5, 8, 12, 20, 1), gas_day=gd),
        pub("b", "93.0756", datetime(2026, 5, 8, 14, 20, 1), gas_day=gd),
        pub("c", "100.848", datetime(2026, 5, 9, 12, 20, 1), gas_day=gd),
    ]
    assert not demand_for_gas_day(rows, gas_day=gd, as_of=ONE_DOWNLOAD).has_value
    rows += [
        pub("d", "180.402", datetime(2026, 5, 11, 9, 20, 1), gas_day=gd),
        pub("e", "180.39", datetime(2026, 5, 12, 12, 20, 1), gas_day=gd),
    ]
    assert demand_for_gas_day(rows, gas_day=gd, as_of=ONE_DOWNLOAD).value_text == "180.39"


def test_d6_is_the_settled_figure_and_wins_over_a_later_d1_amendment():
    gd = date(2026, 3, 31)
    rows = [
        pub("a", "209.572", datetime(2026, 4, 1, 12, 20, 1), gas_day=gd),
        pub("b", "209.04", datetime(2026, 4, 1, 14, 20, 1), gas_day=gd),
        pub("d6", "209.093", datetime(2026, 4, 6, 11, 20, 1), gas_day=gd, term="D+6",
            generated=datetime(2026, 4, 6, 12, 0)),
        pub("amend", "209.328", datetime(2026, 4, 5, 12, 20, 1), gas_day=gd,
            generated=datetime(2026, 4, 10, 13, 34, 7)),
    ]
    result = demand_for_gas_day(rows, gas_day=gd, as_of=ONE_DOWNLOAD)
    assert (result.status, result.value_text) == (DemandStatus.SETTLED, "209.093")


def test_confirmation_received_later_than_the_confirmed_row_does_not_count():
    gd = date(2026, 11, 10)
    early = datetime(2026, 11, 11, 13, 0, tzinfo=UTC)
    rows = [
        pub(
            "a",
            "284.148",
            datetime(2026, 11, 11, 12, 20),
            gas_day=gd,
            received=early + timedelta(days=1),
        ),
        pub("b", "284.147", datetime(2026, 11, 11, 14, 20), gas_day=gd, received=early),
    ]
    assert classify_d1_publications(rows)["b"] is D1Stage.UNCONFIRMED


def test_demand_by_gas_day_names_days_without_a_value():
    out = demand_by_gas_day(live_12_nov(), as_of=ONE_DOWNLOAD, gas_days=[DAY, date(2026, 11, 13)])
    assert out[date(2026, 11, 13)].status is DemandStatus.NOT_PUBLISHED
    assert out[DAY].value_text == "239.595"


def _build(records, **overrides):
    arguments = {
        "provider_item_id": "PUBOB637",
        "source_format": "CSV",
        "gas_day_from": date(2026, 11, 1),
        "gas_day_to": date(2026, 11, 30),
        "available_at_utc": ONE_DOWNLOAD + timedelta(days=1),
        "allow_provisional_targets": True,
    }
    arguments.update(overrides)
    return build_demand_target_rows(records, **arguments)


def test_default_target_policy_is_provider_order_with_the_day_rule():
    assert DEFAULT_REVISION_ORDER_POLICY is RevisionOrderPolicy.PROVIDER_PUBLICATION_ORDER_V1
    mapped = _build(live_12_nov())
    assert [row.revision_id for row in mapped.rows] == ["hash-1111", "hash-5555"]
    assert [row.revision for row in mapped.rows] == [1, 2]
    assert {d.record_id: d.code for d in mapped.diagnostics} == {
        "hash-ffff": DemandTargetDiagnosticCode.D1_BUILD_UP_STAGE,
        "hash-0000": DemandTargetDiagnosticCode.D1_BUILD_UP_STAGE,
        "hash-9999": DemandTargetDiagnosticCode.D1_UNCONFIRMED,
    }
    resolved = _resolve_targets(mapped.rows, ONE_DOWNLOAD)
    assert resolved[DAY].value == 239.595
    selected = [p for p in mapped.provenance_by_record_id.values() if p.selected]
    assert [p.value_text for p in selected] == ["239.595"]
    assert selected[0].revision_order_basis == "PROVIDER_PUBLICATION_ORDER_V1"


def test_legacy_receipt_policy_refused_the_live_shape():
    with pytest.raises(DemandTargetAmbiguityError):
        _build(live_12_nov(), revision_order_policy=RevisionOrderPolicy.DERIVED_RECEIPT_ORDER)


def test_fold_cutoff_before_the_receipt_sees_nothing():
    mapped = _build(live_12_nov())
    assert _resolve_targets(mapped.rows, ONE_DOWNLOAD - timedelta(seconds=1)) == {}


def test_equal_provider_clocks_for_distinct_confirmed_publications_are_refused():
    at = datetime(2026, 11, 13, 14, 20, 1)
    rows = [
        pub("x", "240.0", datetime(2026, 11, 13, 12, 20, 2)),
        pub("y", "239.9", at),
        pub("z", "239.8", at),
    ]
    with pytest.raises(DemandTargetAmbiguityError):
        _build(rows)

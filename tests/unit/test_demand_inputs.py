"""Cutoff, blank/zero, opt-in and ambiguity contracts for REST demand inputs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.application.research.demand_inputs import (
    AmbiguousDemandTargetError,
    DemandInputDiagnosticCode,
    project_rest_demand_targets,
)
from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord

CUTOFF = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)
RECEIVED = datetime(2026, 1, 3, 10, 0, tzinfo=UTC)
AVAILABLE = datetime(2026, 1, 3, 11, 0, tzinfo=UTC)
GAS_DAY = date(2026, 1, 2)
PROVIDER_CLOCK_MAX = "2026-01-02T05:30:00Z"


def _record(
    record_id: str,
    *,
    value_text: str = "42.5",
    value_is_blank: bool = False,
    quality_indicator: str | None = "A",
    is_provisional: bool = False,
    provisional_status: str = "FINAL",
    received: datetime = RECEIVED,
    available: datetime = AVAILABLE,
) -> NationalGasActualDemandRecord:
    """Build the real ORM row, including the REST provenance the projector reads."""

    return NationalGasActualDemandRecord(
        record_id=record_id,
        source_publication_id=f"{record_id}-publication",
        provider_item_id="PUBOB637",
        series_key="NG:PUBOB637:D+1",
        region="GB_NTS",
        term="D+1",
        label="NTS actual demand",
        gas_day=GAS_DAY,
        period_start_utc=datetime(2026, 1, 2, 5, 0, tzinfo=UTC),
        period_end_utc=datetime(2026, 1, 3, 5, 0, tzinfo=UTC),
        value_text=value_text,
        unit="mscm",
        received_at_utc=received,
        available_at_utc=available,
        ingested_at_utc=received,
        published_at_utc=available,
        applicable_at_raw="2026-01-02T05:00:00Z",
        generated_at_raw=PROVIDER_CLOCK_MAX,
        applicable_at_naive=datetime(2026, 1, 2, 5, 0),
        generated_at_naive=datetime(2026, 1, 2, 5, 30),
        quality_indicator=quality_indicator,
        provisional_status=provisional_status,
        is_provisional=is_provisional,
        raw_sha256="0" * 64,
        source_url="https://data.nationalgas.com/rest/actual-demand",
        hash_schema="national-gas-rest/v1",
        value_is_blank=value_is_blank,
        source_format="REST",
        rest_provenance={
            "received_at_utc": received.isoformat(),
            "available_at_utc": available.isoformat(),
            "provider_timestamp_upper_bound_utc": PROVIDER_CLOCK_MAX,
            "substituted_raw": "N",
        },
    )


def test_received_at_cutoff_with_availability_after_cutoff_is_excluded() -> None:
    row = _record(
        "received-at-cutoff",
        received=CUTOFF,
        available=CUTOFF + timedelta(hours=1),
    )

    bundle = project_rest_demand_targets([row], cutoff=CUTOFF, allow_provisional=True)

    assert bundle.targets == ()
    assert bundle.evidence == ()
    assert [diagnostic.code for diagnostic in bundle.diagnostics] == [
        DemandInputDiagnosticCode.RECEIVED_AFTER_CUTOFF
    ]
    assert bundle.diagnostics[0].record_id == "received-at-cutoff"


def test_availability_exactly_at_cutoff_is_accepted_and_preserved() -> None:
    row = _record("available-at-cutoff", received=RECEIVED, available=CUTOFF)

    bundle = project_rest_demand_targets([row], cutoff=CUTOFF, allow_provisional=True)

    assert bundle.diagnostics == ()
    assert len(bundle.targets) == 1
    assert bundle.targets[0].available_at == CUTOFF
    assert bundle.targets[0].value == 42.5
    assert bundle.evidence[0].received_at_utc == RECEIVED


def test_blank_is_not_admitted_as_zero_even_with_zero_opt_in() -> None:
    row = _record("blank", value_text="", value_is_blank=True)

    bundle = project_rest_demand_targets(
        [row],
        cutoff=CUTOFF,
        allow_unknown_quality=True,
        allow_provisional=True,
        allow_zero=True,
    )

    assert bundle.targets == ()
    assert bundle.evidence == ()
    assert [diagnostic.code for diagnostic in bundle.diagnostics] == [
        DemandInputDiagnosticCode.BLANK_VALUE
    ]


def test_explicit_zero_needs_the_zero_opt_in() -> None:
    row = _record("zero", value_text="0")

    refused = project_rest_demand_targets([row], cutoff=CUTOFF, allow_provisional=True)
    admitted = project_rest_demand_targets(
        [row], cutoff=CUTOFF, allow_provisional=True, allow_zero=True
    )

    assert refused.targets == ()
    assert [diagnostic.code for diagnostic in refused.diagnostics] == [
        DemandInputDiagnosticCode.ZERO_VALUE
    ]
    assert len(admitted.targets) == 1
    assert admitted.targets[0].value == 0.0
    assert admitted.evidence[0].value_text == "0"


def test_unknown_quality_and_provisional_need_separate_opt_ins() -> None:
    row = _record(
        "opt-ins",
        quality_indicator="U",
        is_provisional=True,
        provisional_status="PROVISIONAL",
    )

    unknown_quality = project_rest_demand_targets([row], cutoff=CUTOFF)
    provisional_only = project_rest_demand_targets(
        [row], cutoff=CUTOFF, allow_unknown_quality=True
    )
    admitted = project_rest_demand_targets(
        [row], cutoff=CUTOFF, allow_unknown_quality=True, allow_provisional=True
    )

    assert [diagnostic.code for diagnostic in unknown_quality.diagnostics] == [
        DemandInputDiagnosticCode.UNKNOWN_QUALITY
    ]
    assert [diagnostic.code for diagnostic in provisional_only.diagnostics] == [
        DemandInputDiagnosticCode.PROVISIONAL_NOT_ADMITTED
    ]
    assert len(admitted.targets) == 1
    assert admitted.evidence[0].quality_indicator_raw == "U"
    assert admitted.evidence[0].is_provisional is True


def test_equal_availability_conflicting_values_raise_typed_ambiguity() -> None:
    first = _record("conflict-a", value_text="10.0")
    second = _record("conflict-b", value_text="11.0")

    with pytest.raises(AmbiguousDemandTargetError) as exc_info:
        project_rest_demand_targets([first, second], cutoff=CUTOFF, allow_provisional=True)

    assert exc_info.value.code == "AMBIGUOUS_DEMAND_TARGET"

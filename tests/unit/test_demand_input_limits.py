"""Hard row limit, duplicate identity and mixed-provider contracts."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.application.research.demand_inputs import (
    AmbiguousDemandTargetError,
    DemandInputContractError,
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
    publication_id: str | None = None,
    provider_item_id: str = "PUBOB637",
    term: str = "D+1",
    value_text: str = "42.5",
    quality_indicator: str | None = "A",
    is_provisional: bool | None = False,
    provisional_status: str = "PROVISIONAL_INITIAL",
) -> NationalGasActualDemandRecord:
    """Build the real ORM row, including the REST provenance the projector reads."""

    return NationalGasActualDemandRecord(
        record_id=record_id,
        source_publication_id=(
            publication_id if publication_id is not None else f"{record_id}-publication"
        ),
        provider_item_id=provider_item_id,
        series_key=f"NG:{provider_item_id}:{term}",
        region="GB_NTS",
        term=term,
        label="NTS actual demand",
        gas_day=GAS_DAY,
        period_start_utc=datetime(2026, 1, 2, 5, 0, tzinfo=UTC),
        period_end_utc=datetime(2026, 1, 3, 5, 0, tzinfo=UTC),
        value_text=value_text,
        unit="mscm",
        received_at_utc=RECEIVED,
        available_at_utc=AVAILABLE,
        ingested_at_utc=RECEIVED,
        published_at_utc=AVAILABLE,
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
        value_is_blank=False,
        source_format="REST",
        rest_provenance={
            "received_at_utc": RECEIVED.isoformat(),
            "available_at_utc": AVAILABLE.isoformat(),
            "provider_timestamp_upper_bound_utc": PROVIDER_CLOCK_MAX,
            "substituted_raw": "N",
        },
    )


def _rows(count: int) -> Iterator[None]:
    for _ in range(count):
        yield None


def test_10001_rows_hit_the_hard_limit_even_when_every_row_is_a_diagnostic() -> None:
    tolerated = project_rest_demand_targets(_rows(10_000), cutoff=CUTOFF)

    assert tolerated.targets == ()
    assert len(tolerated.diagnostics) == 10_000

    with pytest.raises(DemandInputContractError) as exc_info:
        project_rest_demand_targets(_rows(10_001), cutoff=CUTOFF)

    assert exc_info.value.code == "DEMAND_INPUT_CONTRACT_ERROR"
    assert "input exceeds 10000 stored rows" in str(exc_info.value)


def test_conflicting_content_for_one_revision_identity_is_refused() -> None:
    first = _record("duplicate-identity", value_text="10.0")
    second = _record("duplicate-identity", value_text="11.0")

    assert (
        len(project_rest_demand_targets([first], cutoff=CUTOFF, allow_provisional=True).targets)
        == 1
    )
    assert (
        len(project_rest_demand_targets([second], cutoff=CUTOFF, allow_provisional=True).targets)
        == 1
    )

    with pytest.raises(AmbiguousDemandTargetError) as exc_info:
        project_rest_demand_targets([first, second], cutoff=CUTOFF, allow_provisional=True)

    assert exc_info.value.code == "AMBIGUOUS_DEMAND_TARGET"
    assert "one revision identity has conflicting content" in str(exc_info.value)


def test_valid_d1_and_d6_same_gas_day_are_refused_even_with_explicit_opt_ins() -> None:
    d1 = _record(
        "d1-row",
        provider_item_id="PUBOB637",
        term="D+1",
        quality_indicator="A",
        is_provisional=True,
        provisional_status="PROVISIONAL_INITIAL",
    )
    d6 = _record(
        "d6-row",
        provider_item_id="PUBOB652",
        term="D+6",
        quality_indicator="U",
        is_provisional=None,
        provisional_status="UNRESOLVED_D_PLUS_6",
    )

    assert (
        len(
            project_rest_demand_targets(
                [d1],
                cutoff=CUTOFF,
                allow_unknown_quality=True,
                allow_provisional=True,
            ).targets
        )
        == 1
    )
    assert (
        len(
            project_rest_demand_targets(
                [d6],
                cutoff=CUTOFF,
                allow_unknown_quality=True,
                allow_provisional=True,
            ).targets
        )
        == 1
    )

    with pytest.raises(DemandInputContractError) as exc_info:
        project_rest_demand_targets(
            [d1, d6],
            cutoff=CUTOFF,
            allow_unknown_quality=True,
            allow_provisional=True,
        )

    assert exc_info.value.code == "DEMAND_INPUT_CONTRACT_ERROR"
    assert "D+1 and D+6 cannot be mixed" in str(exc_info.value)

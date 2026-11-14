"""The GIE placeholder purge removes only valueless GIE rows without revision history."""

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    LngObservationRecord,
    ObservationRevisionRecord,
    StorageObservationRecord,
)
from scripts.ops.purge_gie_placeholder_rows import purge

DAY = datetime(2026, 11, 11, 5, tzinfo=UTC)


def _lng(observation_id, country, *, source="GIE", send_out=None):
    return LngObservationRecord(
        observation_id=observation_id,
        source_dataset="ALSI",
        terminal_id=country,
        terminal_name=country,
        country=country,
        send_out_twh_d=send_out,
        period_start_utc=DAY,
        period_end_utc=DAY,
        observed_at_utc=DAY,
        source_system=source,
        source_reference="ref",
        freshness="daily",
        research_only=False,
    )


def test_purge_counts_then_deletes_only_valueless_gie_rows_without_history() -> None:
    engine = create_engine("sqlite://")
    for model in (StorageObservationRecord, LngObservationRecord, ObservationRevisionRecord):
        model.__table__.create(engine)
    with Session(engine) as session:
        session.add_all(
            [
                _lng("dk-blank", "DK"),
                _lng("lu-blank", "LU"),
                _lng("nl-value", "NL", send_out=0.8),
                _lng("ng-blank", "GB", source="NATIONAL_GAS"),
                _lng("de-revised-blank", "DE"),
                ObservationRevisionRecord(
                    revision_id="r1",
                    observation_table="lng_observations",
                    observation_id="de-revised-blank",
                    source_system="GIE",
                    reason="value_changed",
                    changed_fields=["send_out_twh_d"],
                    prior_row_json={},
                    prior_received_at_utc=DAY,
                    superseded_at_utc=DAY,
                    prior_source_reference="a",
                    superseding_source_reference="b",
                    recorded_at_utc=DAY,
                ),
            ]
        )
        session.flush()

        dry = purge(session, commit=False)
        assert dry["lng_observations"] == {"DK": 1, "LU": 1}
        assert len(session.execute(select(LngObservationRecord)).all()) == 5

        purge(session, commit=True)
        kept = {row.observation_id for row in session.scalars(select(LngObservationRecord))}
        assert kept == {"nl-value", "ng-blank", "de-revised-blank"}

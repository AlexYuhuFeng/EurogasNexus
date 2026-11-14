"""ONT-01 worked example: one ENTSOG point traced from the provider to the API response.

docs/ontology/ONTOLOGY_AUTHORITY.md walks this path in prose; this test runs it. Each hop
asserts the identifier and the unit it carries:

provider record (ITP-00106, kWh/d, BE-TSO-0001)
  -> canonical id (ent:point:ITP-00106, through source_entity_mappings)
  -> stored observation (flow_observations: point_id ITP-00106, kWh/d as published)
  -> feature (flow.gwh_d.ITP-00106.entry, GWh/d, energy as published)
  -> dataset snapshot (entity ent:point:ITP-00106, content-addressed, ontology version)
  -> API response (/api/research/datasets: the same value, unit and snapshot id)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public.research_data import _fundamental_evidence
from eurogas_nexus.application.identity_resolution import (
    entsog_reference_identities,
    load_resolver,
    record_identities,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.db.repositories import research as repo
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.domain.ontology.quantity import convert
from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.ontology import ONTOLOGY_SCHEMA_VERSION
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import DatasetMode
from eurogas_nexus.ingestion.entsog_native_observations import (
    native_entsog_flow_observations_from_json,
)

POINT_KEY = "ITP-00106"  # Zeebrugge ZPT (Zeepipe), Fluxys Belgium: a Norwegian landing
OPERATOR_KEY = "BE-TSO-0001"
CANONICAL = "ent:point:ITP-00106"
SERIES = f"flow.gwh_d.{POINT_KEY}.entry"
KWH_D = "423450000"  # 423.45 GWh/d, as ENTSOG publishes it (kWh/d, a numeric string)
RECEIPT = datetime(2026, 11, 11, 9, 30, tzinfo=UTC)  # after the gas day closed

#: The provider's record, in the operationaldatas shape the live platform returns.
PROVIDER_PAYLOAD = {
    "operationaldatas": [
        {
            "id": "zpt-2026-11-10-entry",
            "indicator": "Physical Flow",
            "value": KWH_D,
            "unit": "kWh/d",
            "periodFrom": "2026-11-10T06:00:00+01:00",
            "periodTo": "2026-11-11T06:00:00+01:00",
            "pointKey": POINT_KEY,
            "pointLabel": "Zeebrugge ZPT",
            "operatorKey": OPERATOR_KEY,
            "directionKey": "entry",
            "periodType": "day",
        }
    ]
}
REFERENCE_NODE = {"source_system": "ENTSOG", "source_record_id": POINT_KEY,
                  "name": "Zeebrugge ZPT"}
REFERENCE_ACCESS = {"point_key": POINT_KEY, "point_name": "Zeebrugge ZPT",
                    "operator_key": OPERATOR_KEY, "operator_name": "Fluxys Belgium"}

FEATURE = FeatureDefinition(
    feature_id="ZPT_ENTRY_GWH_D",
    name="Zeebrugge ZPT entry",
    description="ENTSOG physical flow at ITP-00106, energy as published.",
    category="fundamental",
    input_dependencies=[SERIES],
    output_unit="GWh/d",
    frequency="1d",
    availability_class="DERIVED_AS_OF",
    transformation="identity",
    transformation_version="v1",
    missing_data_policy="mask",
)
TARGET = TargetDefinition(
    target_id="ZPT_ENTRY_NEXT_DAY",
    name="Zeebrugge ZPT entry, next day",
    description="Worked-example target.",
    target_type=TargetKind.PRICE,
    entity_type="point",
    entity_id=POINT_KEY,
    metric=SERIES,
    horizon="D1",
    target_window="1d",
    unit="GWh/d",
    aggregation="first",
    label_calculation="first_observation_at_or_after_origin_plus_horizon",
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'worked.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    for name in ("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    return engine


def test_itp_00106_from_provider_record_to_api_response(store) -> None:
    # 1. Provider identifier -> normalised row: the key and the unit as published.
    (row,) = native_entsog_flow_observations_from_json(PROVIDER_PAYLOAD, observed_at_utc=RECEIPT)
    assert row["point_id"] == POINT_KEY
    assert row["metadata_json"]["operatorKey"] == OPERATOR_KEY
    assert (row["original_value"], row["original_unit"]) == (423_450_000.0, "kWh/d")
    assert row["flow_mcm_d"] is None  # energy is never turned into a volume
    gas_day = row["period_start_utc"]
    assert gas_day == datetime(2026, 11, 10, 5, tzinfo=UTC)  # CET 06:00 is 05:00 UTC

    with Session(store) as session:
        # 2. Canonical id through the one resolver (ONT-02): the reference read's mapping.
        record_identities(session, entsog_reference_identities([REFERENCE_NODE],
                                                               [REFERENCE_ACCESS]))
        resolver = load_resolver(session)
        point = resolver.resolve("src-entsog", "entsog_point", row["point_id"])
        operator = resolver.resolve(
            "src-entsog", "entsog_operator", row["metadata_json"]["operatorKey"]
        )
        assert (point.canonical_entity_id, point.basis) == (CANONICAL, "mapping")
        assert operator.canonical_entity_id == f"ent:operator:{OPERATOR_KEY}"

        # 3. Stored observation: identity and unit unchanged in the store.
        session.add(FlowObservationRecord(**row))
        session.commit()
        stored = session.query(FlowObservationRecord).one()
        assert (stored.point_id, stored.original_unit) == (POINT_KEY, "kWh/d")
        assert stored.native_rate_json["unit_text"] == "kWh/d"

        # 4. Feature input: the dataset series, energy in GWh/d by the unit authority.
        definitions = {d.provider.casefold(): d for d in source_definitions()}
        records, sources = _fundamental_evidence(
            session, {SERIES}, definitions, history_start=gas_day - timedelta(days=1),
            end=gas_day + timedelta(days=3), requested_entity_ids={CANONICAL},
        )
        (evidence,) = records
        assert (evidence.series_id, evidence.entity_id, evidence.unit) == (
            SERIES, CANONICAL, "GWh/d"
        )
        assert evidence.value == pytest.approx(convert(423_450_000, "kWh", "GWh"))
        assert evidence.value == pytest.approx(423.45)
        assert sources == {"src-entsog"}

        # Register the feature, target and policy the API build resolves.
        repo.upsert_feature_definition(
            session, feature_id=FEATURE.feature_id,
            definition_json=FEATURE.model_dump(mode="json"), content_hash=FEATURE.content_hash(),
        )
        repo.upsert_target_definition(
            session, target_id=TARGET.target_id,
            definition_json=TARGET.model_dump(mode="json"), content_hash=TARGET.content_hash(),
        )
        repo.upsert_resampling_policy(
            session, policy_id="resampling/v1",
            definition_json=ResamplingPolicy(semantic_type="market_price").model_dump(
                mode="json"
            ),
            content_hash="0" * 64,
        )
        session.commit()

    # 5 and 6. Dataset snapshot built and served by the API, the same id, value and unit.
    spec = {
        "dataset_spec_id": "spec-ont01-zpt",
        "name": "ONT-01 worked example",
        "description": "ITP-00106 entry, one gas day.",
        "target_ids": [TARGET.target_id],
        "feature_ids": [FEATURE.feature_id],
        "entity_ids": [CANONICAL],
        "start": (RECEIPT + timedelta(hours=1)).isoformat(),
        "end": (RECEIPT + timedelta(hours=2)).isoformat(),
        "forecast_origin_frequency": "1h",
        "point_in_time_policy": {
            "policy_id": "pit-policy/v1",
            "cutoff_semantics": "available_at_lt_or_eq_cutoff",
            "allow_forecast_vintages": True,
            "allow_simulated": False,
            "mode": DatasetMode.EXPLORATORY.value,
        },
        "resampling_policy_id": "resampling/v1",
        "missing_data_policy": "mask",
        "minimum_coverage": 0.0,
        "ontology_version": ONTOLOGY_SCHEMA_VERSION,
    }
    response = TestClient(create_app()).post(
        "/api/research/datasets", json={"dataset_spec": spec, "materialize": True}
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    snapshot_id = body["dataset_snapshot_id"]
    assert body["ontology_version"] == ONTOLOGY_SCHEMA_VERSION
    (feature_row,) = [r for r in body["rows"] if r.get("feature_id") == FEATURE.feature_id]
    assert feature_row["value"] == pytest.approx(423.45)
    assert feature_row["unit"] == "GWh/d"
    assert feature_row["source_refs"] == ["entsog-operationaldatas"]

    detail = TestClient(create_app()).get(f"/api/research/datasets/{snapshot_id}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["dataset_snapshot_id"] == snapshot_id
    assert data["ontology_version"] == ONTOLOGY_SCHEMA_VERSION
    assert data["metadata"]["trusted_source_ids"] == ["src-entsog"]
    assert [a["source_id"] for a in data["source_attributions"]] == ["src-entsog"]

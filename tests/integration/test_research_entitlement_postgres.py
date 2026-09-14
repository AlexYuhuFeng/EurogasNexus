"""Live-PostgreSQL source-entitlement checks for the CR-14 research data surface.

Register item CR14-RIGHTS-001 closes its "live PostgreSQL / identity-negative"
gap here. ``tests/api/test_research_data_api.py`` proves the entitlement rules
against SQLite fixtures; this module proves the same rules against the real
runtime store by driving the real repository, builder and route code inside an
isolated PostgreSQL schema:

1. snapshot list/detail/quality reads are filtered by the principal's source
   grants, including the identity-negative case and the legacy wildcard grant;
2. export fails closed for unknown/untrusted provenance and for a forged
   ``EXPORT_ALLOWED`` envelope, because policy is derived server-side from
   canonical provenance;
3. the format-specific artifact read path resolves registrations against real
   ``dataset_artifacts`` rows, and "no artifact of this format" is
   distinguishable from "no artifact at all";
4. source filtering excludes denied and unregistered rows inside the builder
   itself, not only at the API boundary.

Isolation contract: every test owns a fresh ``ent_<uuid4().hex>`` schema, points
a dedicated engine at it through a ``SET search_path`` connect hook, and drops
the schema in fixture teardown -- including when the test fails. The ``public``
schema is only ever read.

The whole module skips when ``RUNTIME_STORE_DATABASE_URL`` is unset, so the CI
validate job can run the suite without a database.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, func, select, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import research_data
from eurogas_nexus.application import research_artifacts
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    DatasetArtifactRecord,
    DatasetSnapshotRecord,
    MarketObservationRecord,
)
from eurogas_nexus.db.repositories import research as repo
from eurogas_nexus.domain.research.datasets import DatasetPointInTimePolicy, DatasetSpec
from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import DatasetMode, TemporalIntegrityState
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    legacy_public_token_principal,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL"),
    reason="RUNTIME_STORE_DATABASE_URL not configured; use the PostgreSQL test DB",
)

# Source families used below, resolved through the canonical dataops registry:
#   src-entsog -> provider "ENTSOG" (public baseline: every principal may read)
#   src-eex    -> provider "EEX"    (commercial: needs an EEX or "*" grant)
#   src-ice-ocm-> provider "ICE_OCM"(commercial: needs an ICE_OCM or "*" grant)
SOURCES = {"entsog": "src-entsog", "eex": "src-eex", "ice_ocm": "src-ice-ocm"}


# ---------------------------------------------------------------------------
# Isolated schema fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_engine() -> Iterator[Engine]:
    """One live PostgreSQL schema per test, dropped even when the test fails."""

    url = os.environ["RUNTIME_STORE_DATABASE_URL"]
    schema = f"ent_{uuid4().hex}"
    admin = create_engine(url, future=True)
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _pin_search_path(dbapi_connection, _record) -> None:
        # Every pooled connection of this engine is confined to the test schema;
        # "public" is deliberately absent from the path, so a test can never
        # write into the seeded development data.
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()
        # pg8000 begins a transaction implicitly, so the SET must be committed
        # here: PostgreSQL reverts a transactional SET when that transaction is
        # rolled back, which would silently send a reused pooled connection back
        # to the public schema on the next Session.
        dbapi_connection.commit()

    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
            Base.metadata.create_all(connection)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture()
def route_engine(
    monkeypatch: pytest.MonkeyPatch, isolated_engine: Engine
) -> Engine:
    """Run the real research routes against the isolated schema."""

    monkeypatch.setattr(research_data, "_session", lambda: Session(bind=isolated_engine))
    return isolated_engine


# ---------------------------------------------------------------------------
# Identity, request and seeding helpers
# ---------------------------------------------------------------------------


def _principal(name: str, *scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=f"pg-entitlement-{name}",
        name=f"pg-entitlement-{name}",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("ANALYST",),
        auth_method="identity_key",
    )


def _request(principal: AuthenticatedPrincipal) -> Request:
    """A real Starlette request carrying an authenticated principal in state."""

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/research/datasets",
            "headers": [],
            "state": {"identity": principal},
        }
    )


def _outcome(call: Callable[..., object], *args: object, **kwargs: object) -> object:
    """Return the route/builder result, or the HTTPException it raised."""

    try:
        return call(*args, **kwargs)
    except HTTPException as exc:
        return exc


def _denied(outcome: object, code: str) -> dict:
    """Assert a fail-closed 403 with a structured code and return its detail."""

    assert isinstance(outcome, HTTPException), f"expected an entitlement denial, got {outcome!r}"
    assert outcome.status_code == 403, outcome.detail
    detail = outcome.detail
    assert isinstance(detail, dict), detail
    assert detail.get("code") == code, detail
    return detail


def _payload(outcome: object) -> dict:
    assert isinstance(outcome, dict), f"expected a route payload, got {outcome!r}"
    data = outcome["data"]
    assert isinstance(data, dict), data
    return data


def _conflict(outcome: object, reason: str) -> dict:
    """Assert the artifact branch failed closed with the given reason."""

    assert isinstance(outcome, HTTPException), f"expected an artifact conflict, got {outcome!r}"
    assert outcome.status_code == 409, outcome.detail
    detail = outcome.detail
    assert isinstance(detail, dict), detail
    assert detail.get("code") == "artifact_not_available", detail
    assert detail.get("reason") == reason, detail
    assert "artifact_ref" not in detail, detail
    return detail


def _snapshot(
    snapshot_id: str,
    *,
    trusted_source_ids: list[str] | None,
    created_at_utc: datetime,
) -> DatasetSnapshotRecord:
    """One persisted snapshot row with canonical-provenance metadata.

    ``entitlement_envelope`` is deliberately stored as ``EXPORT_ALLOWED``. A
    client can supply that envelope through the dataset spec, so it is metadata
    and never the export authority: the route has to re-derive policy from the
    persisted ``trusted_source_ids`` provenance.
    """

    metadata: dict[str, object] = {
        "quality_report": {"coverage": 1.0, "temporal_integrity": "TEMPORAL_VERIFIED"},
        "warnings": [],
        "leakage_issues": [],
        "lineage": [f"test:{snapshot_id}"],
    }
    if trusted_source_ids is not None:
        metadata["trusted_source_ids"] = list(trusted_source_ids)
    return DatasetSnapshotRecord(
        dataset_snapshot_id=snapshot_id,
        dataset_spec_id="spec-entitlement",
        spec_hash="a" * 64,
        ontology_version="energy-ontology/v1",
        source_cutoff_utc=created_at_utc,
        row_count=1,
        column_count=1,
        coverage=1.0,
        temporal_integrity="TEMPORAL_VERIFIED",
        content_hash="b" * 64,
        entitlement_envelope={"export_policy": "EXPORT_ALLOWED", "policy_source": "request"},
        metadata_json=metadata,
        artifact_ref=None,
        created_at_utc=created_at_utc,
        created_by="test",
        status="COMPLETE",
    )


def _artifact(
    artifact_id: str,
    snapshot_id: str,
    artifact_format: str,
    artifact_path: str,
    sha256: str,
) -> DatasetArtifactRecord:
    return DatasetArtifactRecord(
        artifact_id=artifact_id,
        dataset_snapshot_id=snapshot_id,
        format=artifact_format,
        artifact_path=artifact_path,
        sha256=sha256,
        created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _dataset_spec(**overrides: object) -> DatasetSpec:
    payload: dict[str, object] = {
        "dataset_spec_id": "spec-pg-entitlement",
        "name": "PostgreSQL entitlement dataset",
        "description": "Live-PostgreSQL point-in-time dataset.",
        "target_ids": ["NBP_DA_PRICE_D1"],
        "feature_ids": ["NBP_TTF_DA_SPREAD"],
        "entity_ids": ["ent:market_hub:NBP", "ent:market_hub:TTF"],
        "start": datetime(2026, 1, 1, tzinfo=UTC),
        "end": datetime(2026, 1, 1, 3, tzinfo=UTC),
        "forecast_origin_frequency": "1h",
        "point_in_time_policy": DatasetPointInTimePolicy(
            mode=DatasetMode.STRICT, allow_simulated=False
        ),
        "resampling_policy_id": "resampling/v1",
        "missing_data_policy": "mask",
        "minimum_coverage": 0.0,
        "ontology_version": "energy-ontology/v1",
    }
    payload.update(overrides)
    return DatasetSpec.model_validate(payload)


def _seed_registry(session: Session) -> None:
    """Seed the canonical registry rows a dataset build resolves against."""

    feature = FeatureDefinition(
        feature_id="NBP_TTF_DA_SPREAD",
        name="NBP-TTF day-ahead spread",
        description="PostgreSQL entitlement fixture feature.",
        category="market",
        input_dependencies=[
            "market.price.NBP.DAY_AHEAD",
            "market.price.TTF.DAY_AHEAD",
        ],
        output_unit="GBP/MWh",
        frequency="1h",
        availability_class="DERIVED_AS_OF",
        transformation="builtin:NBP_TTF_DA_SPREAD",
        transformation_version="v1",
        missing_data_policy="mask",
    )
    target = TargetDefinition(
        target_id="NBP_DA_PRICE_D1",
        name="NBP day-ahead price",
        description="PostgreSQL entitlement fixture target.",
        target_type=TargetKind.PRICE,
        entity_type="market_hub",
        entity_id="NBP",
        metric="NBP_DA_PRICE_D1",
        horizon="H1",
        target_window="1h",
        unit="GBP/MWh",
        aggregation="first",
        label_calculation="first_observation_at_or_after_origin_plus_horizon",
    )
    repo.upsert_feature_definition(
        session,
        feature_id=feature.feature_id,
        definition_json=feature.model_dump(mode="json"),
        content_hash=feature.content_hash(),
    )
    repo.upsert_target_definition(
        session,
        target_id=target.target_id,
        definition_json=target.model_dump(mode="json"),
        content_hash=target.content_hash(),
    )
    for code in ("NBP", "TTF"):
        repo.upsert_canonical_entity(
            session,
            canonical_entity_id=f"ent:market_hub:{code}",
            entity_type="market_hub",
            canonical_code=code,
            display_name=f"{code} Virtual Trading Point",
        )
    repo.upsert_resampling_policy(
        session,
        policy_id="resampling/v1",
        definition_json=ResamplingPolicy(semantic_type="market_price").model_dump(mode="json"),
        content_hash="0" * 64,
    )


def _seed_market_rows(
    session: Session,
    source_system: str,
    *,
    nbp_price: float,
    ttf_price: float,
) -> None:
    """Three hourly NBP/TTF rows (plus verified temporal metadata) per source."""

    tag = source_system.casefold().replace("_", "-")
    for hour in range(3):
        observed_at = datetime(2026, 1, 1, hour, tzinfo=UTC)
        for hub, price in (("NBP", nbp_price), ("TTF", ttf_price)):
            observation_id = f"pg-{tag}-{hub}-{hour}"
            session.add(
                MarketObservationRecord(
                    observation_id=observation_id,
                    market_venue=hub,
                    product="DAY_AHEAD",
                    price=price + hour,
                    unit="GBP/MWh",
                    currency="GBP" if hub == "NBP" else "EUR",
                    period_start_utc=observed_at,
                    period_end_utc=observed_at + timedelta(hours=1),
                    observed_at_utc=observed_at,
                    source_system=source_system,
                    source_reference=f"test:{tag}:{hub}:{hour}",
                    source_record_id=observation_id,
                    freshness="OBSERVED",
                    quality_score=1.0,
                    research_only=True,
                    metadata_json={"hub": hub, "tenor": "DAY_AHEAD"},
                )
            )
            repo.upsert_observation_temporal_metadata(
                session,
                observation_id=observation_id,
                observation_table="market_observations",
                observed_at_utc=observed_at,
                available_at_utc=observed_at,
                ingested_at_utc=observed_at,
                temporal_integrity=TemporalIntegrityState.TEMPORAL_VERIFIED.value,
            )


def _artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the artifact store at the test sandbox (nothing in the checkout)."""

    root = tmp_path / "research-artifacts"
    monkeypatch.setenv("EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(root))
    return root


# ---------------------------------------------------------------------------
# 1. Snapshot list / detail / quality reads follow the principal's grants
# ---------------------------------------------------------------------------


def test_snapshot_reads_are_filtered_by_source_grants(route_engine: Engine) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(route_engine) as session:
        session.add_all(
            [
                _snapshot(
                    "snap-entsog", trusted_source_ids=[SOURCES["entsog"]], created_at_utc=now
                ),
                _snapshot("snap-eex", trusted_source_ids=[SOURCES["eex"]], created_at_utc=now),
                _snapshot("snap-ice", trusted_source_ids=[SOURCES["ice_ocm"]], created_at_utc=now),
                _snapshot(
                    "snap-mixed",
                    trusted_source_ids=[SOURCES["entsog"], SOURCES["eex"]],
                    created_at_utc=now,
                ),
                _snapshot(
                    "snap-unknown",
                    trusted_source_ids=["src-not-registered"],
                    created_at_utc=now,
                ),
                # Legacy provenance: no trusted source ids persisted at all.
                _snapshot("snap-legacy", trusted_source_ids=None, created_at_utc=now),
            ]
        )
        session.commit()
        # The denied snapshots are real persisted rows, never missing ones.
        assert session.get(DatasetSnapshotRecord, "snap-eex") is not None
        assert session.get(DatasetSnapshotRecord, "snap-ice") is not None

    def listed(principal: AuthenticatedPrincipal) -> set[str]:
        body = _outcome(research_data.list_datasets, _request(principal))
        assert isinstance(body, dict), body
        return {row["dataset_snapshot_id"] for row in body["data"]}

    entsog_only = _principal("entsog", "ENTSOG")
    eex_only = _principal("eex", "EEX")
    icis_only = _principal("icis", "ICIS")
    legacy = legacy_public_token_principal()
    assert legacy.data_scopes == ("*",)

    # A principal granted only ENTSOG sees the public-baseline snapshot and
    # none of the commercial ones, even though every row really exists.
    assert listed(entsog_only) == {"snap-entsog"}
    # Commercial grants are additive to the public baseline, and never leak
    # a different commercial family.
    assert listed(eex_only) == {"snap-entsog", "snap-eex", "snap-mixed"}
    assert listed(icis_only) == {"snap-entsog"}
    # The legacy wildcard grant reads every trusted commercial snapshot but
    # still fails closed on unknown and legacy provenance.
    assert listed(legacy) == {"snap-entsog", "snap-eex", "snap-ice", "snap-mixed"}

    # Identity-negative: a scoped identity asking for a snapshot it cannot read
    # gets an entitlement 403 on a real row, never a 404.
    for snapshot_id in ("snap-eex", "snap-mixed"):
        request = _request(entsog_only)
        _denied(
            _outcome(research_data.get_dataset, snapshot_id, request),
            "source_entitlement_denied",
        )
        _denied(
            _outcome(research_data.get_dataset_quality, snapshot_id, request),
            "source_entitlement_denied",
        )

    # Unknown and legacy provenance fail closed for the wildcard grant too.
    for snapshot_id in ("snap-unknown", "snap-legacy"):
        request = _request(legacy)
        _denied(
            _outcome(research_data.get_dataset, snapshot_id, request),
            "source_entitlement_denied",
        )
        _denied(
            _outcome(research_data.get_dataset_quality, snapshot_id, request),
            "source_entitlement_denied",
        )

    # The granted read succeeds and reports the stored envelope verbatim
    # (it is metadata, not authority -- see the export test).
    granted = _payload(_outcome(research_data.get_dataset, "snap-eex", _request(eex_only)))
    assert granted["dataset_snapshot_id"] == "snap-eex"
    assert granted["entitlement_envelope"] == {
        "export_policy": "EXPORT_ALLOWED",
        "policy_source": "request",
    }
    quality = _payload(_outcome(research_data.get_dataset_quality, "snap-eex", _request(eex_only)))
    assert quality["quality_report"]["temporal_integrity"] == "TEMPORAL_VERIFIED"
    # An unknown snapshot id is still a 404 for a granted principal.
    absent = _outcome(research_data.get_dataset, "snap-does-not-exist", _request(eex_only))
    assert isinstance(absent, HTTPException)
    assert absent.status_code == 404


# ---------------------------------------------------------------------------
# 2. Export fails closed on provenance, never on request metadata
# ---------------------------------------------------------------------------


def test_export_denial_ignores_forged_export_allowed_envelopes(
    route_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(route_engine) as session:
        session.add_all(
            [
                _snapshot("snap-eex", trusted_source_ids=[SOURCES["eex"]], created_at_utc=now),
                _snapshot(
                    "snap-unknown", trusted_source_ids=["src-not-registered"], created_at_utc=now
                ),
                _snapshot("snap-legacy", trusted_source_ids=None, created_at_utc=now),
            ]
        )
        session.commit()

    legacy = legacy_public_token_principal()
    legacy_request = _request(legacy)
    for snapshot_id, code in (
        ("snap-unknown", "source_entitlement_denied"),
        ("snap-legacy", "source_entitlement_denied"),
        ("snap-eex", "export_denied_entitlement"),
    ):
        detail = _denied(
            _outcome(
                research_data.export_dataset,
                snapshot_id,
                research_data.DatasetExportRequest(format="csv"),
                legacy_request,
            ),
            code,
        )
        if code == "export_denied_entitlement":
            # Derived from the EEX source definition, not from the stored
            # EXPORT_ALLOWED envelope.
            assert detail["policy"] == "EXPORT_RESTRICTED"

    # Same decision through HTTP, with a forged envelope in the request body.
    client = TestClient(create_app())
    forged = {"format": "csv", "entitlement_envelope": {"export_policy": "EXPORT_ALLOWED"}}
    for snapshot_id, code in (
        ("snap-unknown", "source_entitlement_denied"),
        ("snap-legacy", "source_entitlement_denied"),
        ("snap-eex", "export_denied_entitlement"),
    ):
        response = client.post(f"/api/research/datasets/{snapshot_id}/export", json=forged)
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["code"] == code, response.text

    with Session(route_engine) as session:
        stored = repo.get_dataset_snapshot(session, "snap-eex")
        assert stored is not None
        assert stored.entitlement_envelope["export_policy"] == "EXPORT_ALLOWED"


# ---------------------------------------------------------------------------
# 3. Artifact read path resolves format registrations against real rows
# ---------------------------------------------------------------------------


def test_artifact_read_path_is_format_specific(
    route_engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _artifact_root(tmp_path, monkeypatch)
    (root / "snap-artifacts").mkdir(parents=True)
    written = root / "snap-artifacts" / "dataset.csv"
    written.write_text("record_id,value\npg-1,1.0\n", encoding="utf-8")
    csv_sha = hashlib.sha256(written.read_bytes()).hexdigest()

    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(route_engine) as session:
        session.add_all(
            [
                _snapshot(
                    "snap-artifacts", trusted_source_ids=[SOURCES["entsog"]], created_at_utc=now
                ),
                _snapshot(
                    "snap-csv-only", trusted_source_ids=[SOURCES["entsog"]], created_at_utc=now
                ),
                _snapshot(
                    "snap-no-artifacts", trusted_source_ids=[SOURCES["entsog"]], created_at_utc=now
                ),
            ]
        )
        # An explicit flush keeps the seeded order FK-safe: the unit of work
        # orders mappers by relationship, not by a bare foreign key, which is
        # exactly why ``persist_dataset_snapshot`` flushes its snapshot first.
        session.flush()
        session.add_all(
            [
                _artifact(
                    "artifact:snap-artifacts:csv",
                    "snap-artifacts",
                    "csv",
                    "snap-artifacts/dataset.csv",
                    csv_sha,
                ),
                _artifact(
                    "artifact:snap-artifacts:parquet",
                    "snap-artifacts",
                    "parquet",
                    "snap-artifacts/dataset.parquet",
                    "c" * 64,
                ),
                _artifact(
                    "artifact:snap-csv-only:csv",
                    "snap-csv-only",
                    "csv",
                    "snap-csv-only/dataset.csv",
                    "d" * 64,
                ),
            ]
        )
        session.commit()

        # Repository read path, ordered deterministically by format.
        assert [
            item.format for item in repo.list_dataset_artifacts(session, "snap-artifacts")
        ] == ["csv", "parquet"]
        csv_row = repo.get_dataset_artifact(session, "snap-artifacts", "csv")
        assert csv_row is not None and csv_row.artifact_id == "artifact:snap-artifacts:csv"
        parquet_row = repo.get_dataset_artifact(session, "snap-artifacts", "parquet")
        assert parquet_row is not None
        assert parquet_row.artifact_path == "snap-artifacts/dataset.parquet"
        # A registered format is distinguishable from an unregistered one...
        assert [
            item.format for item in repo.list_dataset_artifacts(session, "snap-csv-only")
        ] == ["csv"]
        assert repo.get_dataset_artifact(session, "snap-csv-only", "parquet") is None
        # ...and both are distinguishable from a snapshot with no artifact at all.
        assert repo.list_dataset_artifacts(session, "snap-no-artifacts") == []
        assert repo.get_dataset_artifact(session, "snap-no-artifacts", "csv") is None
        assert repo.list_dataset_artifacts(session, "snap-does-not-exist") == []
        assert repo.get_dataset_artifact(session, "snap-does-not-exist", "csv") is None

    request = _request(legacy_public_token_principal())
    export = research_data.export_dataset
    body = research_data.DatasetExportRequest

    # Canonical policy decides first: ENTSOG provenance is EXPORT_RESTRICTED, so
    # the stored-artifact branch below is only reachable through a test-only
    # envelope. EXPORT_ALLOWED is unreachable from canonical governance because
    # no registered source family maps to the PUBLIC scope.
    denial = _denied(
        _outcome(export, "snap-artifacts", body(format="csv"), request),
        "export_denied_entitlement",
    )
    assert denial["policy"] == "EXPORT_RESTRICTED"

    monkeypatch.setattr(
        research_data,
        "effective_entitlement_envelope",
        lambda _definitions: {"export_policy": "EXPORT_ALLOWED", "policy_source": "test"},
    )

    served = _payload(_outcome(export, "snap-artifacts", body(format="csv"), request))
    assert served["format"] == "csv"
    assert served["artifact_ref"] == "snap-artifacts/dataset.csv"
    assert served["artifact_id"] == "artifact:snap-artifacts:csv"
    assert served["artifact_sha256"] == csv_sha
    assert served["available_formats"] == ["csv", "parquet"]
    assert served["entitlement_policy"] == "EXPORT_ALLOWED"
    assert str(tmp_path) not in served["artifact_ref"]

    # Registered format, file gone: FILE_MISSING proves the row was resolved.
    missing = _conflict(
        _outcome(export, "snap-artifacts", body(format="parquet"), request), "FILE_MISSING"
    )
    assert missing["available_formats"] == ["csv", "parquet"]
    # Format never registered for this snapshot: FORMAT_NOT_REGISTERED.
    unregistered = _conflict(
        _outcome(export, "snap-csv-only", body(format="parquet"), request),
        "FORMAT_NOT_REGISTERED",
    )
    assert unregistered["available_formats"] == ["csv"]
    # No artifact at all: same reason code, empty inventory -- distinguishable.
    empty = _conflict(
        _outcome(export, "snap-no-artifacts", body(format="csv"), request),
        "FORMAT_NOT_REGISTERED",
    )
    assert empty["available_formats"] == []


# ---------------------------------------------------------------------------
# 4. Row-level source filtering inside the builder that feeds the snapshots
# ---------------------------------------------------------------------------


def test_builder_row_filtering_excludes_denied_and_unregistered_rows(
    route_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _artifact_root(tmp_path, monkeypatch)
    spec = _dataset_spec()
    entsog_only = _principal("entsog", "ENTSOG")
    legacy = legacy_public_token_principal()

    with Session(route_engine) as session:
        _seed_registry(session)
        # Same shape, different provenance: ENTSOG (public baseline),
        # ICE_OCM (commercial, not granted to the scoped principal) and
        # operator-input (manual rows, not a registered source provider).
        for source_system, nbp_price, ttf_price in (
            ("ENTSOG", 20.0, 18.0),
            ("ICE_OCM", 100.0, 96.0),
            ("operator-input", 70.0, 62.0),
        ):
            _seed_market_rows(
                session, source_system, nbp_price=nbp_price, ttf_price=ttf_price
            )
        session.commit()

        stored = dict(
            session.execute(
                select(MarketObservationRecord.source_system, func.count()).group_by(
                    MarketObservationRecord.source_system
                )
            ).all()
        )
        assert stored == {"ENTSOG": 6, "ICE_OCM": 6, "operator-input": 6}

        # ENTSOG-scoped principal: only the six granted rows reach the builder.
        result, _dependencies, _issues = research_data._build_from_runtime(
            session, spec, principal=entsog_only
        )
        assert result.trusted_source_ids == ["src-entsog"]
        assert set(result.lineage) == {
            f"test:entsog:{hub}:{hour}" for hub in ("NBP", "TTF") for hour in range(3)
        }
        assert result.quality_report["source_count"] == 6
        assert {row["value"] for row in result.rows if row.get("feature_id")} == {2.0}
        assert {
            row["target_value"]
            for row in result.rows
            if row.get("target_id") and row["target_value"] is not None
        } == {21.0, 22.0}
        assert all(
            ref.startswith("test:entsog:")
            for row in result.rows
            for ref in row.get("source_refs", [])
        )
        assert result.as_metadata()["entitlement_envelope"]["export_policy"] == "EXPORT_RESTRICTED"
        assert result.dataset_snapshot_id.startswith("dataset-snapshot-")

        # The same build is deterministic (content-addressed snapshot id).
        repeat, _d, _i = research_data._build_from_runtime(session, spec, principal=entsog_only)
        assert repeat.dataset_snapshot_id == result.dataset_snapshot_id
        assert repeat.content_hash == result.content_hash

        # Wildcard grant adds the commercial rows; the manual rows still cannot
        # enter, because "operator-input" is not a registered source provider.
        wide, _d, _i = research_data._build_from_runtime(session, spec, principal=legacy)
        assert wide.trusted_source_ids == ["src-entsog", "src-ice-ocm"]
        assert any(ref.startswith("test:ice-ocm:") for ref in wide.lineage)
        assert not any(ref.startswith("test:operator-input:") for ref in wide.lineage)

        # The row-level restriction selects the other real rows: the built
        # values switch, which is only possible if filtering happens pre-build.
        restricted = _dataset_spec(source_restrictions=["ICE_OCM"])
        ice, _d, _i = research_data._build_from_runtime(session, restricted, principal=legacy)
        assert ice.trusted_source_ids == ["src-ice-ocm"]
        assert set(ice.lineage) == {
            f"test:ice-ocm:{hub}:{hour}" for hub in ("NBP", "TTF") for hour in range(3)
        }
        assert {row["value"] for row in ice.rows if row.get("feature_id")} == {4.0}
        assert {
            row["target_value"]
            for row in ice.rows
            if row.get("target_id") and row["target_value"] is not None
        } == {101.0, 102.0}

        # A restriction naming a registered source the principal is not granted
        # is an entitlement denial, not a silent empty build.
        for restriction in ("ICE_OCM", "EEX"):
            denied_spec = _dataset_spec(source_restrictions=[restriction])
            _denied(
                _outcome(
                    research_data._build_from_runtime,
                    session,
                    denied_spec,
                    principal=entsog_only,
                ),
                "source_entitlement_denied",
            )

        # Nothing was deleted or rewritten by any of the builds.
        after = dict(
            session.execute(
                select(MarketObservationRecord.source_system, func.count()).group_by(
                    MarketObservationRecord.source_system
                )
            ).all()
        )
        assert after == stored

        # Persist the ICE_OCM build: the real built snapshot is readable by the
        # wildcard grant and denied to the ENTSOG-scoped identity, and its export
        # is refused from canonical provenance (not from the stored envelope).
        persisted = repo.persist_dataset_snapshot(
            session,
            metadata=ice.as_metadata(),
            dependencies=[],
            issues=[],
            artifacts=research_artifacts.write_dataset_artifacts(ice),
        )
        session.commit()
        built_snapshot_id = persisted.dataset_snapshot_id
        assert persisted.artifact_ref is not None
        assert repo.get_dataset_artifact(session, built_snapshot_id, "csv") is not None

    _denied(
        _outcome(
            research_data.get_dataset, built_snapshot_id, _request(_principal("icis", "ICIS"))
        ),
        "source_entitlement_denied",
    )
    read = _payload(
        _outcome(research_data.get_dataset, built_snapshot_id, _request(legacy))
    )
    assert read["metadata"]["trusted_source_ids"] == ["src-ice-ocm"]
    _denied(
        _outcome(
            research_data.export_dataset,
            built_snapshot_id,
            research_data.DatasetExportRequest(format="csv"),
            _request(legacy),
        ),
        "export_denied_entitlement",
    )

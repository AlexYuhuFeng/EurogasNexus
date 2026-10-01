"""Governed upstream-contract writes capture both sides of an overwrite.

`docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md` section 10: the
existing ``POST /api/route-cost/upstream-contracts`` route now resolves the
authenticated actor, captures the stored economic state as an immutable
revision before overwriting it, captures the new state afterwards, and writes
the mutation audit in the same transaction. These tests run the real route
against a throw-away SQLite runtime store and assert:

* creation captures once and audits the created mutation;
* an identical replay writes nothing, adds no revision and no audit row, and
  preserves the original recorder and timestamp;
* an economic change captures the previous and the new state, allocating the
  next revision number, and the earlier snapshot is unchanged afterwards;
* a metadata-only change (display name, raw operator notes) is audited even
  though the economics capture is idempotent;
* a stored row whose terms cannot be captured refuses the overwrite with a
  stable structured code and keeps the malformed terms;
* an audit-writer failure rolls the whole write back - row, revision and audit
  commit or roll back together.

PostgreSQL-authoritative locking and create-concurrency semantics live in
``tests/integration/test_contract_revision_capture_postgres.py`` behind the
existing disposable-database opt-in.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories import route_cost as route_cost_repository
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.db.repositories.route_cost import (
    list_upstream_contract_revisions,
    upsert_upstream_contract,
)

PUBLIC_TOKEN = "test-public-api-token"
CONTRACT_PATH = "/api/route-cost/upstream-contracts"
CONTRACT_ID = "governed-write-ttf-supply-2025"
UNAUTHORISED_CONTRACT_ID = "legacy-malformed-supply"


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_id": CONTRACT_ID,
        "contract_name": "Governed TTF supply 2025",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 125.5,
        "contract_price_gbp_mwh": 29.75,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2,
        "nomination_tolerance_pct": 1,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
        "annual_financing_rate_pct": 6,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["NBP", "TTF"],
        "eligible_sale_modes": ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
        "variable_cost_gbp_mwh": 0.75,
        "regas_fee_gbp_mwh": 1.25,
        "fuel_loss_allowance_pct": 1.5,
        "notes": "operator draft decision support",
    }
    payload.update(overrides)
    return payload


def _prepare_db(tmp_path, monkeypatch) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'governed-write.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _deployment_client() -> TestClient:
    """The development-profile SDK/CLI caller: the deployment's own principal."""

    return TestClient(create_app())


def _analyst_client(url: str) -> tuple[TestClient, str]:
    """A release-profile client acting as a distinct authenticated analyst."""

    with Session(create_engine(url, future=True)) as session:
        principal = create_identity_principal(
            session,
            name="revision-trader",
            display_name="Revision Trader",
            role="ANALYST",
            data_scopes=["TTF"],
        )
        _key, bearer = create_identity_api_key(
            session, principal.principal_id, display_name="governed-write"
        )
        session.commit()
        principal_id = principal.principal_id
    client = TestClient(create_app(Settings(api_profile="release")))
    client.headers.update(
        {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
    )
    return client, principal_id


def _session(url: str) -> Session:
    return Session(create_engine(url, future=True))


def _audit_rows(url: str, action: str | None = None) -> list[AuditEventRecord]:
    with _session(url) as session:
        query = session.query(AuditEventRecord)
        if action:
            query = query.filter(AuditEventRecord.action == action)
        return query.order_by(AuditEventRecord.event_ts_utc).all()


def _instant(value: str) -> datetime:
    """Parse a response timestamp: SQLite fixtures drop the UTC offset, PG keeps it."""

    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _assert_same_revision_identity(
    latest: dict[str, object], expected: dict[str, object]
) -> None:
    """The captured revision named by a response must be the same evidence row."""

    for field in (
        "contract_revision_id",
        "contract_id",
        "revision_number",
        "capture_origin",
        "content_hash",
        "recorded_by",
    ):
        assert latest[field] == expected[field], field
    assert _instant(str(latest["recorded_at_utc"])) == _instant(
        str(expected["recorded_at_utc"])
    )


def test_create_captures_one_revision_and_audits_the_created_mutation(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)

    response = _deployment_client().post(CONTRACT_PATH, json=_body())

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["contract_id"] == CONTRACT_ID
    # The legacy response fields are unchanged.
    assert data["delivery_quantity_mwh_per_day"] == 125.5
    assert data["variable_cost_gbp_mwh"] == 0.75
    assert data["regas_fee_gbp_mwh"] == 1.25
    assert data["fuel_loss_allowance_pct"] == 1.5
    assert data["human_review_required"] is True
    # Additive revision identity: the new row and its first captured revision.
    assert data["write_outcome"] == "created"
    assert data["latest_revision"]["revision_number"] == 1
    assert data["latest_revision"]["capture_origin"] == "legacy_capture"
    assert data["latest_revision"]["content_hash"].startswith("sha256:")
    assert data["latest_revision"]["recorded_by"] == "service:public-api"

    with _session(url) as session:
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        assert row is not None
        stored_notes = json.loads(row.notes)
        assert stored_notes["operator_notes"] == "operator draft decision support"
        assert stored_notes["variable_cost_gbp_mwh"] == 0.75

        revisions = list_upstream_contract_revisions(session, CONTRACT_ID)
        assert [item["revision_number"] for item in revisions] == [1]
        assert revisions[0]["snapshot"]["contract_price_gbp_mwh"] == "29.75"
        assert revisions[0]["recorded_by"] == "service:public-api"

    captures = _audit_rows(url, "route_cost.contract.capture_revision")
    assert [row.outcome for row in captures] == ["captured"]
    mutations = _audit_rows(url, "route_cost.contract.upsert")
    assert [row.outcome for row in mutations] == ["created"]
    assert mutations[0].principal == "service:public-api"
    assert mutations[0].resource == f"upstream_contract:{CONTRACT_ID}"
    assert mutations[0].after_summary["latest_revision_number"] == 1
    assert "changed_fields=none" in mutations[0].detail


def test_identical_replay_writes_nothing_and_preserves_attribution(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    first = _deployment_client().post(CONTRACT_PATH, json=_body())
    assert first.status_code == 200, first.text
    first_revision = first.json()["data"]["latest_revision"]
    with _session(url) as session:
        first_updated_at = session.get(
            UpstreamResourceContractRecord, CONTRACT_ID
        ).updated_at_utc

    # A *different* authenticated caller replays the identical payload.
    analyst_client, analyst_id = _analyst_client(url)
    replay = analyst_client.post(CONTRACT_PATH, json=_body())

    assert replay.status_code == 200, replay.text
    data = replay.json()["data"]
    assert data["write_outcome"] == "unchanged"
    # The original recorder and timestamp survive the replay.
    _assert_same_revision_identity(data["latest_revision"], first_revision)
    assert data["latest_revision"]["recorded_by"] == "service:public-api"
    assert data["updated_at_utc"] == first_updated_at.isoformat()
    assert "latest_revision" in data

    with _session(url) as session:
        assert session.query(UpstreamContractRevisionRecord).count() == 1
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        assert row.updated_at_utc == first_updated_at
    # No duplicate mutation audit and no second capture audit for a true replay.
    assert len(_audit_rows(url)) == 2
    assert len(_audit_rows(url, "route_cost.contract.upsert")) == 1
    assert analyst_id not in {
        row.principal for row in _audit_rows(url)
    }


def test_economic_change_captures_previous_and_new_state(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    analyst_client, analyst_id = _analyst_client(url)
    created = analyst_client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    first_revision_id = created.json()["data"]["latest_revision"]["contract_revision_id"]

    changed = _deployment_client().post(
        CONTRACT_PATH, json=_body(contract_price_gbp_mwh=31.5)
    )

    assert changed.status_code == 200, changed.text
    data = changed.json()["data"]
    assert data["contract_price_gbp_mwh"] == 31.5
    assert data["write_outcome"] == "economics_updated"
    assert data["latest_revision"]["revision_number"] == 2
    assert data["latest_revision"]["recorded_by"] == "service:public-api"

    with _session(url) as session:
        revisions = list_upstream_contract_revisions(session, CONTRACT_ID)
        assert [item["revision_number"] for item in revisions] == [1, 2]
        # The previous snapshot is untouched by the later overwrite.
        assert revisions[0]["contract_revision_id"] == first_revision_id
        assert revisions[0]["snapshot"]["contract_price_gbp_mwh"] == "29.75"
        assert revisions[0]["recorded_by"] == analyst_id
        assert revisions[1]["snapshot"]["contract_price_gbp_mwh"] == "31.5"
        assert (
            session.get(UpstreamResourceContractRecord, CONTRACT_ID).contract_price_gbp_mwh
            == 31.5
        )

    mutations = _audit_rows(url, "route_cost.contract.upsert")
    assert [row.outcome for row in mutations] == ["created", "economics_updated"]
    assert [row.principal for row in mutations] == [analyst_id, "service:public-api"]
    assert mutations[1].correlation_id == changed.headers["x-request-id"]
    assert mutations[1].before_summary["latest_revision_number"] == 1
    assert mutations[1].after_summary["latest_revision_number"] == 2
    assert mutations[1].after_summary["changed_fields"] == ["contract_price_gbp_mwh"]
    assert len(_audit_rows(url, "route_cost.contract.capture_revision")) == 2


def test_metadata_only_change_is_audited_without_a_new_revision(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    analyst_client, analyst_id = _analyst_client(url)
    created = analyst_client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    first_revision = created.json()["data"]["latest_revision"]

    renamed = _deployment_client().post(
        CONTRACT_PATH,
        json=_body(contract_name="Renamed governed supply", notes="renamed operator notes"),
    )

    assert renamed.status_code == 200, renamed.text
    data = renamed.json()["data"]
    assert data["contract_name"] == "Renamed governed supply"
    assert data["write_outcome"] == "metadata_updated"
    # The economics capture is idempotent: no new revision, original attribution.
    _assert_same_revision_identity(data["latest_revision"], first_revision)

    with _session(url) as session:
        assert session.query(UpstreamContractRevisionRecord).count() == 1
        assert session.get(UpstreamResourceContractRecord, CONTRACT_ID).contract_name == (
            "Renamed governed supply"
        )

    mutations = _audit_rows(url, "route_cost.contract.upsert")
    assert [row.outcome for row in mutations] == ["created", "metadata_updated"]
    assert mutations[1].principal == "service:public-api"
    assert set(mutations[1].after_summary["changed_fields"]) == {"contract_name", "notes"}
    # The economics capture wrote nothing, so there is no second capture audit.
    assert len(_audit_rows(url, "route_cost.contract.capture_revision")) == 1
    assert analyst_id not in {row.principal for row in mutations[1:]}


def test_stored_terms_that_cannot_be_captured_refuse_the_overwrite(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        # Seed the stored row, then corrupt its notes outside the upsert - the
        # shape a legacy row can have and a governed write must not destroy.
        upsert_upstream_contract(session, _body(contract_id=UNAUTHORISED_CONTRACT_ID))
        session.execute(
            text(
                "UPDATE upstream_resource_contracts SET notes = :notes"
                " WHERE contract_id = :contract_id"
            ),
            {"notes": "variable cost 0.75 gbp/mwh", "contract_id": UNAUTHORISED_CONTRACT_ID},
        )
        session.commit()

    response = _deployment_client().post(
        CONTRACT_PATH,
        json=_body(contract_id=UNAUTHORISED_CONTRACT_ID, contract_price_gbp_mwh=99.0),
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "conflict"
    assert detail["code"] == "contract_revision_mapping_ambiguous"

    with _session(url) as session:
        row = session.get(UpstreamResourceContractRecord, UNAUTHORISED_CONTRACT_ID)
        # The malformed terms and the rest of the row are preserved; the
        # requested price was never written.
        assert row.notes == "variable cost 0.75 gbp/mwh"
        assert row.contract_price_gbp_mwh == 29.75
        assert session.query(UpstreamContractRevisionRecord).count() == 0
    assert _audit_rows(url) == []


def test_audit_writer_failure_rolls_back_the_whole_contract_write(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    created = _deployment_client().post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    first_revision_id = created.json()["data"]["latest_revision"]["contract_revision_id"]

    def _refuse_audit(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(
        "eurogas_nexus.db.repositories.route_cost.record_audit_event", _refuse_audit
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    failed = client.post(CONTRACT_PATH, json=_body(contract_price_gbp_mwh=31.5))

    assert failed.status_code == 500
    assert "audit store unavailable" not in failed.text
    with _session(url) as session:
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        # The overwrite, its capture and its audit rolled back together.
        assert row.contract_price_gbp_mwh == 29.75
        revisions = list_upstream_contract_revisions(session, CONTRACT_ID)
        assert [item["revision_number"] for item in revisions] == [1]
        assert revisions[0]["contract_revision_id"] == first_revision_id
        assert revisions[0]["snapshot"]["contract_price_gbp_mwh"] == "29.75"
    assert len(_audit_rows(url, "route_cost.contract.upsert")) == 1
    assert len(_audit_rows(url, "route_cost.contract.capture_revision")) == 1


def test_audit_writer_failure_rolls_back_a_created_contract(
    tmp_path, monkeypatch
) -> None:
    """A creation that cannot be attributed must not persist either."""

    url = _prepare_db(tmp_path, monkeypatch)

    def _refuse_audit(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(
        "eurogas_nexus.db.repositories.route_cost.record_audit_event", _refuse_audit
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    failed = client.post(CONTRACT_PATH, json=_body())

    assert failed.status_code == 500
    with _session(url) as session:
        assert session.get(UpstreamResourceContractRecord, CONTRACT_ID) is None
        assert session.query(UpstreamContractRevisionRecord).count() == 0
    assert _audit_rows(url) == []


def test_create_race_loser_recovers_as_a_governed_update(
    tmp_path, monkeypatch
) -> None:
    """A create whose row appears mid-flight must not leak the key conflict.

    The winner's commit between the governed call's own lock read and its
    insert is simulated by letting the first lock read report "no row" while
    the row already exists. The conflict-tolerant insert then inserts nothing
    exactly as it would under PostgreSQL, and the same transaction must
    re-read the committed row and continue as an update.
    """

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        # The concurrent winner's committed row: same identity, different price,
        # written by the ungoverned repository path so it carries no revision yet.
        upsert_upstream_contract(session, _body(contract_price_gbp_mwh=28.0))
        session.commit()

    real_lock = route_cost_repository._locked_contract_row
    lock_calls = {"count": 0}

    def _raced_lock(session, contract_id):
        lock_calls["count"] += 1
        if lock_calls["count"] == 1:
            return None
        return real_lock(session, contract_id)

    monkeypatch.setattr(route_cost_repository, "_locked_contract_row", _raced_lock)

    response = _deployment_client().post(CONTRACT_PATH, json=_body())

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["write_outcome"] == "economics_updated"
    assert data["contract_price_gbp_mwh"] == 29.75
    assert lock_calls["count"] >= 2
    with _session(url) as session:
        assert session.query(UpstreamResourceContractRecord).count() == 1
        revisions = list_upstream_contract_revisions(session, CONTRACT_ID)
        # The winner's committed state was captured before it was replaced.
        assert [item["revision_number"] for item in revisions] == [1, 2]
        assert revisions[0]["snapshot"]["contract_price_gbp_mwh"] == "28.0"
        assert revisions[1]["snapshot"]["contract_price_gbp_mwh"] == "29.75"

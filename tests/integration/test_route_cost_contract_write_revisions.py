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
* saved-contract reads and the write response carry the same opaque edit
  token, and an update only succeeds with the token from the current read;
* economics-only and metadata-only edits both invalidate the previous token,
  and a stale update leaves the row, its revisions and its audit trail
  unchanged;
* a create-only request (no token) never overwrites an existing identity, a
  concurrent create loser refuses instead of taking over the winner's row, and
  a token for a nonexistent identity writes nothing;
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


def _read_token(client: TestClient, contract_id: str = CONTRACT_ID) -> str:
    """Read one stored contract's current edit token through the public read."""

    response = client.get(CONTRACT_PATH)
    assert response.status_code == 200, response.text
    row = next(
        item for item in response.json()["data"] if item["contract_id"] == contract_id
    )
    token = row.get("edit_token")
    assert isinstance(token, str), f"no edit_token on the stored read: {row!r}"
    assert token.startswith("sha256:")
    return token


def _audit_rows(url: str, action: str | None = None) -> list[AuditEventRecord]:
    with _session(url) as session:
        query = session.query(AuditEventRecord)
        if action:
            query = query.filter(AuditEventRecord.action == action)
        return query.order_by(AuditEventRecord.event_ts_utc).all()


def _stored_revision_count(url: str) -> int:
    with _session(url) as session:
        return session.query(UpstreamContractRevisionRecord).count()


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
    assert data["edit_token"].startswith("sha256:")
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


def test_saved_contract_reads_carry_a_stable_edit_token(tmp_path, monkeypatch) -> None:
    """The write response token, the read token and a fresh-session read agree."""

    url = _prepare_db(tmp_path, monkeypatch)

    created = _deployment_client().post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    write_token = created.json()["data"]["edit_token"]

    first_read = _deployment_client().get(CONTRACT_PATH)
    assert first_read.status_code == 200, first_read.text
    read_token = first_read.json()["data"][0]["edit_token"]
    assert read_token == write_token

    # A read in a *fresh* session (and a fresh engine) serializes the same stored
    # state to the same token: the token is a function of the persisted row, not
    # of the session that read it.
    with _session(url) as session:
        fresh_token = route_cost_repository.contract_edit_token(
            session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        )
    assert fresh_token == write_token

    # The stored-contract read is still a read: nothing was captured or audited
    # by either read.
    assert len(_audit_rows(url)) == 2
    with _session(url) as session:
        assert session.query(UpstreamContractRevisionRecord).count() == 1


def test_economics_and_metadata_edits_both_invalidate_the_previous_token(
    tmp_path, monkeypatch
) -> None:
    """A token covers the whole persisted row: price *and* name/notes changes."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    first_token = created.json()["data"]["edit_token"]

    # An economics-only edit through the token refreshes it.
    economic = client.post(
        CONTRACT_PATH,
        json=_body(contract_price_gbp_mwh=31.5, expected_edit_token=first_token),
    )
    assert economic.status_code == 200, economic.text
    assert economic.json()["data"]["write_outcome"] == "economics_updated"
    after_economic = economic.json()["data"]["edit_token"]
    assert after_economic != first_token

    # A metadata-only edit (name and raw notes; no captured economic revision)
    # also invalidates the previous token.
    metadata = client.post(
        CONTRACT_PATH,
        json=_body(
            contract_price_gbp_mwh=31.5,
            contract_name="Renamed governed supply",
            notes="renamed operator notes",
            expected_edit_token=after_economic,
        ),
    )
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["data"]["write_outcome"] == "metadata_updated"
    after_metadata = metadata.json()["data"]["edit_token"]
    assert after_metadata != after_economic
    assert _read_token(client) == after_metadata

    # Both previous tokens are now stale and are refused without any write.
    revisions_before = _stored_revision_count(url)
    audits_before = len(_audit_rows(url))
    for stale in (first_token, after_economic):
        refused = client.post(
            CONTRACT_PATH,
            json=_body(expected_edit_token=stale),
        )
        assert refused.status_code == 409, refused.text
        detail = refused.json()["detail"]
        assert detail["error"] == "conflict"
        assert detail["code"] == "contract_edit_conflict"
        # The refusal is sanitized: no stale token, no stored values.
        assert stale not in refused.text
        assert "31.5" not in refused.text
    with _session(url) as session:
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        assert row.contract_price_gbp_mwh == 31.5
        assert row.contract_name == "Renamed governed supply"
    assert _stored_revision_count(url) == revisions_before
    assert len(_audit_rows(url)) == audits_before


def test_create_only_request_never_overwrites_an_existing_identity(
    tmp_path, monkeypatch
) -> None:
    """An omitted/null token means create: an existing identity is refused."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    first_revision = created.json()["data"]["latest_revision"]

    for overrides in ({}, {"expected_edit_token": None}):
        refused = client.post(
            CONTRACT_PATH,
            json=_body(contract_price_gbp_mwh=99.5, **overrides),
        )
        assert refused.status_code == 409, refused.text
        detail = refused.json()["detail"]
        assert detail["error"] == "conflict"
        assert detail["code"] == "contract_edit_conflict"
        assert "99.5" not in refused.text

    with _session(url) as session:
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        assert row.contract_price_gbp_mwh == 29.75
        revisions = list_upstream_contract_revisions(session, CONTRACT_ID)
        assert [item["revision_number"] for item in revisions] == [1]
        assert revisions[0]["contract_revision_id"] == first_revision["contract_revision_id"]
    assert len(_audit_rows(url, "route_cost.contract.upsert")) == 1
    assert len(_audit_rows(url, "route_cost.contract.capture_revision")) == 1


def test_expected_token_for_a_nonexistent_row_writes_nothing(
    tmp_path, monkeypatch
) -> None:
    """A token can only update the stored contract it was read from."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    token = created.json()["data"]["edit_token"]

    refused = client.post(
        CONTRACT_PATH,
        json=_body(contract_id="no-such-contract", expected_edit_token=token),
    )
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "conflict"
    assert detail["code"] == "contract_edit_conflict"
    assert token not in refused.text

    with _session(url) as session:
        assert session.get(UpstreamResourceContractRecord, "no-such-contract") is None
        assert session.query(UpstreamResourceContractRecord).count() == 1
        assert session.query(UpstreamContractRevisionRecord).count() == 1
    assert len(_audit_rows(url)) == 2


def test_malformed_expected_token_is_refused_without_touching_the_store(
    tmp_path, monkeypatch
) -> None:
    """A token that is not this API's token shape is malformed, not compared."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text

    for malformed in ("", "not-a-token", "sha256:" + "0" * 63, "SHA256:" + "0" * 64):
        refused = client.post(
            CONTRACT_PATH,
            json=_body(contract_price_gbp_mwh=99.5, expected_edit_token=malformed),
        )
        assert refused.status_code == 409, refused.text
        detail = refused.json()["detail"]
        assert detail["error"] == "conflict"
        assert detail["code"] == "contract_edit_token_malformed"

    with _session(url) as session:
        stored = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        assert stored.contract_price_gbp_mwh == 29.75
        assert session.query(UpstreamContractRevisionRecord).count() == 1
    assert len(_audit_rows(url)) == 2


def test_successful_update_with_the_read_token_preserves_unknown_notes(
    tmp_path, monkeypatch
) -> None:
    """The precondition does not change the notes-preservation round trip."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    notes = json.dumps(
        {
            "source": "upstream_confirmation_capture",
            "capture_reference": "case-4711",
            "indexation": {"index": "TTF", "enabled": False},
            "variable_cost_gbp_mwh": 0.75,
        },
        sort_keys=True,
    )
    created = client.post(CONTRACT_PATH, json=_body(notes=notes))
    assert created.status_code == 200, created.text

    # The editor's round trip: the stored notes object plus the one edited field.
    stored_notes = json.loads(created.json()["data"]["notes"])
    updated_notes = {**stored_notes, "counterparty": "Recorded counterparty"}
    updated = client.post(
        CONTRACT_PATH,
        json=_body(
            contract_price_gbp_mwh=31.5,
            notes=json.dumps(updated_notes, sort_keys=True),
            expected_edit_token=created.json()["data"]["edit_token"],
        ),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["write_outcome"] == "economics_updated"

    with _session(url) as session:
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        stored = json.loads(row.notes)
        assert stored["source"] == "upstream_confirmation_capture"
        assert stored["capture_reference"] == "case-4711"
        assert stored["indexation"] == {"index": "TTF", "enabled": False}
        assert stored["counterparty"] == "Recorded counterparty"
        assert stored["variable_cost_gbp_mwh"] == 0.75


def test_identical_replay_writes_nothing_and_preserves_attribution(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    first = _deployment_client().post(CONTRACT_PATH, json=_body())
    assert first.status_code == 200, first.text
    first_revision = first.json()["data"]["latest_revision"]
    read_token = _read_token(_deployment_client())
    with _session(url) as session:
        first_updated_at = session.get(
            UpstreamResourceContractRecord, CONTRACT_ID
        ).updated_at_utc

    # A *different* authenticated caller replays the identical payload.
    analyst_client, analyst_id = _analyst_client(url)
    replay = analyst_client.post(
        CONTRACT_PATH,
        json=_body(expected_edit_token=read_token),
    )

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
        CONTRACT_PATH,
        json=_body(
            contract_price_gbp_mwh=31.5,
            expected_edit_token=_read_token(_deployment_client()),
        ),
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
        json=_body(
            contract_name="Renamed governed supply",
            notes="renamed operator notes",
            expected_edit_token=_read_token(_deployment_client()),
        ),
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
        json=_body(
            contract_id=UNAUTHORISED_CONTRACT_ID,
            contract_price_gbp_mwh=99.0,
            expected_edit_token=_read_token(
                _deployment_client(), UNAUTHORISED_CONTRACT_ID
            ),
        ),
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
    read_token = _read_token(_deployment_client())

    def _refuse_audit(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(
        "eurogas_nexus.db.repositories.route_cost.record_audit_event", _refuse_audit
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    failed = client.post(
        CONTRACT_PATH,
        json=_body(contract_price_gbp_mwh=31.5, expected_edit_token=read_token),
    )

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


def test_create_race_loser_refuses_conflict_and_keeps_the_winner(
    tmp_path, monkeypatch
) -> None:
    """A create whose row appears mid-flight must refuse, never take over.

    The winner's commit between the governed call's own lock read and its
    insert is simulated by letting the first lock read report "no row" while
    the row already exists. The conflict-tolerant insert then inserts nothing
    exactly as it would under PostgreSQL. Because the request supplied no edit
    token (create-only), the loser must refuse with ``contract_edit_conflict``
    rather than continue as an overwrite: the winner's committed row,
    revisions and audit trail are untouched.
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

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "conflict"
    assert detail["code"] == "contract_edit_conflict"
    # The refusal is sanitized: no current or requested commercial values.
    assert "28.0" not in response.text
    assert "29.75" not in response.text
    with _session(url) as session:
        assert session.query(UpstreamResourceContractRecord).count() == 1
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        # The winner's row is intact; the loser overwrote and captured nothing.
        assert row.contract_price_gbp_mwh == 28.0
        assert session.query(UpstreamContractRevisionRecord).count() == 0
    assert _audit_rows(url) == []

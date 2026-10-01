"""Governed captured-revision reads: bounded, scoped, verified and read-only.

`docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md` section 11: the
captured revisions written by the governed contract write are now reachable
through the existing route-cost contract family, without a new page and
without a second write path:

* ``GET /api/route-cost/upstream-contracts/{contract_id}/revisions`` lists one
  contract's verified capture evidence as a bounded, ordered page;
* ``GET .../revisions/{contract_revision_id}`` reads one revision, explicitly
  scoped to its contract, so a cross-contract id answers the same 404 as an
  unknown id;
* an unknown contract is 404 while an existing contract without captures is an
  empty page with an explicit warning;
* a tampered stored snapshot is refused with a stable structured code instead
  of being served (and without echoing stored content or driver text);
* reading never captures: a changed source row read through these routes adds
  no revision and no audit row, and the original recorder/instant are
  preserved.

These tests run the real routes against a throw-away SQLite runtime store. Row
locking and PostgreSQL-authoritative concurrency remain covered by the
disposable CI PostgreSQL job.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public.route_cost import (
    CONTRACT_REVISION_EMPTY_WARNING,
    CONTRACT_REVISION_EVIDENCE_WARNINGS,
)
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.db.repositories.route_cost import (
    capture_upstream_contract_revision,
    upsert_upstream_contract,
)

PUBLIC_TOKEN = "test-public-api-token"
CONTRACT_ID = "revision-read-ttf-supply-2025"
OTHER_CONTRACT_ID = "revision-read-other-supply-2025"
REVISIONS_PATH = f"/api/route-cost/upstream-contracts/{CONTRACT_ID}/revisions"


def _body(contract_id: str = CONTRACT_ID, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_id": contract_id,
        "contract_name": "Revision read TTF supply 2025",
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
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'revision-reads.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _session(url: str) -> Session:
    return Session(create_engine(url, future=True))


def _analyst_bearer(session: Session, name: str) -> tuple[str, str]:
    principal = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role="ANALYST",
        data_scopes=["TTF"],
    )
    _key, bearer = create_identity_api_key(session, principal.principal_id, display_name=name)
    return principal.principal_id, bearer


def _release_client(bearer: str) -> TestClient:
    client = TestClient(create_app(Settings(api_profile="release")))
    client.headers.update(
        {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
    )
    return client


def _seed_contract(session: Session, contract_id: str, *, price: float = 29.75) -> None:
    upsert_upstream_contract(session, _body(contract_id, contract_price_gbp_mwh=price))
    session.commit()


def _capture(
    session: Session,
    contract_id: str,
    *,
    actor: str = "history-trader",
    price: float | None = None,
) -> UpstreamContractRevisionRecord:
    if price is not None:
        upsert_upstream_contract(session, _body(contract_id, contract_price_gbp_mwh=price))
    result = capture_upstream_contract_revision(
        session,
        contract_id,
        recorded_by=actor,
        recorded_at_utc=datetime.now(UTC),
    )
    assert result.outcome == "captured"
    assert result.revision is not None
    session.commit()
    return result.revision


def _stored_revision_count(url: str) -> int:
    with _session(url) as session:
        return session.query(UpstreamContractRevisionRecord).count()


def _audit_count(url: str) -> int:
    with _session(url) as session:
        return session.query(AuditEventRecord).count()


def _instant(value: str) -> datetime:
    """Parse a response timestamp: SQLite fixtures drop the UTC offset, PG keeps it."""

    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def test_revision_history_returns_verified_capture_evidence(tmp_path, monkeypatch) -> None:
    """The history read serves the stored evidence with its capture metadata."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        _analyst_id, bearer = _analyst_bearer(session, "revision-history-reader")
        _seed_contract(session, CONTRACT_ID)
        _capture(session, CONTRACT_ID, actor="history-trader")
        _capture(session, CONTRACT_ID, actor="history-trader", price=31.5)
        session.commit()

    response = _release_client(bearer).get(REVISIONS_PATH)

    assert response.status_code == 200, response.text
    payload = response.json()
    data = payload["data"]
    assert data["scope"] == "UPSTREAM_CONTRACT_REVISIONS"
    assert data["data_source"] == "runtime-postgresql"
    assert data["contract_id"] == CONTRACT_ID
    assert data["revision_count"] == 2
    assert data["returned_count"] == 2
    assert data["has_more"] is False
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert [item["revision_number"] for item in data["revisions"]] == [1, 2]

    first = data["revisions"][0]
    assert first["contract_id"] == CONTRACT_ID
    assert first["schema_version"] == "upstream-contract-revision/v1"
    assert first["capture_origin"] == "legacy_capture"
    assert first["content_hash"].startswith("sha256:")
    assert first["recorded_by"] == "history-trader"
    recorded_at = _instant(first["recorded_at_utc"])
    assert recorded_at.tzinfo is not None
    # The capture preserves the raw stored operator notes verbatim (the legacy
    # upsert stores structured note fields inside that text).
    with _session(url) as session:
        stored_notes = session.query(UpstreamResourceContractRecord.notes).one()[0]
    assert first["display_metadata"] == {
        "contract_name": "Revision read TTF supply 2025",
        "operator_notes": stored_notes,
    }
    assert "operator draft decision support" in stored_notes
    # Exact decimal strings and null-versus-zero survive transport unchanged.
    assert first["snapshot"]["contract_price_gbp_mwh"] == "29.75"
    assert first["snapshot"]["payment_terms"] is None
    assert data["revisions"][1]["snapshot"]["contract_price_gbp_mwh"] == "31.5"

    meta = payload["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True
    assert meta["source_references"] == ["runtime-postgresql"]
    for warning in CONTRACT_REVISION_EVIDENCE_WARNINGS:
        assert warning in meta["warnings"]
    assert CONTRACT_REVISION_EMPTY_WARNING not in meta["warnings"]


def test_unknown_contract_is_404_while_no_captures_is_an_empty_page(
    tmp_path, monkeypatch
) -> None:
    """Missing contract and existing-without-captures are visibly different."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        _analyst_id, bearer = _analyst_bearer(session, "revision-empty-reader")
        _seed_contract(session, OTHER_CONTRACT_ID)
        session.commit()

    client = _release_client(bearer)
    unknown = client.get("/api/route-cost/upstream-contracts/no-such-contract/revisions")
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "upstream_contract_not_found"
    assert unknown.json()["detail"]["error"] == "not_found"

    empty = client.get(f"/api/route-cost/upstream-contracts/{OTHER_CONTRACT_ID}/revisions")
    assert empty.status_code == 200, empty.text
    data = empty.json()["data"]
    assert data["contract_id"] == OTHER_CONTRACT_ID
    assert data["revisions"] == []
    assert data["revision_count"] == 0
    assert data["returned_count"] == 0
    assert data["has_more"] is False
    assert CONTRACT_REVISION_EMPTY_WARNING in empty.json()["meta"]["warnings"]

    missing_revision = client.get(
        f"/api/route-cost/upstream-contracts/{OTHER_CONTRACT_ID}/revisions/no-such-revision"
    )
    assert missing_revision.status_code == 404
    assert missing_revision.json()["detail"]["code"] == "contract_revision_not_found"


def test_revision_read_is_scoped_to_the_named_contract(tmp_path, monkeypatch) -> None:
    """A revision id is only answered under the contract it was captured for."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        _analyst_id, bearer = _analyst_bearer(session, "revision-scope-reader")
        _seed_contract(session, CONTRACT_ID)
        _seed_contract(session, OTHER_CONTRACT_ID)
        revision = _capture(session, CONTRACT_ID, actor="scoped-trader")
        session.commit()
        revision_id = revision.contract_revision_id

    client = _release_client(bearer)
    scoped = client.get(f"{REVISIONS_PATH}/{revision_id}")
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["data"]["contract_revision_id"] == revision_id
    assert scoped.json()["data"]["contract_id"] == CONTRACT_ID
    assert scoped.json()["data"]["scope"] == "UPSTREAM_CONTRACT_REVISION"

    cross_contract = client.get(
        f"/api/route-cost/upstream-contracts/{OTHER_CONTRACT_ID}/revisions/{revision_id}"
    )
    assert cross_contract.status_code == 404
    assert cross_contract.json()["detail"]["code"] == "contract_revision_not_found"
    # The refusal is one fixed sentence: it never confirms which contract the
    # revision actually belongs to.
    assert CONTRACT_ID not in cross_contract.text

    # The history read is scoped by contract too: the other contract is empty.
    other_history = client.get(
        f"/api/route-cost/upstream-contracts/{OTHER_CONTRACT_ID}/revisions"
    )
    assert other_history.status_code == 200
    assert other_history.json()["data"]["revision_count"] == 0
    assert other_history.json()["data"]["revisions"] == []


def test_tampered_stored_revision_is_refused_with_a_structured_error(
    tmp_path, monkeypatch
) -> None:
    """Stored evidence that fails verification is refused, not served."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        _analyst_id, bearer = _analyst_bearer(session, "revision-tamper-reader")
        _seed_contract(session, CONTRACT_ID)
        revision = _capture(session, CONTRACT_ID, actor="tamper-trader")
        session.commit()
        revision_id = revision.contract_revision_id
    with _session(url) as session:
        session.execute(
            text(
                "UPDATE upstream_contract_revisions SET snapshot_json = :payload"
                " WHERE contract_revision_id = :revision_id"
            ),
            {
                "payload": json.dumps({"tampered": "evidence"}),
                "revision_id": revision_id,
            },
        )
        session.commit()

    client = _release_client(bearer)
    single = client.get(f"{REVISIONS_PATH}/{revision_id}")
    assert single.status_code == 409
    assert single.json()["detail"]["error"] == "conflict"
    assert single.json()["detail"]["code"] == "contract_revision_hash_mismatch"

    history = client.get(REVISIONS_PATH)
    assert history.status_code == 409
    assert history.json()["detail"]["code"] == "contract_revision_hash_mismatch"

    # Sanitized: no driver text, SQL or stack trace is echoed.
    lowered = f"{single.text} {history.text}".lower()
    for leak in ("traceback", "sqlalchemy", "select ", "psycopg", "sqlite"):
        assert leak not in lowered


def test_revision_paging_is_bounded_ordered_and_reads_write_nothing(
    tmp_path, monkeypatch
) -> None:
    """Pages are bounded and ordered, and reads never create captures."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        _analyst_id, bearer = _analyst_bearer(session, "revision-paging-reader")
        _seed_contract(session, CONTRACT_ID)
        _capture(session, CONTRACT_ID, actor="paging-trader", price=30.0)
        _capture(session, CONTRACT_ID, actor="paging-trader", price=31.0)
        _capture(session, CONTRACT_ID, actor="paging-trader", price=32.0)
        session.commit()

    client = _release_client(bearer)
    audits_before = _audit_count(url)
    revisions_before = _stored_revision_count(url)

    first_page = client.get(REVISIONS_PATH, params={"limit": 2})
    assert first_page.status_code == 200, first_page.text
    first_data = first_page.json()["data"]
    assert [item["revision_number"] for item in first_data["revisions"]] == [1, 2]
    assert first_data["revision_count"] == 3
    assert first_data["returned_count"] == 2
    assert first_data["has_more"] is True

    second_page = client.get(REVISIONS_PATH, params={"limit": 2, "offset": 2})
    assert second_page.status_code == 200, second_page.text
    second_data = second_page.json()["data"]
    assert [item["revision_number"] for item in second_data["revisions"]] == [3]
    assert second_data["returned_count"] == 1
    assert second_data["has_more"] is False

    beyond = client.get(REVISIONS_PATH, params={"limit": 2, "offset": 10})
    assert beyond.status_code == 200
    assert beyond.json()["data"]["revision_count"] == 3
    assert beyond.json()["data"]["revisions"] == []
    assert CONTRACT_REVISION_EMPTY_WARNING not in beyond.json()["meta"]["warnings"]

    # The page size is bounded and offsets cannot be negative.
    assert client.get(REVISIONS_PATH, params={"limit": 500}).status_code == 422
    assert client.get(REVISIONS_PATH, params={"limit": 0}).status_code == 422
    assert client.get(REVISIONS_PATH, params={"offset": -1}).status_code == 422

    # A source row changed after the last capture is not captured by reading:
    # the plain repository write keeps overwriting the mutable row, and the
    # revision history must not silently grow from a read.
    with _session(url) as session:
        upsert_upstream_contract(session, _body(CONTRACT_ID, contract_price_gbp_mwh=99.5))
        session.commit()
    reread = client.get(REVISIONS_PATH)
    assert reread.status_code == 200, reread.text
    assert reread.json()["data"]["revision_count"] == 3
    assert [item["revision_number"] for item in reread.json()["data"]["revisions"]] == [1, 2, 3]
    assert _stored_revision_count(url) == revisions_before == 3
    assert _audit_count(url) == audits_before


def test_read_preserves_the_original_capture_actor_and_instant(
    tmp_path, monkeypatch
) -> None:
    """A read by another principal never re-attributes stored evidence."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        writer_id, writer_bearer = _analyst_bearer(session, "revision-writer")
        reader_id, reader_bearer = _analyst_bearer(session, "revision-reader")
        session.commit()

    writer = _release_client(writer_bearer)
    created = writer.post(
        "/api/route-cost/upstream-contracts",
        json=_body(),
    )
    assert created.status_code == 200, created.text
    written = created.json()["data"]["latest_revision"]
    assert written["recorded_by"] == writer_id

    reader = _release_client(reader_bearer)
    history = reader.get(REVISIONS_PATH)
    assert history.status_code == 200, history.text
    evidence = history.json()["data"]["revisions"][0]
    assert evidence["recorded_by"] == writer_id
    assert _instant(evidence["recorded_at_utc"]) == _instant(written["recorded_at_utc"])
    assert evidence["contract_revision_id"] == written["contract_revision_id"]
    assert evidence["content_hash"] == written["content_hash"]

    # Reading again as the writer returns the identical attribution: the read
    # path records nothing and rewrites nothing.
    again = writer.get(REVISIONS_PATH)
    assert again.status_code == 200, again.text
    repeated = again.json()["data"]["revisions"][0]
    assert repeated["recorded_by"] == writer_id
    assert _instant(repeated["recorded_at_utc"]) == _instant(evidence["recorded_at_utc"])
    assert repeated["content_hash"] == evidence["content_hash"]
    with _session(url) as session:
        stored = session.query(UpstreamContractRevisionRecord).one()
        assert stored.recorded_by == writer_id
        assert session.query(UpstreamResourceContractRecord).count() == 1

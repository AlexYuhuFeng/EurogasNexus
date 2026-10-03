"""S2b declared payment-terms persistence on the governed contract write.

`docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md` section 15: the
nullable ``payment_terms_json`` carrier is written and read with field
presence semantics - omitted preserves, explicit null clears, a strict
canonical ``contract-payment-terms/v1`` document is validated before any
business mutation and stored as its own canonical JSON. These tests run the
real route and the repository helpers against a throw-away SQLite runtime
store and assert:

* a create with declared terms stores the canonical text and captures a v2
  revision carrying them; a create without terms stores NULL and captures the
  unchanged v1 snapshot (an untouched legacy state gains no schema-only
  revision);
* omitting the field while changing another field preserves the stored
  declaration; explicit null deliberately clears it and the post-capture is a
  v1 snapshot again;
* a terms-only edit is an economic change: both sides are captured, the
  declared revision replays as v2 through the verified revision reads, and a
  stale token is refused with ``contract_edit_conflict`` before any capture,
  audit or mutation;
* a denied authority writes nothing, including nothing to the terms carrier;
* a malformed supplied declaration is refused with the shared strict decoder's
  stable, sanitized code before any write, and the sentinel is never echoed,
  whichever shape (mapping or wrong-typed value) reaches the route;
* a corrupt stored declaration fails closed on read and on write even when the
  request asks to clear it, and the corrupt text is preserved, not repaired;
* the internal compatibility upsert applies the same set/preserve/clear rules
  without any route.

PostgreSQL-authoritative lock semantics remain covered by the existing
disposable-database opt-in job; no test here migrates or writes a runtime
store.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
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
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.db.repositories.route_cost import (
    CONTRACT_PAYMENT_TERMS_CORRUPT,
    CONTRACT_REVISION_ALREADY_CAPTURED,
    CONTRACT_REVISION_CAPTURED,
    ContractPaymentTermsRefusal,
    capture_upstream_contract_revision,
    contract_edit_token,
    get_upstream_contract_revision,
    list_upstream_contract_revisions,
    upsert_upstream_contract,
)
from eurogas_nexus.domain.route_cost.contract_revision import (
    CONTRACT_REVISION_SCHEMA_VERSION,
    CONTRACT_REVISION_SCHEMA_VERSION_V2,
)
from eurogas_nexus.domain.route_cost.payment_terms import ContractPaymentTerms

PUBLIC_TOKEN = "test-public-api-token"
CONTRACT_PATH = "/api/route-cost/upstream-contracts"
CONTRACT_ID = "s2b-ttf-supply-2025"

#: A piece of untrusted text that must never be echoed by a refusal.
SENTINEL = "sentinel-supplied-value-must-not-be-echoed"


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_id": CONTRACT_ID,
        "contract_name": "S2b TTF supply 2025",
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


def _terms_document(**overrides: object) -> dict[str, object]:
    """One strict canonical declaration document (both date shapes)."""

    document: dict[str, object] = {
        "schema_version": "contract-payment-terms/v1",
        "quantity_basis_reference": "invoiced_quantity",
        "items": [
            {
                "item_id": "supply-1",
                "cash_flow_category": "cargo_purchase",
                "flow_direction": "OUTFLOW",
                "source_reference": "contract clause 5.1",
                "date_specification": {
                    "kind": "EXPLICIT_DATE",
                    "final_payable_date": "2026-11-30",
                    "source_reference": "invoice INV-2026-0042",
                },
            }
        ],
    }
    document.update(overrides)
    return document


def _canonical_terms_text(document: dict[str, object]) -> str:
    return ContractPaymentTerms.from_canonical_document(document).canonical_json()


def _prepare_db(tmp_path, monkeypatch) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'payment-terms.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _deployment_client() -> TestClient:
    """The development-profile SDK/CLI caller: the deployment's own principal."""

    return TestClient(create_app())


def _release_client(url: str, *, role: str) -> TestClient:
    """A release-profile client acting as a distinct authenticated identity."""

    with Session(create_engine(url, future=True)) as session:
        principal = create_identity_principal(
            session,
            name=f"s2b-{role.lower()}",
            display_name=f"S2b {role.title()}",
            role=role,
            data_scopes=["TTF"],
        )
        _key, bearer = create_identity_api_key(
            session, principal.principal_id, display_name="s2b-payment-terms"
        )
        session.commit()
    client = TestClient(create_app(Settings(api_profile="release")))
    client.headers.update(
        {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
    )
    return client


def _session(url: str) -> Session:
    return Session(create_engine(url, future=True))


def _read_token(client: TestClient, contract_id: str = CONTRACT_ID) -> str:
    response = client.get(CONTRACT_PATH)
    assert response.status_code == 200, response.text
    row = next(
        item for item in response.json()["data"] if item["contract_id"] == contract_id
    )
    token = row.get("edit_token")
    assert isinstance(token, str), f"no edit_token on the stored read: {row!r}"
    assert token.startswith("sha256:")
    return token


def _stored_terms_text(url: str, contract_id: str = CONTRACT_ID) -> str | None:
    with _session(url) as session:
        return session.get(UpstreamResourceContractRecord, contract_id).payment_terms_json


def _stored_rows(url: str, contract_id: str = CONTRACT_ID) -> tuple[int, int]:
    """(revision rows, audit rows) for the whole fixture store."""

    with _session(url) as session:
        revisions = session.query(UpstreamContractRevisionRecord).count()
        audits = session.query(AuditEventRecord).count()
    return revisions, audits


def _revision_snapshots(url: str) -> list[dict]:
    with _session(url) as session:
        return list_upstream_contract_revisions(session, CONTRACT_ID)


def test_create_with_declared_terms_stores_canonical_text_and_captures_v2(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    document = _terms_document()

    response = _deployment_client().post(
        CONTRACT_PATH, json=_body(payment_terms=document)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["payment_terms"] == document
    assert data["write_outcome"] == "created"

    # Stored text is the declaration's own canonical JSON: strict replay and an
    # exact token are possible, and no other field was folded in.
    stored = _stored_terms_text(url)
    assert stored == _canonical_terms_text(document)
    assert ContractPaymentTerms.from_canonical_document(json.loads(stored)) == (
        ContractPaymentTerms.from_canonical_document(document)
    )

    revisions = _revision_snapshots(url)
    assert [item["revision_number"] for item in revisions] == [1]
    assert revisions[0]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert revisions[0]["snapshot"]["payment_terms"] == document

    # The stored-contract read decodes the declaration rather than echoing text.
    read = _deployment_client().get(CONTRACT_PATH)
    assert read.status_code == 200, read.text
    row = next(item for item in read.json()["data"] if item["contract_id"] == CONTRACT_ID)
    assert row["payment_terms"] == document
    assert row["edit_token"].startswith("sha256:")


def test_create_without_terms_stores_null_and_keeps_the_v1_snapshot(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)

    response = _deployment_client().post(CONTRACT_PATH, json=_body())

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["payment_terms"] is None
    assert _stored_terms_text(url) is None
    revisions = _revision_snapshots(url)
    assert revisions[0]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION
    assert revisions[0]["snapshot"]["payment_terms"] is None


def test_omitting_terms_preserves_the_stored_declaration(
    tmp_path, monkeypatch
) -> None:
    """An older client that does not send the field must never erase it."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    document = _terms_document()
    created = client.post(CONTRACT_PATH, json=_body(payment_terms=document))
    assert created.status_code == 200, created.text
    stored_before = _stored_terms_text(url)

    updated = client.post(
        CONTRACT_PATH,
        json=_body(
            contract_price_gbp_mwh=31.5,
            expected_edit_token=_read_token(client),
        ),
    )

    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["write_outcome"] == "economics_updated"
    assert data["payment_terms"] == document
    assert _stored_terms_text(url) == stored_before

    revisions = _revision_snapshots(url)
    # Both sides of the overwrite are evidence: v2 with the terms, then v2 again
    # because the preserved declaration still accompanies the new price.
    assert [item["revision_number"] for item in revisions] == [1, 2]
    assert revisions[1]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert revisions[1]["snapshot"]["payment_terms"] == document
    assert revisions[1]["snapshot"]["contract_price_gbp_mwh"] == "31.5"

    with _session(url) as session:
        mutations = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "route_cost.contract.upsert")
            .all()
        )
    assert mutations[-1].after_summary["changed_fields"] == ["contract_price_gbp_mwh"]


def test_explicit_null_clears_the_declaration_and_returns_to_a_v1_snapshot(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    document = _terms_document()
    created = client.post(CONTRACT_PATH, json=_body(payment_terms=document))
    assert created.status_code == 200, created.text

    cleared = client.post(
        CONTRACT_PATH,
        json=_body(
            contract_price_gbp_mwh=31.5,
            payment_terms=None,
            expected_edit_token=_read_token(client),
        ),
    )

    assert cleared.status_code == 200, cleared.text
    data = cleared.json()["data"]
    assert data["payment_terms"] is None
    assert data["write_outcome"] == "economics_updated"
    assert _stored_terms_text(url) is None

    revisions = _revision_snapshots(url)
    assert [item["revision_number"] for item in revisions] == [1, 2]
    # The declared revision stays exactly as captured; clearing back to "not
    # stated" intentionally produces the v1 economic snapshot again.
    assert revisions[0]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert revisions[0]["snapshot"]["payment_terms"] == document
    assert revisions[1]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION
    assert revisions[1]["snapshot"]["payment_terms"] is None

    with _session(url) as session:
        mutations = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "route_cost.contract.upsert")
            .all()
        )
    assert mutations[-1].after_summary["changed_fields"] == [
        "contract_price_gbp_mwh",
        "payment_terms_json",
    ]


def test_stored_v2_revision_replays_and_a_terms_only_edit_is_economic(
    tmp_path, monkeypatch
) -> None:
    """A declared revision is verified evidence, not just a response field."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    document = _terms_document()

    declared = client.post(
        CONTRACT_PATH,
        json=_body(payment_terms=document, expected_edit_token=_read_token(client)),
    )
    assert declared.status_code == 200, declared.text
    assert declared.json()["data"]["write_outcome"] == "economics_updated"
    latest = declared.json()["data"]["latest_revision"]
    # Two captures (the create and the declared write) and two mutation audits,
    # with no duplicate for the idempotent pre-capture.
    assert _stored_rows(url) == (2, 4)

    # The stored v2 revision replays through the verified repository read with
    # its exact declaration, while the earlier v1 revision is unchanged.
    with _session(url) as session:
        stored = get_upstream_contract_revision(
            session, latest["contract_revision_id"], contract_id=CONTRACT_ID
        )
        revisions = list_upstream_contract_revisions(session, CONTRACT_ID)
    assert stored["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert stored["snapshot"]["payment_terms"] == document
    assert stored["content_hash"] == latest["content_hash"]
    assert [item["revision_number"] for item in revisions] == [1, 2]
    assert revisions[0]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION
    assert revisions[0]["snapshot"]["payment_terms"] is None

    # The declared v2 revision is readable through the public revision route.
    read = client.get(
        f"{CONTRACT_PATH}/{CONTRACT_ID}/revisions/{latest['contract_revision_id']}"
    )
    assert read.status_code == 200, read.text
    assert read.json()["data"]["snapshot"]["payment_terms"] == document


def test_stale_token_after_a_terms_only_edit_is_refused_without_writing(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    stale_token = created.json()["data"]["edit_token"]

    terms_edit = client.post(
        CONTRACT_PATH,
        json=_body(payment_terms=_terms_document(), expected_edit_token=stale_token),
    )
    assert terms_edit.status_code == 200, terms_edit.text
    stored_after_edit = _stored_terms_text(url)
    revisions_before, audits_before = _stored_rows(url)

    refused = client.post(
        CONTRACT_PATH,
        json=_body(
            contract_price_gbp_mwh=99.5,
            payment_terms=None,
            expected_edit_token=stale_token,
        ),
    )

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "conflict"
    assert detail["code"] == "contract_edit_conflict"
    assert stale_token not in refused.text
    assert _stored_terms_text(url) == stored_after_edit
    assert _stored_rows(url) == (revisions_before, audits_before)


def test_denied_authority_writes_nothing_including_the_terms_carrier(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    created = _deployment_client().post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    stored_before = _stored_terms_text(url)
    revisions_before, audits_before = _stored_rows(url)

    viewer = _release_client(url, role="VIEWER")
    refused = viewer.post(
        CONTRACT_PATH,
        json=_body(
            payment_terms=_terms_document(),
            expected_edit_token=_read_token(_deployment_client()),
        ),
    )

    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["error"] == "identity_role_forbidden"
    assert _stored_terms_text(url) == stored_before
    assert _stored_rows(url) == (revisions_before, audits_before)


def test_malformed_supplied_terms_are_refused_sanitized_before_any_write(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    token = _read_token(client)
    revisions_before, audits_before = _stored_rows(url)

    unknown_field = {**_terms_document(), "unexpected": SENTINEL}
    bad_enum = _terms_document()
    bad_enum["items"][0]["flow_direction"] = SENTINEL  # type: ignore[index]

    for malformed, expected_code in (
        (unknown_field, "canonical_field_set_mismatch"),
        (bad_enum, "canonical_flow_direction_unknown"),
        (SENTINEL, "canonical_not_mapping"),
    ):
        refused = client.post(
            CONTRACT_PATH,
            json=_body(
                contract_price_gbp_mwh=99.5,
                payment_terms=malformed,
                expected_edit_token=token,
            ),
        )
        assert refused.status_code == 422, refused.text
        detail = refused.json()["detail"]
        assert detail["error"] == expected_code
        assert SENTINEL not in refused.text

    # Nothing was written by any refused request.
    with _session(url) as session:
        row = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        assert row.payment_terms_json is None
        assert row.contract_price_gbp_mwh == 29.75
    assert _stored_rows(url) == (revisions_before, audits_before)


def test_malformed_supplied_terms_on_create_write_nothing(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)

    refused = _deployment_client().post(
        CONTRACT_PATH, json=_body(payment_terms={"items": [], "unknown": SENTINEL})
    )

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["error"] == "canonical_field_set_mismatch"
    assert SENTINEL not in refused.text
    with _session(url) as session:
        assert session.get(UpstreamResourceContractRecord, CONTRACT_ID) is None
        assert session.query(UpstreamContractRevisionRecord).count() == 0
        assert session.query(AuditEventRecord).count() == 0


def test_corrupt_stored_terms_fail_closed_on_read_and_write(
    tmp_path, monkeypatch
) -> None:
    """Corruption is refused, never served as absent and never silently cleared."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(
        CONTRACT_PATH, json=_body(payment_terms=_terms_document())
    )
    assert created.status_code == 200, created.text
    revisions_before, audits_before = _stored_rows(url)

    corrupt_text = json.dumps(_terms_document(), indent=2)  # decodeable, not canonical
    with _session(url) as session:
        session.execute(
            text(
                "UPDATE upstream_resource_contracts SET payment_terms_json = :text"
                " WHERE contract_id = :contract_id"
            ),
            {"text": corrupt_text, "contract_id": CONTRACT_ID},
        )
        session.commit()

    # The read fails closed with a stable code and no stored content echoed.
    read = client.get(CONTRACT_PATH)
    assert read.status_code == 409, read.text
    assert read.json()["detail"]["code"] == CONTRACT_PAYMENT_TERMS_CORRUPT
    assert corrupt_text not in read.text

    # The only token that can reach the pre-capture is the corrupt row's own
    # (the public read refuses to issue one): clearing must still fail closed
    # and the corrupt declaration must stay in place.
    with _session(url) as session:
        current_token = contract_edit_token(
            session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        )
    refused = client.post(
        CONTRACT_PATH,
        json=_body(payment_terms=None, expected_edit_token=current_token),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == CONTRACT_PAYMENT_TERMS_CORRUPT
    assert corrupt_text not in refused.text
    assert _stored_terms_text(url) == corrupt_text
    assert _stored_rows(url) == (revisions_before, audits_before)

    # Internal imports must not silently repair corrupted evidence either.
    with _session(url) as session:
        with pytest.raises(ValueError) as internal_refusal:
            upsert_upstream_contract(session, _body(payment_terms=None))
        assert internal_refusal.value.code == CONTRACT_PAYMENT_TERMS_CORRUPT
        assert corrupt_text not in str(internal_refusal.value)
        session.rollback()
    assert _stored_terms_text(url) == corrupt_text


def test_audit_writer_failure_rolls_back_the_terms_carrier_and_capture(
    tmp_path, monkeypatch
) -> None:
    """The carrier mutation, its capture and its audit commit or roll back together."""

    url = _prepare_db(tmp_path, monkeypatch)
    client = _deployment_client()
    created = client.post(CONTRACT_PATH, json=_body())
    assert created.status_code == 200, created.text
    token = _read_token(client)

    def _refuse_audit(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(
        "eurogas_nexus.db.repositories.route_cost.record_audit_event", _refuse_audit
    )
    failing = TestClient(create_app(), raise_server_exceptions=False)

    failed = failing.post(
        CONTRACT_PATH,
        json=_body(payment_terms=_terms_document(), expected_edit_token=token),
    )

    assert failed.status_code == 500
    assert "audit store unavailable" not in failed.text
    # Only the creation evidence survives; the declared write rolled back whole.
    assert _stored_terms_text(url) is None
    assert _stored_rows(url) == (1, 2)


def test_internal_helper_applies_set_preserve_and_clear_the_same_way(
    tmp_path, monkeypatch
) -> None:
    """The ungoverned compatibility path uses the shared presence semantics."""

    url = _prepare_db(tmp_path, monkeypatch)
    document = _terms_document()

    with _session(url) as session:
        upsert_upstream_contract(session, _body(payment_terms=document))
        session.commit()
        assert session.get(UpstreamResourceContractRecord, CONTRACT_ID).payment_terms_json == (
            _canonical_terms_text(document)
        )

        # Omitted key: preserve the declaration while another field changes.
        upsert_upstream_contract(session, _body(contract_price_gbp_mwh=31.5))
        session.commit()
        stored = session.get(UpstreamResourceContractRecord, CONTRACT_ID)
        assert stored.payment_terms_json == _canonical_terms_text(document)
        assert stored.contract_price_gbp_mwh == 31.5

        # Explicit null: clear it.
        upsert_upstream_contract(session, _body(payment_terms=None))
        session.commit()
        assert session.get(UpstreamResourceContractRecord, CONTRACT_ID).payment_terms_json is None

        # Malformed declaration: refused before any write, row unchanged.
        with pytest.raises(ContractPaymentTermsRefusal):
            upsert_upstream_contract(
                session, _body(payment_terms={"schema_version": SENTINEL})
            )
        session.rollback()
        assert session.get(UpstreamResourceContractRecord, CONTRACT_ID).payment_terms_json is None


def test_capture_records_v2_for_declared_terms_and_v1_after_a_clear(
    tmp_path, monkeypatch
) -> None:
    url = _prepare_db(tmp_path, monkeypatch)
    document = _terms_document()
    captured_at = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)

    with _session(url) as session:
        upsert_upstream_contract(session, _body(payment_terms=document))
        session.commit()

        first = capture_upstream_contract_revision(
            session, CONTRACT_ID, recorded_by="trader-a", recorded_at_utc=captured_at
        )
        session.commit()
        assert first.outcome == CONTRACT_REVISION_CAPTURED
        assert first.revision.schema_version == CONTRACT_REVISION_SCHEMA_VERSION_V2
        assert json.loads(first.revision.snapshot_json)["payment_terms"] == document

        # An identical capture replays: no schema-only revision is allocated.
        replay = capture_upstream_contract_revision(
            session, CONTRACT_ID, recorded_by="trader-b", recorded_at_utc=captured_at
        )
        assert replay.outcome == CONTRACT_REVISION_ALREADY_CAPTURED
        assert replay.revision.revision_number == 1
        assert replay.revision.recorded_by == "trader-a"

        # Clearing back to "not stated" captures the v1 snapshot again as a new
        # revision, while the declared v2 row stays untouched.
        upsert_upstream_contract(session, _body(payment_terms=None))
        session.commit()
        cleared = capture_upstream_contract_revision(
            session, CONTRACT_ID, recorded_by="trader-a", recorded_at_utc=captured_at
        )
        session.commit()
        assert cleared.outcome == CONTRACT_REVISION_CAPTURED
        assert cleared.revision.revision_number == 2
        assert cleared.revision.schema_version == CONTRACT_REVISION_SCHEMA_VERSION
        assert json.loads(cleared.revision.snapshot_json)["payment_terms"] is None

        revisions = list_upstream_contract_revisions(session, CONTRACT_ID)
    assert [item["revision_number"] for item in revisions] == [1, 2]
    assert revisions[0]["snapshot"]["payment_terms"] == document
    assert revisions[1]["snapshot"]["payment_terms"] is None

"""Authenticated payment-term HTTP acceptance over the disposable PostgreSQL store.

`docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md` acceptance section:
`tests/integration/test_route_cost_contract_payment_terms.py` proves the
set/preserve/clear semantics against a throw-away SQLite fixture; this module
drives the same governed write and verified-read surfaces over the *real*
configured runtime store (CI: the disposable PostgreSQL 16 service) with the
*real* authenticated identities a deployment resolves - DB-backed
``X-Eurogas-Identity`` keys read through the configured store, never a
dependency override and never a fabricated ``request.state.actor``.

One focused journey per concern, each on its own UUID-labelled synthetic
contract and identity, all removed by the fixture after the test:

1. an ANALYST creates a labelled contract with no declared terms and the real
   store captures the unchanged v1 snapshot;
2. the ANALYST declares a strict ``contract-payment-terms/v1`` schedule with
   the fresh read token; the carrier stores the declaration's own canonical
   text and the store captures the declared v2 snapshot;
3. an OPERATOR metadata edit and an ANALYST economic edit both *omit* the
   field: the stored declaration is preserved, the carried revision stays v2,
   and the audit names the authenticated principal;
4. an OPERATOR clears explicitly with a fresh token: stored NULL, a new v1
   snapshot, and the declared evidence remains in its earlier revision;
5. a stale token is refused with the existing conflict code and changes
   nothing - row, revisions, hashes and audit rows are identical afterwards;
6. the revision list/detail reads replay v1 (no terms) and v2 (declared) and
   name the original recorder;
7. a VIEWER and an administration-only identity are refused by the existing
   role floor / commercial boundary without writing anything;
8. a malformed supplied declaration is refused sanitized before any write and
   the sentinel text never appears in the response.

Honest limits: this is authenticated HTTP acceptance of storage, authority and
captured read evidence, not trader acceptance, not a UI walkthrough, and it
asserts no resolved payable date or valuation. The module skips unless
``RUNTIME_STORE_DATABASE_URL`` is a PostgreSQL URL *and*
``EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST=1``, so collection without a
configured disposable store skips cleanly. It runs no migrations and must
never point at a developer's running desk database; CI runs it through
``scripts/ci/run_postgres_ci.sh``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.models import (
    AuditEventRecord,
    IdentityApiKeyRecord,
    IdentityPrincipalRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.route_cost.contract_revision import (
    CONTRACT_REVISION_SCHEMA_VERSION,
    CONTRACT_REVISION_SCHEMA_VERSION_V2,
)
from eurogas_nexus.domain.route_cost.payment_terms import ContractPaymentTerms

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql")
    or os.environ.get("EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST") != "1",
    reason=(
        "Requires a disposable PostgreSQL URL and"
        " EUROGAS_NEXUS_PAYMENT_TERMS_INTEGRATION_TEST=1; use run_postgres_ci.sh"
    ),
)

PUBLIC_TOKEN = "test-public-api-token"
CONTRACT_PATH = "/api/route-cost/upstream-contracts"

#: Untrusted text that must never be echoed by a refusal.
SENTINEL = "sentinel-acceptance-value-must-not-be-echoed"


@dataclass(frozen=True)
class _Actor:
    """One real DB-backed identity presented through its own release client."""

    principal_id: str
    role: str
    client: TestClient


@dataclass
class _AcceptanceStore:
    """The configured disposable store plus the synthetic rows this test wrote.

    Rows are tracked by the UUID identities the test allocates, so teardown
    removes exactly this test's fixtures - child tables first, because the
    revision table references the contract row - and nothing a human or an
    earlier job left in the store.
    """

    url: str
    engine: Engine
    contract_ids: list[str] = field(default_factory=list)
    principal_ids: list[str] = field(default_factory=list)

    def labelled_contract_id(self, label: str) -> str:
        contract_id = f"pt-accept-{label}-{uuid4().hex[:12]}"
        self.contract_ids.append(contract_id)
        return contract_id

    def actor(self, *, role: str, label: str, scopes: list[str] | None = None) -> _Actor:
        """Create a hashed identity key in the store and a release-profile client.

        The client authenticates with the deployment token plus the bearer, so
        the request resolves ``AuthenticatedPrincipal`` from the configured
        store exactly as a deployment would - no dependency override and no
        fabricated actor.
        """

        with Session(self.engine) as session:
            principal = create_identity_principal(
                session,
                name=f"pt-accept-{label}-{uuid4().hex[:10]}",
                display_name=f"PT acceptance {label}",
                role=role,
                data_scopes=scopes if scopes is not None else ["TTF"],
            )
            _key, bearer = create_identity_api_key(
                session, principal.principal_id, display_name=f"pt-accept-{label}"
            )
            session.commit()
            principal_id = principal.principal_id
        self.principal_ids.append(principal_id)
        client = TestClient(create_app(Settings(api_profile="release")))
        client.headers.update(
            {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        )
        return _Actor(principal_id=principal_id, role=role, client=client)

    def session(self) -> Session:
        return Session(self.engine)

    def cleanup(self) -> None:
        with Session(self.engine) as session:
            for contract_id in self.contract_ids:
                resource = f"upstream_contract:{contract_id}"[:128]
                session.query(AuditEventRecord).filter(
                    AuditEventRecord.resource == resource
                ).delete(synchronize_session=False)
                session.query(UpstreamContractRevisionRecord).filter(
                    UpstreamContractRevisionRecord.contract_id == contract_id
                ).delete(synchronize_session=False)
                session.query(UpstreamResourceContractRecord).filter(
                    UpstreamResourceContractRecord.contract_id == contract_id
                ).delete(synchronize_session=False)
            for principal_id in self.principal_ids:
                session.query(AuditEventRecord).filter(
                    AuditEventRecord.principal == principal_id
                ).delete(synchronize_session=False)
                session.query(IdentityApiKeyRecord).filter(
                    IdentityApiKeyRecord.principal_id == principal_id
                ).delete(synchronize_session=False)
                session.query(IdentityPrincipalRecord).filter(
                    IdentityPrincipalRecord.principal_id == principal_id
                ).delete(synchronize_session=False)
            session.commit()


@pytest.fixture()
def store() -> Iterator[_AcceptanceStore]:
    """Bind to the configured disposable store; clean up even when a test fails."""

    url = os.environ["RUNTIME_STORE_DATABASE_URL"]
    engine = create_engine(url, future=True)
    acceptance = _AcceptanceStore(url=url, engine=engine)
    try:
        yield acceptance
    finally:
        try:
            acceptance.cleanup()
        finally:
            engine.dispose()


def _body(contract_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_id": contract_id,
        "contract_name": f"PT acceptance fixture {contract_id}",
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
        "notes": "disposable PostgreSQL acceptance fixture (synthetic)",
    }
    payload.update(overrides)
    return payload


def _terms_document(**overrides: object) -> dict[str, object]:
    """One strict canonical declaration document."""

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


def _read_token(client: TestClient, contract_id: str) -> str:
    response = client.get(CONTRACT_PATH)
    assert response.status_code == 200, response.text
    row = next(
        item for item in response.json()["data"] if item["contract_id"] == contract_id
    )
    token = row.get("edit_token")
    assert isinstance(token, str), f"no edit_token on the stored read: {row!r}"
    assert token.startswith("sha256:")
    return token


def _stored_contract(acceptance: _AcceptanceStore, contract_id: str) -> dict:
    """Stored row plus evidence counts: an unchanged-state fingerprint."""

    with acceptance.session() as session:
        row = session.get(UpstreamResourceContractRecord, contract_id)
        assert row is not None, f"no stored contract for {contract_id!r}"
        revisions = (
            session.query(UpstreamContractRevisionRecord)
            .filter(UpstreamContractRevisionRecord.contract_id == contract_id)
            .order_by(UpstreamContractRevisionRecord.revision_number)
            .all()
        )
        audits = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == f"upstream_contract:{contract_id}")
            .count()
        )
        return {
            "persisted_row": {
                column.name: getattr(row, column.name)
                for column in UpstreamResourceContractRecord.__table__.columns
            },
            "payment_terms_json": row.payment_terms_json,
            "contract_name": row.contract_name,
            "contract_price_gbp_mwh": row.contract_price_gbp_mwh,
            "notes": row.notes,
            "revision_numbers": [item.revision_number for item in revisions],
            "revision_hashes": [item.content_hash for item in revisions],
            "revision_recorders": [item.recorded_by for item in revisions],
            "audits": audits,
        }


def _revision_list(client: TestClient, contract_id: str) -> list[dict]:
    response = client.get(f"{CONTRACT_PATH}/{contract_id}/revisions")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["source_references"] == ["runtime-postgresql"]
    data = payload["data"]
    assert data["revision_count"] == data["returned_count"] == len(data["revisions"])
    return data["revisions"]


def _contract_audits(acceptance: _AcceptanceStore, contract_id: str) -> list[AuditEventRecord]:
    with acceptance.session() as session:
        rows = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == f"upstream_contract:{contract_id}")
            .all()
        )
        session.expunge_all()
        return rows


def test_authenticated_set_preserve_clear_journey_on_the_disposable_store(
    store: _AcceptanceStore,
) -> None:
    contract_id = store.labelled_contract_id("journey")
    analyst = store.actor(role="ANALYST", label="journey-analyst")
    operator = store.actor(role="OPERATOR", label="journey-operator")
    document = _terms_document()

    # 1. The ANALYST creates the labelled contract with no declared terms: the
    #    real store captures the unchanged v1 snapshot, not a schema-only one.
    created = analyst.client.post(CONTRACT_PATH, json=_body(contract_id))
    assert created.status_code == 200, created.text
    created_data = created.json()["data"]
    assert created_data["write_outcome"] == "created"
    assert created_data["payment_terms"] is None
    assert created_data["latest_revision"]["revision_number"] == 1

    listed = _revision_list(analyst.client, contract_id)
    assert [item["schema_version"] for item in listed] == [CONTRACT_REVISION_SCHEMA_VERSION]
    assert listed[0]["snapshot"]["payment_terms"] is None
    assert listed[0]["recorded_by"] == analyst.principal_id

    # 2. The ANALYST declares the strict schedule with the fresh read token;
    #    the carrier stores the declaration's own canonical text, not a
    #    re-serialized echo, and the store captures the declared v2 snapshot.
    declared = analyst.client.post(
        CONTRACT_PATH,
        json=_body(
            contract_id,
            payment_terms=document,
            expected_edit_token=_read_token(analyst.client, contract_id),
        ),
    )
    assert declared.status_code == 200, declared.text
    declared_data = declared.json()["data"]
    assert declared_data["write_outcome"] == "economics_updated"
    assert declared_data["payment_terms"] == document
    assert declared_data["latest_revision"]["revision_number"] == 2
    assert _stored_contract(store, contract_id)["payment_terms_json"] == (
        _canonical_terms_text(document)
    )

    # 3. An OPERATOR metadata edit omits the field entirely: the stored
    #    declaration is preserved and the economics capture stays idempotent
    #    (no new revision), while the change is still audited.
    renamed = f"{contract_id} renamed"
    metadata_notes = "metadata-only acceptance edit"
    metadata = operator.client.post(
        CONTRACT_PATH,
        json=_body(
            contract_id,
            contract_name=renamed,
            notes=metadata_notes,
            expected_edit_token=_read_token(operator.client, contract_id),
        ),
    )
    assert metadata.status_code == 200, metadata.text
    metadata_data = metadata.json()["data"]
    assert metadata_data["write_outcome"] == "metadata_updated"
    assert metadata_data["payment_terms"] == document
    assert metadata_data["latest_revision"]["revision_number"] == 2
    assert _stored_contract(store, contract_id)["payment_terms_json"] == (
        _canonical_terms_text(document)
    )

    # 4. An ANALYST economic edit omits the field too: the new price is
    #    captured as a v2 snapshot that still carries the preserved terms.
    repriced = analyst.client.post(
        CONTRACT_PATH,
        json=_body(
            contract_id,
            contract_name=renamed,
            notes=metadata_notes,
            contract_price_gbp_mwh=31.5,
            expected_edit_token=_read_token(analyst.client, contract_id),
        ),
    )
    assert repriced.status_code == 200, repriced.text
    repriced_data = repriced.json()["data"]
    assert repriced_data["write_outcome"] == "economics_updated"
    assert repriced_data["payment_terms"] == document
    assert repriced_data["latest_revision"]["revision_number"] == 3
    listed = _revision_list(analyst.client, contract_id)
    assert [item["revision_number"] for item in listed] == [1, 2, 3]
    assert listed[2]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert listed[2]["snapshot"]["payment_terms"] == document
    assert listed[2]["snapshot"]["contract_price_gbp_mwh"] == "31.5"
    assert listed[2]["recorded_by"] == analyst.principal_id

    # 5. The OPERATOR clears explicitly with a fresh token: stored NULL, a new
    #    v1 snapshot captured, and the declared evidence stays in its revision.
    stale_token = _read_token(operator.client, contract_id)
    cleared = operator.client.post(
        CONTRACT_PATH,
        json=_body(
            contract_id,
            contract_name=renamed,
            notes=metadata_notes,
            contract_price_gbp_mwh=31.5,
            payment_terms=None,
            expected_edit_token=stale_token,
        ),
    )
    assert cleared.status_code == 200, cleared.text
    cleared_data = cleared.json()["data"]
    assert cleared_data["write_outcome"] == "economics_updated"
    assert cleared_data["payment_terms"] is None
    assert cleared_data["latest_revision"]["revision_number"] == 4
    fingerprint = _stored_contract(store, contract_id)
    assert fingerprint["payment_terms_json"] is None
    assert fingerprint["revision_numbers"] == [1, 2, 3, 4]

    # 6. The stale token is refused with the existing conflict code and writes
    #    nothing: row, revisions, hashes and audit rows are identical after.
    before_refusal = _stored_contract(store, contract_id)
    refused = analyst.client.post(
        CONTRACT_PATH,
        json=_body(
            contract_id,
            contract_price_gbp_mwh=99.5,
            payment_terms=document,
            expected_edit_token=stale_token,
        ),
    )
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "conflict"
    assert detail["code"] == "contract_edit_conflict"
    assert stale_token not in refused.text
    assert _stored_contract(store, contract_id) == before_refusal

    # 7. The verified reads replay the capture history: v1 (no terms), v2
    #    (declared), v2 (preserved), v1 (cleared), each naming its recorder.
    listed = _revision_list(analyst.client, contract_id)
    assert [item["revision_number"] for item in listed] == [1, 2, 3, 4]
    assert [item["schema_version"] for item in listed] == [
        CONTRACT_REVISION_SCHEMA_VERSION,
        CONTRACT_REVISION_SCHEMA_VERSION_V2,
        CONTRACT_REVISION_SCHEMA_VERSION_V2,
        CONTRACT_REVISION_SCHEMA_VERSION,
    ]
    assert [item["snapshot"]["payment_terms"] for item in listed] == [
        None,
        document,
        document,
        None,
    ]
    assert [item["recorded_by"] for item in listed] == [
        analyst.principal_id,
        analyst.principal_id,
        analyst.principal_id,
        operator.principal_id,
    ]
    detail_read = analyst.client.get(
        f"{CONTRACT_PATH}/{contract_id}/revisions/{listed[1]['contract_revision_id']}"
    )
    assert detail_read.status_code == 200, detail_read.text
    detail_data = detail_read.json()["data"]
    assert detail_data["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2
    assert detail_data["snapshot"]["payment_terms"] == document
    assert detail_data["recorded_by"] == analyst.principal_id

    # 8. Audit evidence: every accepted write and capture names the
    #    authenticated principal; the refused stale write added nothing, and
    #    the omitted fields never appear as changed.
    audits = _contract_audits(store, contract_id)
    upserts = [row for row in audits if row.action == "route_cost.contract.upsert"]
    captures = [
        row for row in audits if row.action == "route_cost.contract.capture_revision"
    ]
    assert sorted((row.outcome, row.principal) for row in upserts) == sorted(
        [
            ("created", analyst.principal_id),
            ("economics_updated", analyst.principal_id),
            ("metadata_updated", operator.principal_id),
            ("economics_updated", analyst.principal_id),
            ("economics_updated", operator.principal_id),
        ]
    )
    changed_fields_by_revision = {
        (row.outcome, row.after_summary["latest_revision_number"]): tuple(
            row.after_summary["changed_fields"]
        )
        for row in upserts
    }
    assert changed_fields_by_revision[("created", 1)] == ()
    assert changed_fields_by_revision[("economics_updated", 2)] == ("payment_terms_json",)
    assert changed_fields_by_revision[("metadata_updated", 2)] == (
        "contract_name",
        "notes",
    )
    assert changed_fields_by_revision[("economics_updated", 3)] == (
        "contract_price_gbp_mwh",
    )
    assert changed_fields_by_revision[("economics_updated", 4)] == ("payment_terms_json",)
    assert len(captures) == 4
    assert sorted(row.principal for row in captures) == sorted(
        [analyst.principal_id] * 3 + [operator.principal_id]
    )

    # The stored-contract read serves the cleared state and a token that is
    # current for the row the refusal left untouched.
    current = analyst.client.get(CONTRACT_PATH)
    assert current.status_code == 200, current.text
    current_row = next(
        item for item in current.json()["data"] if item["contract_id"] == contract_id
    )
    assert current_row["payment_terms"] is None
    assert current_row["edit_token"].startswith("sha256:")


def test_denied_identities_are_refused_without_any_write(store: _AcceptanceStore) -> None:
    """VIEWER keeps the role refusal; ADMIN-only keeps the commercial boundary."""

    contract_id = store.labelled_contract_id("denied")
    analyst = store.actor(role="ANALYST", label="denied-analyst")
    created = analyst.client.post(
        CONTRACT_PATH, json=_body(contract_id, payment_terms=_terms_document())
    )
    assert created.status_code == 200, created.text
    before = _stored_contract(store, contract_id)

    viewer = store.actor(role="VIEWER", label="denied-viewer")
    admin = store.actor(role="ADMIN", label="denied-admin", scopes=[])
    for actor, expected_error in (
        (viewer, "identity_role_forbidden"),
        (admin, "commercial_access_not_granted"),
    ):
        refused = actor.client.post(
            CONTRACT_PATH,
            json=_body(contract_id, contract_price_gbp_mwh=99.5, payment_terms=None),
        )
        assert refused.status_code == 403, (actor.role, refused.text)
        assert refused.json()["detail"]["error"] == expected_error

    # No refused attempt changed the row, its revisions or its audit trail.
    assert _stored_contract(store, contract_id) == before
    listed = _revision_list(analyst.client, contract_id)
    assert [item["revision_number"] for item in listed] == [1]
    assert listed[0]["schema_version"] == CONTRACT_REVISION_SCHEMA_VERSION_V2


def test_malformed_declaration_is_refused_sanitized_before_any_write(
    store: _AcceptanceStore,
) -> None:
    contract_id = store.labelled_contract_id("malformed")
    analyst = store.actor(role="ANALYST", label="malformed-analyst")
    created = analyst.client.post(CONTRACT_PATH, json=_body(contract_id))
    assert created.status_code == 200, created.text
    before = _stored_contract(store, contract_id)
    token = _read_token(analyst.client, contract_id)

    unknown_field = {**_terms_document(), "unexpected": SENTINEL}
    bad_value = _terms_document()
    bad_value["items"][0]["flow_direction"] = SENTINEL  # type: ignore[index]

    for malformed, expected_code in (
        (unknown_field, "canonical_field_set_mismatch"),
        (bad_value, "canonical_flow_direction_unknown"),
        (SENTINEL, "canonical_not_mapping"),
    ):
        refused = analyst.client.post(
            CONTRACT_PATH,
            json=_body(
                contract_id,
                contract_price_gbp_mwh=99.5,
                payment_terms=malformed,
                expected_edit_token=token,
            ),
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["detail"]["error"] == expected_code
        assert SENTINEL not in refused.text

    # Every refused request wrote nothing, including nothing to the carrier.
    assert _stored_contract(store, contract_id) == before

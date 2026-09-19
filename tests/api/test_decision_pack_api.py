"""The decision pack as the API serves it: one case, composed for signature.

The pack rides on the single-case read, so these tests check the two things a reviewer depends on:
that the pack is *of this case* (its evidence, its record, its audit trail) and that what it cannot
verify is reported rather than smoothed over - an evidence reference whose snapshot is not on record
is the case in point.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _prepare(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "decision-pack.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _identity(database_url: str, *, name: str, role: str) -> str:
    with Session(create_engine(database_url, future=True)) as session:
        row = create_identity_principal(
            session,
            name=name,
            display_name=name.title(),
            role=role,
            data_scopes=[],
        )
        _key, bearer = create_identity_api_key(
            session, row.principal_id, display_name="decision-pack-test"
        )
        session.commit()
    return bearer


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def _open_case_with_evidence(client, analyst, *, snapshot_id: str | None) -> str:
    case_id = client.post(
        "/api/decision-cases",
        headers=_headers(analyst),
        json={
            "objective": "Cover tomorrow's NBP balance.",
            "gas_day": "2026-09-15",
            "delivery_product": "day-ahead",
            "hub_id": "NBP",
        },
    ).json()["data"]["case_id"]
    body: dict[str, object] = {
        "kind": "ROUTE_RECOMMENDATION",
        "ref": "route-rec-9",
        "label": "NBP recommendation",
        "as_of_utc": "2026-09-15T06:00:00+00:00",
    }
    if snapshot_id:
        body["snapshot_id"] = snapshot_id
    attached = client.post(
        f"/api/decision-cases/{case_id}/evidence",
        headers=_headers(analyst),
        json=body,
    )
    assert attached.status_code == 200, attached.text
    return case_id


def test_the_pack_travels_with_the_case_and_cites_its_own_trail(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    analyst = _identity(database_url, name="pack-analyst", role="ANALYST")
    reviewer = _identity(database_url, name="pack-reviewer", role="REVIEWER")
    client = TestClient(create_app(Settings(api_profile="release")))

    case_id = _open_case_with_evidence(client, analyst, snapshot_id=None)
    recorded = client.post(
        f"/api/decision-cases/{case_id}/decisions",
        headers=_headers(reviewer),
        json={"outcome": "accepted", "note": "Capacity confirmed."},
    )
    assert recorded.status_code == 200

    payload = client.get(
        f"/api/decision-cases/{case_id}", headers=_headers(analyst)
    ).json()["data"]
    pack = payload["pack"]

    assert pack["pack_version"] == "decision-pack-1"
    assert pack["case_id"] == case_id
    assert pack["context"]["gas_day"] == "2026-09-15"
    assert pack["decision"]["actor"] == "pack-reviewer"
    assert pack["signable"] is True
    # The case's own acts, recorded against it, are part of the artefact.
    assert pack["audit"]["resource"] == f"decision_case:{case_id}"
    assert "decision_case_create" in {row["action"] for row in pack["audit"]["events"]}
    assert "decision_case_record" in {row["action"] for row in pack["audit"]["events"]}
    assert pack["content_hash"].startswith("sha256:")

    # The pack is composed from the same case the read returns, not a second opinion about it.
    assert pack["evidence"] == [
        {
            "kind": "ROUTE_RECOMMENDATION",
            "ref": "route-rec-9",
            "label": "NBP recommendation",
            "as_of_utc": "2026-09-15T06:00:00+00:00",
            "snapshot_id": None,
            "snapshot_resolvable": None,
        }
    ]


def test_the_pack_reports_an_evidence_reference_whose_snapshot_is_not_on_record(
    tmp_path, monkeypatch
) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    analyst = _identity(database_url, name="pack-analyst", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    case_id = _open_case_with_evidence(client, analyst, snapshot_id="snap-not-recorded")

    pack = client.get(f"/api/decision-cases/{case_id}", headers=_headers(analyst)).json()["data"][
        "pack"
    ]

    assert pack["evidence"][0]["snapshot_resolvable"] is False
    assert "DECISION_PACK_SNAPSHOT_UNRESOLVED" in pack["blockers"]
    # The case itself remains decidable on its own terms: the pack reports a citation it could not
    # resolve, it does not re-decide the case.
    assert pack["decision"] is None
    assert pack["signable"] is False


def test_an_undecided_case_packs_as_unsigned(tmp_path, monkeypatch) -> None:
    database_url = _prepare(tmp_path, monkeypatch)
    analyst = _identity(database_url, name="pack-analyst", role="ANALYST")
    client = TestClient(create_app(Settings(api_profile="release")))

    case_id = _open_case_with_evidence(client, analyst, snapshot_id=None)

    pack = client.get(f"/api/decision-cases/{case_id}", headers=_headers(analyst)).json()["data"][
        "pack"
    ]

    assert pack["signable"] is False
    assert "DECISION_PACK_DECISION_NOT_RECORDED" in pack["blockers"]
    assert pack["signature_note"]


def test_an_unknown_case_is_not_packed(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.get("/api/decision-cases/case-does-not-exist")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "unknown_decision_case"


def test_without_a_runtime_database_the_read_states_that_and_packs_nothing(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    client = TestClient(create_app(Settings(api_profile="development")))

    payload = client.get("/api/decision-cases/case-any").json()

    assert payload["data"] is None
    assert "RUNTIME_DB_NOT_CONFIGURED" in payload["meta"]["warnings"]
    assert payload.get("pack") is None

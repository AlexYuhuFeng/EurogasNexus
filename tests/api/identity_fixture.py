"""Explicit persisted callers for business tests that require private ownership."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)


def install_named_client(database_url, monkeypatch):
    with Session(create_engine(database_url)) as session:
        owner = create_identity_principal(
            session,
            name="fixture-owner",
            display_name="Fixture owner",
            role="ANALYST",
            data_scopes=["*"],
        )
        _, bearer = create_identity_api_key(session, owner.principal_id, scopes=["*"])
        owner_id = owner.principal_id
        session.commit()
    original_init = TestClient.__init__

    def initialize(self, app, *args, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        if not any(
            key.lower() in {"x-eurogas-identity", "authorization", "x-eurogas-oidc-access-token"}
            for key in headers
        ):
            headers["X-Eurogas-Identity"] = bearer
        headers.setdefault("X-Eurogas-Api-Key", "test-public-api-token")
        original_init(self, app, *args, headers=headers, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", initialize)
    return owner_id

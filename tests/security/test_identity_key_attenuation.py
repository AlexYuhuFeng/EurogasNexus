"""Issued bearer scopes constrain current principal grants on every request."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    authenticate_identity_bearer,
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.identity import principal_allows_source_family


@pytest.mark.parametrize(
    ("grants", "key_scopes", "expected"),
    [
        (["EEX"], [], ()),
        (["EEX"], ["Trayport"], ()),
        (["EEX", "Trayport"], [" eex "], ("EEX",)),
        (["*"], ["EEX"], ("EEX",)),
        (["EEX"], ["*"], ("EEX",)),
        (["*"], ["*"], ("*",)),
        ([], ["*"], ()),
        (["*"], [], ()),
    ],
)
def test_bearer_cannot_exceed_key_or_principal(grants, key_scopes, expected):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = create_identity_principal(
            session,
            name="limited-key",
            display_name="Limited key",
            role="ANALYST",
            data_scopes=grants,
        )
        _, bearer = create_identity_api_key(
            session,
            row.principal_id,
            scopes=key_scopes,
        )
        identity = authenticate_identity_bearer(session, bearer)
        assert identity.data_scopes == expected
        assert principal_allows_source_family(identity, "ENTSOG")
        assert principal_allows_source_family(identity, "EEX_Sim") == (
            "EEX" in expected or "*" in expected
        )
        # An already-issued key cannot retain a grant withdrawn from its owner.
        row.data_scopes = []
        session.flush()
        identity = authenticate_identity_bearer(session, bearer)
        assert identity.data_scopes == ()
        assert not principal_allows_source_family(identity, "EEX_Sim")
    engine.dispose()

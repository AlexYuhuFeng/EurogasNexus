"""A data-subject access export finds the person's records and withholds secrets."""

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)


def test_export_lists_records_and_withholds_secrets(tmp_path, monkeypatch):
    import scripts.ops.personal_data_export as script

    url = f"sqlite+pysqlite:///{(tmp_path / 'dsar.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = create_identity_principal(
            session, name="jsmith", display_name="J Smith", role="ANALYST", data_scopes=[]
        )
        create_identity_api_key(session, row.principal_id, display_name="laptop")
        principal_id = row.principal_id
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    out = tmp_path / "dsar.json"
    assert script.main(["--principal-id", principal_id, "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    tables = report["tables"]
    assert "identity_principals" in tables and "identity_api_keys" in tables
    key = tables["identity_api_keys"][0]
    assert all(v == "[withheld]" for k, v in key.items() if "hash" in k)

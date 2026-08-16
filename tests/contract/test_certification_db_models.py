"""Provider certification DB model contract tests."""

from eurogas_nexus.db.models import ProviderCertificationRecord
from eurogas_nexus.db.registry import list_required_tables


def test_provider_certifications_is_a_required_table() -> None:
    assert "provider_certifications" in set(list_required_tables())


def test_certification_model_fields_match_gate_contract() -> None:
    columns = {column.name for column in ProviderCertificationRecord.__table__.columns}

    assert {
        "certification_id",
        "source_system",
        "stage",
        "checks",
        "evidence",
        "evaluated_by",
        "note",
        "evaluated_at_utc",
    } <= columns
    assert ProviderCertificationRecord.__tablename__ == "provider_certifications"

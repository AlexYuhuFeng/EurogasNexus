"""Governance foundation contract tests (DB-free)."""



# --- EntitlementDecision -----------------------------------------------------

def test_entitlement_decision_defaults_to_denied() -> None:
    from eurogas_nexus.governance import EntitlementDecision

    decision = EntitlementDecision()
    assert decision.granted is False
    assert decision.human_review_required is True


def test_entitlement_decision_can_be_granted() -> None:
    from eurogas_nexus.governance import EntitlementDecision, EntitlementScope

    decision = EntitlementDecision(
        granted=True,
        scope=EntitlementScope.INTERNAL_RESEARCH,
        source_system="test-source",
    )
    assert decision.granted is True
    assert decision.scope == EntitlementScope.INTERNAL_RESEARCH


# --- entitlement_check -------------------------------------------------------

def test_entitlement_check_fails_closed_for_unknown_source() -> None:
    from eurogas_nexus.governance import entitlement_check

    decision = entitlement_check("unknown-vendor-api")
    assert decision.granted is False
    assert "not in the known-entitled set" in decision.reason


def test_entitlement_check_passes_for_known_source() -> None:
    from eurogas_nexus.governance import entitlement_check

    known = frozenset({"entsog-tp", "gie-alsi"})
    decision = entitlement_check("entsog-tp", known_entitled_systems=known)
    assert decision.granted is True


def test_entitlement_check_preserves_source_info() -> None:
    from eurogas_nexus.governance import entitlement_check

    decision = entitlement_check("eex-power", source_dataset="agora-hourly")
    assert decision.source_system == "eex-power"
    assert decision.source_dataset == "agora-hourly"


# --- ExportDecision / ExportEvaluation ---------------------------------------

def test_export_evaluation_defaults_to_unknown() -> None:
    from eurogas_nexus.governance import ExportDecision, ExportEvaluation

    evaluation = ExportEvaluation()
    assert evaluation.decision == ExportDecision.UNKNOWN
    assert evaluation.human_review_required is True


# --- export_check ------------------------------------------------------------

def test_export_check_fails_closed_for_unknown_scope() -> None:
    from eurogas_nexus.governance import EntitlementScope, export_check

    evaluation = export_check(EntitlementScope.UNKNOWN)
    assert evaluation.decision == "denied"
    assert "fail-closed" in evaluation.reason


def test_export_check_restricts_internal_research() -> None:
    from eurogas_nexus.governance import EntitlementScope, export_check

    evaluation = export_check(EntitlementScope.INTERNAL_RESEARCH)
    assert evaluation.decision == "restricted"
    assert "no-redistribution" in evaluation.restrictions


def test_export_check_allows_public_with_clearance() -> None:
    from eurogas_nexus.governance import EntitlementScope, export_check

    evaluation = export_check(EntitlementScope.PUBLIC, allow_public_export=True)
    assert evaluation.decision == "allowed"


def test_export_check_restricts_public_without_clearance() -> None:
    from eurogas_nexus.governance import EntitlementScope, export_check

    evaluation = export_check(EntitlementScope.PUBLIC, allow_public_export=False)
    assert evaluation.decision == "restricted"


# --- AuditEvent --------------------------------------------------------------

def test_audit_event_has_required_fields() -> None:
    from eurogas_nexus.governance import AuditEvent, AuditSeverity

    event = AuditEvent(
        event_type="entitlement.check",
        severity=AuditSeverity.WARNING,
        principal="operator",
        action="check_entitlement",
        resource="ice-ocm",
        outcome="denied",
    )
    assert event.event_type == "entitlement.check"
    assert event.severity == AuditSeverity.WARNING
    assert event.principal == "operator"
    assert event.outcome == "denied"
    assert event.event_id  # auto-generated


def test_audit_event_defaults() -> None:
    from eurogas_nexus.governance import AuditEvent, AuditSeverity

    event = AuditEvent()
    assert event.event_type == "governance.action"
    assert event.severity == AuditSeverity.INFO
    assert event.human_review_required is True


def test_audit_event_id_is_unique() -> None:
    from eurogas_nexus.governance import AuditEvent

    e1 = AuditEvent()
    e2 = AuditEvent()
    assert e1.event_id != e2.event_id


# --- AuditSeverity -----------------------------------------------------------

def test_audit_severity_values() -> None:
    from eurogas_nexus.governance import AuditSeverity

    assert AuditSeverity.INFO.value == "info"
    assert AuditSeverity.WARNING.value == "warning"
    assert AuditSeverity.ERROR.value == "error"
    assert AuditSeverity.CRITICAL.value == "critical"


# --- EntitlementScope --------------------------------------------------------

def test_entitlement_scope_values() -> None:
    from eurogas_nexus.governance import EntitlementScope

    assert EntitlementScope.INTERNAL_RESEARCH.value == "internal-research"
    assert EntitlementScope.PUBLIC.value == "public"
    assert EntitlementScope.LICENSED.value == "licensed"
    assert EntitlementScope.UNKNOWN.value == "unknown"


# --- Import safety -----------------------------------------------------------

def test_governance_package_is_import_safe() -> None:
    """Governance package must not import web, client, or vendor modules."""
    import eurogas_nexus.governance as gov

    assert gov.__name__ == "eurogas_nexus.governance"


def test_runtime_store_contracts_are_import_safe() -> None:
    """Runtime store contracts must not import web, client, or vendor modules."""
    import eurogas_nexus.runtime_store.contracts as c

    assert c.__name__ == "eurogas_nexus.runtime_store.contracts"

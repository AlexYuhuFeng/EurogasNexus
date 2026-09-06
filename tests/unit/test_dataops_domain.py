"""CR-09 data-operations domain tests (pure, deterministic)."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from eurogas_nexus.domain.dataops.contracts import (
    CircuitState,
    EntitlementOutcome,
    FailureCategory,
    FreshnessState,
    QualityResult,
    QualitySeverity,
    RetryPolicy,
    SourceClass,
)
from eurogas_nexus.domain.dataops.entitlement import (
    derived_result_access,
    filter_rows_for_principal,
)
from eurogas_nexus.domain.dataops.freshness import (
    FreshnessEvidence,
    evaluate_source_freshness,
    ingestion_lag_seconds,
    pipeline_lag_seconds,
    source_age_seconds,
)
from eurogas_nexus.domain.dataops.quality import (
    make_issue,
    summarize_quality,
    validate_market_row,
)
from eurogas_nexus.domain.dataops.registry import (
    definition_for_provider,
    definition_for_source,
    schedulable_definitions,
    source_definitions,
)
from eurogas_nexus.domain.dataops.retry import (
    circuit_after_failure,
    circuit_after_success,
    classify_failure,
    recovery_probe_due,
    retry_decision,
)
from eurogas_nexus.domain.dataops.schedule import (
    next_scheduled_instant,
    update_expected,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def test_registry_is_canonical_and_classified() -> None:
    definitions = source_definitions()

    assert len(definitions) == 24
    assert definition_for_source("src-eex") is not None
    assert definition_for_provider("ENTSOG") is not None
    assert definition_for_source("src-ice-ocm").source_class == SourceClass.EXCHANGE
    assert definition_for_source("src-trayport").source_class == SourceClass.BROKER
    assert definition_for_source("src-eex-sim").source_class == SourceClass.SIMULATED
    assert definition_for_source("src-ecb").source_class == SourceClass.PUBLIC
    assert {d.source_id for d in schedulable_definitions()} == {
        "src-ecb",
        "src-entsog",
        "src-gie",
    }


def test_interval_schedule_is_anchored_and_deterministic() -> None:
    entsog = definition_for_provider("ENTSOG")
    activated = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)
    first = next_scheduled_instant(entsog, activated_at=activated, after=activated)
    second = next_scheduled_instant(entsog, activated_at=activated, after=first)

    assert first == activated + timedelta(hours=1)
    assert second == activated + timedelta(hours=2)


def test_daily_schedule_respects_source_timezone_and_dst() -> None:
    ecb = definition_for_provider("ECB")
    activated = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    next_run = next_scheduled_instant(ecb, activated_at=activated, after=activated)

    # 16:10 Europe/Berlin in January is 15:10 UTC.
    assert next_run == datetime(2026, 1, 5, 15, 10, tzinfo=UTC)


def test_ecb_is_not_expected_on_weekend() -> None:
    ecb = definition_for_provider("ECB")
    saturday = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    monday = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)

    assert update_expected(ecb, now_utc=saturday) is False
    assert update_expected(ecb, now_utc=monday) is True


def test_freshness_ladder_is_deterministic() -> None:
    definition = definition_for_provider("ENTSOG")

    fresh = evaluate_source_freshness(
        definition,
        FreshnessEvidence(observed_at_utc=NOW - timedelta(minutes=30)),
        now_utc=NOW,
    )
    assert fresh.state == FreshnessState.FRESH

    late = evaluate_source_freshness(
        definition,
        FreshnessEvidence(observed_at_utc=NOW - timedelta(minutes=90)),
        now_utc=NOW,
    )
    assert late.state == FreshnessState.LATE

    stale = evaluate_source_freshness(
        definition,
        FreshnessEvidence(observed_at_utc=NOW - timedelta(hours=7)),
        now_utc=NOW,
    )
    assert stale.state == FreshnessState.STALE

    missing = evaluate_source_freshness(
        definition,
        FreshnessEvidence(),
        now_utc=NOW,
    )
    assert missing.state == FreshnessState.MISSING

    restricted = evaluate_source_freshness(
        definition,
        FreshnessEvidence(
            observed_at_utc=NOW - timedelta(minutes=1),
            access_granted=False,
        ),
        now_utc=NOW,
    )
    assert restricted.state == FreshnessState.RESTRICTED


def test_weekend_freshness_is_not_expected_instead_of_stale() -> None:
    ecb = definition_for_provider("ECB")
    saturday = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    evidence = FreshnessEvidence(
        observed_at_utc=saturday - timedelta(days=3),
        last_success_at_utc=saturday - timedelta(days=3),
    )

    evaluation = evaluate_source_freshness(ecb, evidence, now_utc=saturday)

    assert evaluation.state == FreshnessState.NOT_EXPECTED


def test_latency_decomposition() -> None:
    assert source_age_seconds(NOW - timedelta(seconds=5), now_utc=NOW) == 5.0
    assert ingestion_lag_seconds(NOW - timedelta(seconds=9), NOW - timedelta(seconds=2)) == 7.0
    assert pipeline_lag_seconds(NOW - timedelta(seconds=3), NOW) == 3.0
    assert ingestion_lag_seconds(None, NOW) is None


def test_failure_classification_never_retries_terminal_categories() -> None:
    auth = classify_failure(error=None, status_code=401)
    entitlement = classify_failure(error=None, message="entitlement denied")
    schema = classify_failure(error=None, message="provider schema changed")
    configuration = classify_failure(error=None, message="configuration error")

    assert auth.category == FailureCategory.AUTHENTICATION
    assert auth.retryable is False
    assert entitlement.category == FailureCategory.ENTITLEMENT
    assert entitlement.retryable is False
    assert schema.category == FailureCategory.SCHEMA_CHANGED
    assert schema.retryable is False
    assert configuration.category == FailureCategory.CONFIGURATION
    assert configuration.retryable is False


def test_retry_decision_backs_off_with_bounded_jitter() -> None:
    classification = classify_failure(error=None, status_code=429)
    policy = RetryPolicy(retry_max=3, backoff_seconds=10, max_delay_seconds=60)

    decision = retry_decision(
        classification,
        attempt=0,
        policy=policy,
        retry_after_seconds=7.0,
        rng=random.Random(1),
    )
    assert decision.retry is True
    assert decision.delay_seconds == 7.0

    terminal = retry_decision(
        classify_failure(error=None, status_code=401),
        attempt=0,
        policy=policy,
        rng=random.Random(1),
    )
    assert terminal.retry is False


def test_circuit_opens_and_recovers() -> None:
    from eurogas_nexus.domain.dataops.contracts import CircuitPolicy

    policy = CircuitPolicy(degraded_after_failures=3, open_after_failures=6)
    state = CircuitState.HEALTHY
    failures = 0
    for _ in range(5):
        state, failures = circuit_after_failure(state, failures, policy=policy)
    assert state == CircuitState.DEGRADED
    state, failures = circuit_after_failure(state, failures, policy=policy)
    assert state == CircuitState.OPEN_CIRCUIT
    assert recovery_probe_due(
        state=state,
        opened_at_utc=NOW - timedelta(minutes=20),
        now_utc=NOW,
        policy=policy,
    )
    state, failures = circuit_after_success(state)
    assert state == CircuitState.HEALTHY
    assert failures == 0


def test_quality_summary_and_issues_are_structured() -> None:
    issues = [
        make_issue("OUTLIER", QualitySeverity.WARNING, field="price"),
        make_issue("NEGATIVE_VALUE", QualitySeverity.ERROR, field="price"),
    ]
    summary = summarize_quality(issues)

    assert summary.result == QualityResult.FAILED
    assert summary.error_count == 1
    assert summary.warning_count == 1
    assert issues[0].quality_code == "OUTLIER"

    clean = summarize_quality([])
    assert clean.result == QualityResult.PASSED


def test_market_row_validator_never_deletes_outliers() -> None:
    issues = validate_market_row(
        {
            "price": 6000.0,
            "unit": "EUR/MWh",
            "currency": "EUR",
            "period_start_utc": NOW,
            "period_end_utc": NOW + timedelta(days=1),
            "source_system": "EEX",
        },
        observation_reference="obs-1",
    )

    codes = {issue.quality_code for issue in issues}
    assert "OUTLIER" in codes
    assert all(
        issue.severity != QualitySeverity.ERROR or issue.quality_code != "OUTLIER"
        for issue in issues
    )


def test_principal_matrix_filters_rows_and_derived_results() -> None:
    public_only = AuthenticatedPrincipal(
        principal_id="public-only",
        name="public",
        principal_type="USER",
        role="VIEWER",
        status="ACTIVE",
        data_scopes=("ENTSOG",),
    )
    eex_allowed = AuthenticatedPrincipal(
        principal_id="eex",
        name="eex",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=("EEX",),
    )
    operator = AuthenticatedPrincipal(
        principal_id="operator",
        name="operator",
        principal_type="SERVICE",
        role="OPERATOR",
        status="ACTIVE",
        data_scopes=("*",),
    )
    rows = [
        {"observation_id": "a", "source_system": "ENTSOG"},
        {"observation_id": "b", "source_system": "EEX"},
        {"observation_id": "c", "source_system": "ICIS"},
    ]

    assert [row["observation_id"] for row in filter_rows_for_principal(public_only, rows)] == ["a"]
    assert [row["observation_id"] for row in filter_rows_for_principal(eex_allowed, rows)] == [
        "a",
        "b",
    ]
    assert len(filter_rows_for_principal(operator, rows)) == 3

    assert derived_result_access(public_only, ["ENTSOG"]).outcome == EntitlementOutcome.ALLOWED
    denied = derived_result_access(public_only, ["ENTSOG", "EEX"])
    assert denied.outcome == EntitlementOutcome.DENIED
    assert denied.blocked_sources == ("EEX",)

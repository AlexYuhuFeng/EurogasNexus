"""Live validation certifies only what a live sample showed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "certify_public_source.py"
_spec = importlib.util.spec_from_file_location("certify_public_source", SCRIPT)
certify = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = certify  # dataclasses resolve their module by name
_spec.loader.exec_module(certify)


def _check(**values):
    return certify.DatasetCheck("gie:AGSI", **values)


def test_a_clean_sample_reaches_live_validated_with_both_required_checks():
    stage, checks = certify.decide(
        [_check(records=100, normalised=100)], credential_checked=True
    )
    assert stage == "live_validated"
    assert {"simulated_shape_match", "live_sample_validation", "credential_verified"} <= set(checks)


def test_an_empty_or_failed_sample_certifies_nothing():
    assert certify.decide([_check()], credential_checked=False) == ("configured", [])
    failed = _check(records=10, normalised=10, error="GieTransportError: 401")
    assert certify.decide([failed], credential_checked=False) == ("configured", [])
    assert certify.decide([], credential_checked=True) == ("configured", [])


def test_a_sample_the_normaliser_rejects_stops_at_connection_verified():
    stage, checks = certify.decide(
        [_check(records=100, normalised=40)], credential_checked=True
    )
    assert stage == "connection_verified" and "live_sample_validation" not in checks


def test_a_missing_expected_field_fails_the_shape_check():
    stage, checks = certify.decide(
        [_check(records=100, normalised=100, missing_fields=["gasDayStart"])],
        credential_checked=True,
    )
    assert stage == "connection_verified" and "simulated_shape_match" not in checks


def test_one_bad_dataset_holds_back_the_whole_source():
    good, bad = _check(records=100, normalised=100), _check(records=100, normalised=0)
    assert certify.decide([good, bad], credential_checked=True)[0] == "connection_verified"


def test_a_zero_flow_is_a_value_and_a_blank_is_a_placeholder():
    assert certify._has_value(0) and certify._has_value("0") and certify._has_value(12.5)
    assert not certify._has_value(None) and not certify._has_value("  ")


def test_missing_reports_only_fields_absent_from_every_record():
    records = [{"a": 1, "b": None}, {"a": 2}]
    assert certify._missing(records, ("a", "b", "c")) == ["c"]

#!/usr/bin/env python
"""Bounded installed-wheel acceptance for the shared Python SDK.

This helper exists for one question: *does the wheel we would ship import and
behave correctly when it is the only SDK on the process path?* It deliberately
does not trust a source checkout, a ``PYTHONPATH``, or an already-installed
editable package.

What it does
------------
1. Requires a full 40-hex expected commit, binds it to local ``git rev-parse
   HEAD`` (argv, no shell, captured output), and refuses a dirty tracked worktree
   before wheel capture; untracked and ignored outputs remain allowed.
2. Validates the explicit paths given on the command line. The smoke working
   directory and the isolated venv must be outside the checkout, and the single
   wheel must contain both ``eurogas_nexus`` and ``eurogas_nexus_sdk``.
3. Asks the isolated venv interpreter for its own ``sys.prefix``/``purelib`` and
   asserts the installed SDK file is inside that venv and not inside the source
   checkout.
4. Starts the *backend* from source on an ephemeral loopback port, because the
   customer wheel contains the shared product packages but not the ``apps/``
   deployment wrappers. The SDK/examples run in a separate process from a temp
   directory, with isolated Python ``-I``, using only the installed wheel.
5. Runs a stdlib smoke (every SDK module imported with ``pkgutil``, stable
   typed missing-field errors, and a synthetic normalized-market evidence
   contract) and the existing synthetic economics example (six actual HTTP
   cases: three capacity, one capacity refusal, one LNG and one LNG refusal).
   Financial arithmetic stays in the backend/example; this helper never
   recomputes it.
6. Writes one JSON record with only non-secret fields and terminates the child
   process it started in ``finally``. It never stops a process by port or PID
   discovery.

Failure output is intentionally narrow: a stage and a stable code. Raw child
stdout/stderr, HTTP response bodies, environment contents and exception text are
never emitted, because those can contain caller values or credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "installed-sdk-acceptance/v1"
HEALTH_TIMEOUT_SECONDS = 30.0
SMOKE_TIMEOUT_SECONDS = 120.0
GIT_TIMEOUT_SECONDS = 15.0
EXPECTED_HTTP_CASE_COUNT = 6
EXPECTED_MARKET_EVIDENCE_FIELD_COUNT = 18
EXPECTED_MARKET_CONTRACT_CASE_COUNT = 6
EXPECTED_CHECK_IDS = frozenset(
    {
        "capacity-23h",
        "capacity-25h",
        "capacity-pence-24h",
        "capacity-refusal-inconsistent-billed-energy",
        "lng-golden",
        "lng-refusal-energy-conservation",
    }
)
_SOURCE_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+!_-]{0,79}$")
GitRunner = Callable[[Path, tuple[str, ...]], subprocess.CompletedProcess[str]]

# Only operating-system plumbing is inherited. Ambient credentials, proxies,
# Python path overrides and application settings are deliberately excluded.
_INHERITED_ENV_KEYS = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "PATHEXT",
        "COMSPEC",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_ARCHITEW6432",
        "OS",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)


class AcceptanceFailure(RuntimeError):
    """A controlled failure carrying only a stage and a stable code."""

    def __init__(self, stage: str, code: str) -> None:
        """Record the failing acceptance stage without any raw detail."""

        self.stage = stage
        self.code = code
        super().__init__(f"{stage}: {code}")


def _check(condition: bool, stage: str, code: str) -> None:
    """Raise one stable acceptance failure when a condition is false."""

    if not condition:
        raise AcceptanceFailure(stage, code)


def _base_env() -> dict[str, str]:
    """Return OS plumbing only, never ambient application configuration."""

    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _INHERITED_ENV_KEYS
    }


def _run_git(
    checkout_root: Path,
    arguments: tuple[str, ...],
    *,
    git_runner: GitRunner | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one local git command without a shell, never exposing its output."""

    if git_runner is not None:
        return git_runner(checkout_root, arguments)
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=checkout_root,
            env=_base_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise AcceptanceFailure("source", "git_unavailable") from None


def _bind_source_commit(
    checkout_root: Path,
    expected_commit: str,
    *,
    git_runner: GitRunner | None = None,
) -> str:
    """Require the caller's full commit id to equal the actual checkout HEAD."""

    expected = expected_commit.lower()
    _check(
        _SOURCE_COMMIT_RE.fullmatch(expected) is not None,
        "configuration",
        "source_commit_invalid",
    )
    completed = _run_git(
        checkout_root, ("rev-parse", "HEAD"), git_runner=git_runner
    )
    _check(
        completed.returncode == 0,
        "source",
        "source_commit_unavailable",
    )
    actual = completed.stdout.strip().lower()
    _check(
        _SOURCE_COMMIT_RE.fullmatch(actual) is not None,
        "source",
        "source_commit_invalid_response",
    )
    _check(actual == expected, "source", "source_commit_mismatch")
    return actual


def _require_clean_tracked_worktree(
    checkout_root: Path,
    *,
    git_runner: GitRunner | None = None,
) -> None:
    """Refuse tracked changes before wheel capture; untracked/ignored files stay allowed."""

    completed = _run_git(
        checkout_root,
        ("status", "--porcelain=v1", "--untracked-files=no"),
        git_runner=git_runner,
    )
    _check(completed.returncode == 0, "source", "git_status_unavailable")
    _check(
        not completed.stdout.strip(),
        "source",
        "tracked_worktree_dirty",
    )


def _resolve_existing_dir(value: str, label: str) -> Path:
    """Resolve one explicit directory argument or fail with a safe code."""

    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise AcceptanceFailure("configuration", f"{label}_not_found") from None
    _check(path.is_dir(), "configuration", f"{label}_not_directory")
    return path


def _validate_work_root(checkout_root: Path, work_root: str) -> Path:
    """Reject a smoke working root that would live inside the checkout.

    The isolated smoke must be able to prove that neither ``cwd`` nor an
    accidental relative import supplies the SDK. A temp root inside the source
    tree would make that proof ambiguous.
    """

    try:
        candidate = Path(work_root).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        raise AcceptanceFailure("configuration", "work_dir_invalid") from None
    if candidate == checkout_root or candidate.is_relative_to(checkout_root):
        raise AcceptanceFailure("configuration", "work_dir_inside_checkout")
    return candidate


def _find_single_wheel(wheel_dir: Path) -> Path:
    """Return the one built wheel, refusing missing or ambiguous inputs."""

    try:
        wheels = sorted(
            path for path in wheel_dir.iterdir() if path.is_file() and path.suffix == ".whl"
        )
    except OSError:
        raise AcceptanceFailure("wheel", "wheel_directory_unreadable") from None
    _check(len(wheels) == 1, "wheel", "expected_exactly_one_wheel")
    try:
        wheel = wheels[0].resolve(strict=True)
    except (OSError, RuntimeError):
        raise AcceptanceFailure("wheel", "wheel_unreadable") from None
    _check(wheel.is_relative_to(wheel_dir), "wheel", "wheel_path_escaped_directory")
    _check(wheel.name.startswith("eurogas_nexus-"), "wheel", "wrong_distribution")
    return wheel


def _wheel_sha256(wheel: Path) -> str:
    """Hash the built wheel without loading it into the acceptance process."""

    digest = hashlib.sha256()
    try:
        with wheel.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise AcceptanceFailure("wheel", "wheel_unreadable") from None
    return digest.hexdigest()


def _verify_shared_wheel(wheel: Path) -> None:
    """Prove the one wheel carries both backend and SDK packages."""

    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata_names = [
                name for name in names if name.endswith(".dist-info/METADATA")
            ]
            _check(len(metadata_names) == 1, "wheel", "expected_one_distribution_metadata")
            metadata = archive.read(metadata_names[0]).decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile):
        raise AcceptanceFailure("wheel", "wheel_not_a_zip") from None

    _check(
        any(name.startswith("eurogas_nexus/") and name.endswith(".py") for name in names),
        "wheel",
        "missing_backend_package",
    )
    _check(
        any(
            name.startswith("eurogas_nexus_sdk/") and name.endswith(".py")
            for name in names
        ),
        "wheel",
        "missing_sdk_package",
    )
    name_lines = {
        line.split(":", 1)[1].strip().lower()
        for line in metadata.splitlines()
        if line.lower().startswith("name:")
    }
    _check(name_lines == {"eurogas-nexus"}, "wheel", "wrong_distribution_metadata")


def _normalize_interpreter_path(value: str) -> Path:
    """Return a lexical absolute interpreter path without resolving symlinks.

    A POSIX venv's ``bin/python`` is normally a symlink to the base interpreter.
    Dereferencing it before invocation makes CPython start as that base
    interpreter and lose the venv's ``sys.prefix``. ``abspath`` normalizes the
    caller's path but deliberately leaves symlinks untouched.
    """

    try:
        path = Path(os.path.abspath(os.path.expanduser(value)))
    except (OSError, RuntimeError):
        raise AcceptanceFailure("configuration", "venv_python_not_found") from None
    _check(path.exists(), "configuration", "venv_python_not_found")
    _check(path.is_file(), "configuration", "venv_python_not_file")
    return path


def _query_venv(venv_python: Path) -> tuple[Path, Path]:
    """Ask the isolated interpreter for its prefix and purelib directory."""

    script = (
        "import json, sys, sysconfig; "
        "assert sys.prefix != sys.base_prefix; "
        "print(json.dumps({'prefix': sys.prefix, "
        "'purelib': sysconfig.get_paths()['purelib']}))"
    )
    try:
        completed = subprocess.run(
            [str(venv_python), "-I", "-c", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
            env=_base_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise AcceptanceFailure("venv", "interpreter_unavailable") from None
    _check(completed.returncode == 0, "venv", "interpreter_not_a_venv")
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        raise AcceptanceFailure("venv", "interpreter_invalid_response") from None
    _check(isinstance(payload, dict), "venv", "interpreter_invalid_response")
    try:
        prefix = Path(str(payload["prefix"])).resolve(strict=True)
        purelib = Path(str(payload["purelib"])).resolve(strict=True)
    except (KeyError, OSError, RuntimeError):
        raise AcceptanceFailure("venv", "interpreter_invalid_paths") from None
    _check(prefix.is_dir(), "venv", "prefix_not_directory")
    _check(purelib.is_relative_to(prefix), "venv", "purelib_outside_prefix")
    return prefix, purelib


def _assert_installed_origin(origin: Path, venv_prefix: Path, checkout_root: Path) -> Path:
    """Require the imported SDK to be inside the venv and outside the source tree."""

    try:
        resolved = origin.resolve(strict=True)
    except (OSError, RuntimeError):
        raise AcceptanceFailure("sdk_origin", "sdk_file_missing") from None
    _check(resolved.is_file(), "sdk_origin", "sdk_file_missing")
    if resolved.is_relative_to(checkout_root):
        raise AcceptanceFailure("sdk_origin", "sdk_imported_from_checkout")
    if not resolved.is_relative_to(venv_prefix):
        raise AcceptanceFailure("sdk_origin", "sdk_outside_expected_venv")
    return resolved


_SMOKE_SCRIPT = r'''"""Isolated import/typed-contract smoke for the installed SDK wheel."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import pkgutil
import sys
from pathlib import Path


class SmokeError(RuntimeError):
    """Controlled failure with a stable code and no raw exception text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def main() -> int:
    """Import every SDK module and assert typed and synthetic model contracts."""

    result = {
        "status": "failed",
        "sdk_origin": "",
        "sdk_version": "",
        "module_count": 0,
        "typed_validation_case_count": 0,
        "typed_error_fields": [],
        "market_evidence_field_count": 0,
        "market_contract_case_count": 0,
    }
    try:
        prefix = Path(sys.argv[1]).resolve(strict=True)
        checkout = Path(sys.argv[2]).resolve(strict=True)

        sdk = importlib.import_module("eurogas_nexus_sdk")
        origin = Path(sdk.__file__).resolve(strict=True)
        if origin.is_relative_to(checkout):
            raise SmokeError("sdk_origin_in_checkout")
        if not origin.is_relative_to(prefix):
            raise SmokeError("sdk_origin_outside_venv")
        result["sdk_origin"] = origin.relative_to(prefix).as_posix()

        try:
            result["sdk_version"] = importlib.metadata.version("eurogas-nexus")
        except importlib.metadata.PackageNotFoundError:
            raise SmokeError("distribution_metadata_missing") from None

        imported = []
        for info in pkgutil.walk_packages(
            list(getattr(sdk, "__path__", [])), prefix=sdk.__name__ + "."
        ):
            try:
                importlib.import_module(info.name)
            except Exception:
                raise SmokeError("module_import_failed") from None
            imported.append(info.name)
        if not imported:
            raise SmokeError("no_sdk_modules_found")
        result["module_count"] = len(imported) + 1
        result["python_version"] = ".".join(str(part) for part in sys.version_info[:3])

        from pydantic import ValidationError

        cases = (
            (
                "eurogas_nexus_sdk.capacity_billing",
                "CapacityBillingRequest",
                "billing_start",
            ),
            (
                "eurogas_nexus_sdk.lng_economics_only",
                "LngEconomicsOnlyRequest",
                "valuation_date",
            ),
        )
        fields = []
        for module_name, class_name, required_field in cases:
            model = getattr(importlib.import_module(module_name), class_name)
            try:
                model()
            except ValidationError as exc:
                locations = {
                    item.get("loc", (None,))[0]
                    for item in exc.errors()
                    if item.get("loc")
                }
                if required_field not in locations:
                    raise SmokeError("required_field_not_reported") from None
                fields.append(required_field)
            else:
                raise SmokeError("missing_required_fields_accepted")
        result["typed_validation_case_count"] = len(fields)
        result["typed_error_fields"] = fields

        market = importlib.import_module("eurogas_nexus_sdk.market")
        observation_model = market.NormalizedMarketObservation
        model_fields = getattr(observation_model, "model_fields", None)
        if model_fields is None:
            model_fields = getattr(observation_model, "__fields__", {})
        evidence_fields = (
            "source_price_status",
            "source_price_exact",
            "source_price_raw",
            "source_price_volume_mwh_exact",
            "source_price_volume_raw",
            "source_price_volume_status",
            "source_price_provenance",
            "source_price_issue",
            "source_price_issue_detail",
            "source_price_source_system",
            "source_price_source_reference",
            "source_price_source_dataset",
            "price_float_provenance",
            "price_semantics",
            "executable_quote",
            "price_gbp_mwh_exact",
            "price_gbp_mwh_provenance",
            "price_name",
        )
        strict_text_fields = (
            "price_gbp_mwh_exact",
            "source_price_exact",
            "source_price_raw",
            "source_price_volume_mwh_exact",
            "source_price_volume_raw",
        )
        if not {*evidence_fields, "price_gbp_mwh", "metadata_json"} <= set(model_fields):
            raise SmokeError("market_evidence_field_missing")

        required_values = {
            "observation_id": "synthetic-observation",
            "market_venue": "synthetic-venue",
            "product": "synthetic-product",
            "price": 1.25,
            "unit": "MWh",
            "currency": "GBP",
            "period_start_utc": "2026-01-01T00:00:00Z",
            "period_end_utc": "2026-01-02T00:00:00Z",
            "hub": "NBP",
            "tenor": "day-ahead",
            "is_gas_price": True,
        }
        positive_exact = "+" + "0" * 80 + "12345678901234567890.4500"
        negative_exact = "-" + "9" * 80 + "8765432109876543210.0100"
        positive_volume = "+" + "0" * 64 + "42.500000000000000000"
        negative_volume = "-" + "9" * 64 + "42.500000000000000000"
        evidence_values = {
            "price_gbp_mwh_exact": positive_exact,
            "price_gbp_mwh_provenance": "synthetic-exact-source",
            "price_name": "synthetic-price-name",
            "source_price_status": "exact",
            "source_price_exact": negative_exact,
            "source_price_raw": " " + negative_exact + " ",
            "source_price_volume_mwh_exact": positive_volume,
            "source_price_volume_raw": " " + positive_volume + " ",
            "source_price_volume_status": "exact",
            "source_price_provenance": "synthetic-source-provenance",
            "source_price_issue": None,
            "source_price_issue_detail": None,
            "source_price_source_system": "synthetic-source-system",
            "source_price_source_reference": "synthetic-source-reference",
            "source_price_source_dataset": "synthetic-source-dataset",
            "price_float_provenance": "synthetic-float-provenance",
            "price_semantics": "reference_index",
        }
        full = observation_model(
            **required_values,
            **evidence_values,
            price_gbp_mwh=1.25,
            executable_quote=True,
            metadata_json={
                "publication_time_utc": None,
                "publication_time_basis": "unknown",
                "availability_basis": "response_receipt",
                "available_at_utc": "2026-01-01T00:00:05Z",
            },
        )
        dumped = full.model_dump()
        if not {*evidence_fields, "price_gbp_mwh", "metadata_json"} <= set(dumped):
            raise SmokeError("market_evidence_field_dropped")
        for name, value in evidence_values.items():
            if dumped.get(name) != value:
                raise SmokeError("market_evidence_value_changed")
        if dumped.get("price_gbp_mwh") != 1.25:
            raise SmokeError("market_conversion_value_changed")
        for name in strict_text_fields:
            if not isinstance(dumped.get(name), str):
                raise SmokeError("market_exact_text_not_string")
            if dumped.get(name) != evidence_values[name]:
                raise SmokeError("market_exact_text_not_preserved")
        if dumped.get("executable_quote") is not True:
            raise SmokeError("market_executable_quote_not_strict")
        contract_cases = 1

        for expected in (True, False, None):
            probe = observation_model(**required_values, executable_quote=expected)
            if probe.model_dump().get("executable_quote") is not expected:
                raise SmokeError("market_executable_quote_not_strict")
        contract_cases += 1
        for forged in (1, 0, 1.0, "true", "false"):
            try:
                observation_model(**required_values, executable_quote=forged)
            except ValidationError:
                continue
            raise SmokeError("market_executable_quote_coerced")
        contract_cases += 1

        for name in strict_text_fields:
            for forged in (123.45, 42, True):
                try:
                    observation_model(**required_values, **{name: forged})
                except ValidationError:
                    continue
                raise SmokeError("market_numeric_exact_accepted")
        contract_cases += 1

        legacy = observation_model(**required_values)
        legacy_dump = legacy.model_dump()
        for name in evidence_fields:
            if legacy_dump.get(name) is not None:
                raise SmokeError("market_optional_default_changed")
        if legacy_dump.get("executable_quote") is not None:
            raise SmokeError("market_executable_quote_default_changed")
        if legacy_dump.get("price_gbp_mwh") is not None:
            raise SmokeError("market_conversion_value_default_changed")
        if legacy_dump.get("metadata_json") != {}:
            raise SmokeError("market_metadata_default_changed")
        contract_cases += 1

        metadata = {
            "publication_time_utc": None,
            "publication_time_basis": "unknown",
            "availability_basis": "response_receipt",
            "available_at_utc": "2026-01-01T00:00:05Z",
            "retrieved_at_utc": "2026-01-01T00:00:06Z",
        }
        metadata_dump = observation_model(
            **required_values, metadata_json=metadata
        ).model_dump()["metadata_json"]
        if metadata_dump.get("publication_time_utc", "missing") is not None:
            raise SmokeError("market_unknown_publication_became_receipt")
        if metadata_dump.get("publication_time_basis") != "unknown":
            raise SmokeError("market_publication_basis_changed")
        if metadata_dump.get("availability_basis") != "response_receipt":
            raise SmokeError("market_availability_basis_changed")
        if metadata_dump.get("available_at_utc") != metadata["available_at_utc"]:
            raise SmokeError("market_receipt_time_changed")
        if metadata_dump.get("retrieved_at_utc") != metadata["retrieved_at_utc"]:
            raise SmokeError("market_retrieval_time_changed")
        contract_cases += 1

        result["market_evidence_field_count"] = len(evidence_fields)
        result["market_contract_case_count"] = contract_cases
        result["status"] = "passed"
    except SmokeError as exc:
        result["error_code"] = exc.code
    except Exception:
        result["error_code"] = "unexpected_smoke_failure"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _copy_example(checkout_root: Path, runtime_dir: Path) -> Path:
    """Copy the existing economics example into the isolated runtime directory."""

    try:
        source = (
            checkout_root / "scripts" / "examples" / "lng_capacity_economics.py"
        ).resolve(strict=True)
    except (OSError, RuntimeError):
        raise AcceptanceFailure("example", "source_example_missing") from None
    _check(source.is_relative_to(checkout_root), "example", "example_path_escaped_checkout")
    _check(source.is_file(), "example", "source_example_missing")
    destination = runtime_dir / "lng_capacity_economics.py"
    try:
        shutil.copyfile(source, destination)
    except OSError:
        raise AcceptanceFailure("example", "copy_failed") from None
    _check(
        destination.is_relative_to(runtime_dir),
        "example",
        "copy_path_escaped_runtime",
    )
    return destination


def _write_smoke_script(runtime_dir: Path) -> Path:
    """Write the stdlib smoke outside the checkout."""

    destination = runtime_dir / "sdk_import_smoke.py"
    try:
        destination.write_text(_SMOKE_SCRIPT, encoding="utf-8")
    except OSError:
        raise AcceptanceFailure("smoke", "script_write_failed") from None
    _check(
        destination.is_relative_to(runtime_dir),
        "smoke",
        "script_path_escaped_runtime",
    )
    return destination


def _run_json_process(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stage: str,
) -> dict[str, Any]:
    """Run one JSON-emitting child without ever exposing its output on failure."""

    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise AcceptanceFailure(stage, "timeout") from None
    except OSError:
        raise AcceptanceFailure(stage, "process_start_failed") from None
    if completed.returncode != 0:
        raise AcceptanceFailure(stage, "process_failed")
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        raise AcceptanceFailure(stage, "invalid_json") from None
    _check(isinstance(payload, dict), stage, "invalid_payload")
    return payload


def _validate_smoke_summary(
    summary: dict[str, Any],
    *,
    venv_prefix: Path,
    checkout_root: Path,
    installed_origin: Path,
) -> tuple[int, str, str, str]:
    """Validate the isolated import smoke and return its non-secret counts."""

    _check(summary.get("status") == "passed", "smoke", "smoke_not_passed")
    relative_origin = summary.get("sdk_origin")
    _check(
        isinstance(relative_origin, str)
        and bool(relative_origin)
        and not Path(relative_origin).is_absolute(),
        "smoke",
        "sdk_origin_invalid",
    )
    imported_origin = _assert_installed_origin(
        venv_prefix / relative_origin, venv_prefix, checkout_root
    )
    _check(imported_origin == installed_origin, "smoke", "sdk_origin_mismatch")

    module_count = summary.get("module_count")
    _check(
        isinstance(module_count, int)
        and not isinstance(module_count, bool)
        and module_count > 0,
        "smoke",
        "sdk_module_count_invalid",
    )
    python_version = summary.get("python_version")
    _check(
        isinstance(python_version, str)
        and re.fullmatch(r"3\.11\.\d{1,2}", python_version) is not None,
        "smoke",
        "python_version_not_canonical",
    )
    typed_count = summary.get("typed_validation_case_count")
    typed_fields = summary.get("typed_error_fields")
    _check(typed_count == 2, "smoke", "typed_validation_count_changed")
    _check(
        isinstance(typed_fields, list)
        and set(typed_fields) == {"billing_start", "valuation_date"},
        "smoke",
        "typed_validation_fields_changed",
    )
    market_field_count = summary.get("market_evidence_field_count")
    _check(
        isinstance(market_field_count, int)
        and not isinstance(market_field_count, bool)
        and market_field_count == EXPECTED_MARKET_EVIDENCE_FIELD_COUNT,
        "smoke",
        "market_evidence_field_count_changed",
    )
    market_case_count = summary.get("market_contract_case_count")
    _check(
        isinstance(market_case_count, int)
        and not isinstance(market_case_count, bool)
        and market_case_count == EXPECTED_MARKET_CONTRACT_CASE_COUNT,
        "smoke",
        "market_contract_case_count_changed",
    )
    sdk_version = summary.get("sdk_version")
    _check(
        isinstance(sdk_version, str) and _SAFE_VERSION_RE.fullmatch(sdk_version) is not None,
        "smoke",
        "sdk_version_invalid",
    )
    return module_count, sdk_version, relative_origin, python_version


def _validate_example_summary(summary: dict[str, Any]) -> dict[str, int]:
    """Require the existing example's six actual HTTP checks to have passed."""

    _check(summary.get("status") == "passed", "example", "example_not_passed")
    _check(summary.get("synthetic_inputs") is True, "example", "inputs_not_marked_synthetic")
    _check(summary.get("sdk_mode") == "installed", "example", "example_used_source_sdk")
    checks = summary.get("checks")
    _check(isinstance(checks, list), "example", "checks_missing")
    _check(len(checks) == EXPECTED_HTTP_CASE_COUNT, "example", "http_case_count_changed")
    check_ids: list[str] = []
    for check in checks:
        _check(isinstance(check, dict), "example", "check_payload_invalid")
        _check(check.get("status") == "pass", "example", "http_check_failed")
        check_id = check.get("check")
        _check(isinstance(check_id, str), "example", "check_id_invalid")
        check_ids.append(check_id)
    _check(set(check_ids) == EXPECTED_CHECK_IDS, "example", "http_check_set_changed")
    return {
        "http_case_count": len(checks),
        "capacity_http_case_count": 3,
        "lng_http_case_count": 1,
        "refusal_case_count": 2,
    }


def _terminate_process(
    process: subprocess.Popen[Any] | None,
    grace_seconds: float = 10.0,
) -> None:
    """Terminate and reap exactly the child this helper started."""

    if process is None or process.poll() is not None:
        return
    with suppress(OSError):
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    with suppress(OSError):
        process.kill()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=grace_seconds)


def _reserve_loopback_port() -> int:
    """Reserve one ephemeral IPv4 loopback port for the owned backend child."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            return int(sock.getsockname()[1])
    except OSError:
        raise AcceptanceFailure("api", "loopback_port_unavailable") from None


def _start_api(
    *,
    checkout_root: Path,
    runtime_dir: Path,
    port: int,
    api_token: str,
) -> subprocess.Popen[Any]:
    """Start the source backend on loopback, owned and reaped by this helper."""

    api_env = _base_env()
    api_env.update(
        {
            "EUROGAS_NEXUS_ENV": "test",
            "EUROGAS_NEXUS_API_PROFILE": "development",
            "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED": "false",
            "EUROGAS_NEXUS_PUBLIC_API_TOKEN": api_token,
            "EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT": str(runtime_dir / "artifacts"),
            "PYTHONPATH": str(checkout_root / "src"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    log_path = runtime_dir / "api.log"
    process: subprocess.Popen[Any] | None = None
    popen_options: dict[str, Any] = {}
    if os.name == "posix":
        popen_options["start_new_session"] = True
    try:
        with log_path.open("wb") as log_handle:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "apps.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                    "--no-access-log",
                ],
                cwd=checkout_root,
                env=api_env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                **popen_options,
            )
    except OSError:
        raise AcceptanceFailure("api", "api_process_start_failed") from None
    _check(process is not None, "api", "api_process_start_failed")
    return process


def _wait_for_health(process: subprocess.Popen[Any], health_url: str) -> None:
    """Wait at most 30 seconds for the owned backend's liveness response."""

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AcceptanceFailure("api", "api_exited_before_health")
        remaining = max(0.1, deadline - time.monotonic())
        try:
            with opener.open(health_url, timeout=min(1.5, remaining)) as response:
                if response.status == 200:
                    response.read(4096)
                    return
        except (OSError, urllib.error.URLError):
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.25, remaining))
    raise AcceptanceFailure("api", "api_health_timeout")


def _create_runtime_dir(work_root: Path, checkout_root: Path) -> Path:
    """Create one unique smoke directory outside the checkout."""

    try:
        work_root.mkdir(parents=True, exist_ok=True)
        runtime_dir = Path(
            tempfile.mkdtemp(prefix="eurogas-sdk-acceptance-", dir=str(work_root))
        ).resolve(strict=True)
    except OSError:
        raise AcceptanceFailure("configuration", "runtime_dir_unavailable") from None
    _check(
        not runtime_dir.is_relative_to(checkout_root),
        "configuration",
        "runtime_dir_inside_checkout",
    )
    return runtime_dir


def _safe_source_commit(value: str | None) -> str:
    """Return only a full commit id; callers pass the verified HEAD when known."""

    candidate = (value or "").lower()
    return candidate if _SOURCE_COMMIT_RE.fullmatch(candidate) is not None else "unverified"


def _failure_report(
    stage: str,
    code: str,
    *,
    source_commit: str | None,
    wheel_sha256: str | None,
) -> dict[str, Any]:
    """Build a failure record that cannot contain child output or credentials."""

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "synthetic_inputs": True,
        "stage": stage,
        "error_code": code,
        "source_commit": _safe_source_commit(source_commit),
    }
    if wheel_sha256 is not None:
        report["wheel_sha256"] = wheel_sha256
    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    """Atomically write one non-secret JSON record."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError:
        raise AcceptanceFailure("report", "report_write_failed") from None


def _run_acceptance(
    args: argparse.Namespace,
    context: dict[str, Any],
    *,
    git_runner: GitRunner | None = None,
) -> dict[str, Any]:
    """Run the complete bounded acceptance and return its safe record."""

    _check(
        _SOURCE_COMMIT_RE.fullmatch(args.source_commit) is not None,
        "configuration",
        "source_commit_invalid",
    )
    checkout_root = _resolve_existing_dir(args.checkout_root, "checkout_root")
    source_commit = _bind_source_commit(
        checkout_root, args.source_commit, git_runner=git_runner
    )
    context["source_commit"] = source_commit
    _require_clean_tracked_worktree(checkout_root, git_runner=git_runner)
    wheel_dir = _resolve_existing_dir(args.wheel_dir, "wheel_dir")
    wheel = _find_single_wheel(wheel_dir)
    wheel_sha256 = _wheel_sha256(wheel)
    context["wheel_sha256"] = wheel_sha256
    _verify_shared_wheel(wheel)

    venv_python = _normalize_interpreter_path(args.venv_python)
    venv_prefix, purelib = _query_venv(venv_python)
    _check(
        not venv_prefix.is_relative_to(checkout_root),
        "configuration",
        "venv_inside_checkout",
    )
    installed_origin = _assert_installed_origin(
        purelib / "eurogas_nexus_sdk" / "__init__.py",
        venv_prefix,
        checkout_root,
    )

    work_root = _validate_work_root(checkout_root, args.work_dir)
    runtime_dir = _create_runtime_dir(work_root, checkout_root)
    process: subprocess.Popen[Any] | None = None
    try:
        example_script = _copy_example(checkout_root, runtime_dir)
        smoke_script = _write_smoke_script(runtime_dir)
        api_token = "sdk-acceptance-" + secrets.token_urlsafe(32)
        port = _reserve_loopback_port()
        base_url = f"http://127.0.0.1:{port}"
        process = _start_api(
            checkout_root=checkout_root,
            runtime_dir=runtime_dir,
            port=port,
            api_token=api_token,
        )
        _wait_for_health(process, f"{base_url}/api/health")

        smoke_env = _base_env()
        smoke_env.update(
            {
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        smoke_summary = _run_json_process(
            [
                str(venv_python),
                "-I",
                str(smoke_script),
                str(venv_prefix),
                str(checkout_root),
            ],
            cwd=runtime_dir,
            env=smoke_env,
            timeout=SMOKE_TIMEOUT_SECONDS,
            stage="smoke",
        )
        (
            module_count,
            sdk_version,
            relative_origin,
            sdk_python_version,
        ) = _validate_smoke_summary(
            smoke_summary,
            venv_prefix=venv_prefix,
            checkout_root=checkout_root,
            installed_origin=installed_origin,
        )

        example_env = _base_env()
        example_env.update(
            {
                "EUROGAS_UAT_API_BASE_URL": base_url,
                "EUROGAS_NEXUS_PUBLIC_API_TOKEN": api_token,
                "EUROGAS_NEXUS_PRINCIPAL": "ci-installed-sdk",
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        example_summary = _run_json_process(
            [str(venv_python), "-I", str(example_script)],
            cwd=runtime_dir,
            env=example_env,
            timeout=SMOKE_TIMEOUT_SECONDS,
            stage="example",
        )
        http_counts = _validate_example_summary(example_summary)
    finally:
        _terminate_process(process)
        shutil.rmtree(runtime_dir, ignore_errors=True)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "synthetic_inputs": True,
        "python_version": sdk_python_version,
        "sdk_version": sdk_version,
        "sdk_origin": relative_origin,
        "wheel_sha256": wheel_sha256,
        "source_commit": source_commit,
        "counts": {
            "sdk_module_count": module_count,
            "typed_validation_case_count": 2,
            **http_counts,
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build the explicit, env-independent CLI contract."""

    parser = argparse.ArgumentParser(
        description=(
            "Run installed-wheel SDK acceptance against a loopback source backend. "
            "All paths are explicit; no configuration environment variables are read."
        )
    )
    parser.add_argument("--checkout-root", required=True)
    parser.add_argument("--wheel-dir", required=True)
    parser.add_argument("--venv-python", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--source-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the acceptance, always writing a safe JSON record when possible."""

    args = _build_parser().parse_args(argv)
    context: dict[str, Any] = {}
    try:
        report = _run_acceptance(args, context)
    except AcceptanceFailure as exc:
        report = _failure_report(
            exc.stage,
            exc.code,
            source_commit=context.get("source_commit"),
            wheel_sha256=context.get("wheel_sha256"),
        )
    except Exception:  # noqa: BLE001 - deliberate credential-safe boundary
        report = _failure_report(
            "unexpected",
            "unexpected_failure",
            source_commit=context.get("source_commit"),
            wheel_sha256=context.get("wheel_sha256"),
        )

    try:
        _write_report(Path(args.report), report)
    except AcceptanceFailure as exc:
        print(
            json.dumps(
                _failure_report(
                    exc.stage,
                    exc.code,
                    source_commit=context.get("source_commit"),
                    wheel_sha256=context.get("wheel_sha256"),
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

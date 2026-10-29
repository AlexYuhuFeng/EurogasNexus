# Weather Model Internal Numerical CI Contract

**Status: internal CI computation only.** This contract does not ship NumPy, does
not make NumPy a customer/runtime dependency, does not approve redistribution, and
does not establish provider accuracy, model promotion, or production readiness.
The native notice/source-offer obligations recorded in
`docs/engineering/NUMPY_RUNTIME_CLOSURE_20261029.md` remain **OPEN** for customer
redistribution. The source custom-licence/source-offer question is not solved here.

## Approved scope and artifacts

Root approved NumPy 2.3.5 for isolated internal CI computation under the RFC-0003
approved decoder/numerical experiments and the NumPy default-stack dependency
policy. The exact reviewed artifact is the CPython 3.11 Linux wheel recorded in
`.local-runtime/delivery-20261029-numpy/manifest.json`:

- wheel: `numpy-2.3.5-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`
- SHA-256: `8cba086a43d54ca804ce711b2a940b16e452807acebe7852ff327f1ecd49b0d4`
- `Requires-Dist: []`

`requirements-scientific-ci.lock` contains only that pin and hash. It is not
referenced by `pyproject.toml`, `requirements.lock`, `requirements-runtime.lock`,
the Dockerfile, or any customer/release artifact.

The single shared definition is
`.github/workflows/weather-model-acceptance.yml`. It is both reusable
(`workflow_call`) and manually dispatchable (`workflow_dispatch`), has read-only
`contents` permission, accepts no ref/source inputs, checks out `github.sha`, uses
canonical Python 3.11.12 on Ubuntu 24.04, and is called without inputs by both
`ci.yml` and `ci-manual.yml`.

## Install and execution sequence

1. Install the existing hash-pinned base/build locks:
   `python -m pip install --require-hashes -r requirements-build.lock -r requirements.lock`.
2. Install the project editably without dependency resolution:
   `python -m pip install --no-deps --no-build-isolation -e .`.
3. Install the science-only lock with
   `--require-hashes --only-binary=:all: --no-deps`.
4. Verify `numpy.__version__ == "2.3.5"` before any numerical test.
5. Start the PostgreSQL service with the existing PostgreSQL job's settings and
   run `scripts/ci/run_postgres_ci.sh` for Alembic head, the registered
   PostgreSQL modules, and the in-process authenticated API smoke. The existing
   job records `postgres:16` as a tag, not an image digest; this workflow mirrors
   that exact tag rather than inventing an unverified digest. If a digest is
   approved, it must be applied to every PostgreSQL service together.
6. Run the seven explicitly selected focused unit/db modules and the two
   actual-fit PostgreSQL modules listed below, writing JUnit XML. Selection is
   by exact file name; no directory-wide or glob test selection is used.

The focused selection is:

- `tests/unit/test_weather_demand.py`
- `tests/unit/test_weather_demand_inputs.py`
- `tests/unit/test_demand_target_inputs.py`
- `tests/unit/test_weather_demand_runtime.py`
- `tests/unit/test_weather_demand_operator_cli.py`
- `tests/unit/test_weather_forecast_contract.py`
- `tests/db/test_ecmwf_weather_feature_bridge.py`

The actual-PostgreSQL selection is:

- `tests/integration/test_weather_demand_runtime_postgres.py`
- `tests/integration/test_weather_demand_operator_postgres.py`

All fitting mechanics use explicit synthetic fixtures. No provider history,
accuracy result, promotion, or customer acceptance is claimed. The API smoke is
in-process (`TestClient`); the job starts no owned HTTP server, so there is no
server process to clean up. Database URLs and credentials stay in environment
variables and are never printed.

## JUnit zero-skip gate and module identity

The dedicated pytest invocations write JUnit XML. A parsing step then fails the
job when any of the following is true:

- any `skipped` test is reported (even one), whether as a testcase child or in a
  testsuite aggregate;
- zero test cases are reported;
- any failure or error is reported, whether as a testcase child or in a
  testsuite aggregate;
- any required module identity is absent from the XML;
- a testcase's normalized `classname` and `file` identify different required
  modules (inconsistent evidence).

Module evidence is derived **only** from a testcase's exact normalized
`classname`/`file` identity. The testcase `name` is never evidence:

- `file` is normalized to a repository-relative POSIX path (backslashes and
  repeated separators normalized, leading `./` removed) and must equal the
  required module path exactly. A longer path such as `vendor/tests/...` is not
  that identity, and absolute paths are not accepted;
- `classname` is normalized to a dotted path (separators to `.`, optional `.py`
  removed) and must equal the required dotted module exactly, or that module
  followed by `.` and a narrower test identity such as a test class;
- a required module is present only when at least one testcase's own
  `classname`/`file` identifies it. Text in another testcase's `name` cannot
  satisfy a missing module;
- if a testcase supplies both a recognized `file` and a recognized `classname`,
  they must identify the same required module.

`pytest.importorskip` cannot satisfy the gate: a skip is always a failure here.
The gate writes only safe identity/count JSON (commit, runner, Python and NumPy
versions, pass/fail/skip counts, missing module names, identity-conflict count).
The uploaded artifact is limited to the JUnit XML and those JSON files; no
virtual environment, wheel, archive, credential, or raw model data is uploaded.

The contract tests execute this same extracted inline parser against a valid
report, a missing module spoofed by testcase names, name-only evidence, skips,
failures, errors and zero cases. Every tampered report must fail.

## Audit and licence boundaries

The existing dependency-audit job gains a `pip-audit -r
requirements-scientific-ci.lock` check using the already-installed `pip-audit`.
That audits the reviewed internal lock; it is not proof that a shipped runtime or
customer artifact contains NumPy.

The global default dependency/licence audit is unchanged. NumPy is not added to
the runtime lock, is not suppressed in the licence auditor, and is not part of a
release artifact. The scientific-environment job is limited to reviewed internal
execution and must not be described as a shipped-runtime audit.

## Non-goals

No release signing, publishing, registry/tag mutation, repository write, customer
redistribution, or alternate numerical solver is introduced. No existing
non-science RFC-0004 shared pipeline or gate is relaxed. The reusable workflow has
one job; the two callers add only that invocation.

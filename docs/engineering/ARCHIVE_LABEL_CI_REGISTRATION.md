# Archive Persistence and Label Basis CI Registration

**Status: internal numerical CI registration only.** This document records the
explicit test selections added to the existing internal numerical gates. It is
not provider-history evidence, archive-capture proof, model accuracy, source
activation, model promotion, customer acceptance, or a shipped-runtime claim.

## Registered modules

The following modules are now selected by exact file path, not by directory or
glob, in the existing shared workflow
`.github/workflows/weather-model-acceptance.yml`:

Focused scientific unit step (`Focused weather-model unit tests`, writing
`unit.xml`):

- `tests/unit/test_weather_archive_persistence.py`
- `tests/unit/test_weather_demand_label_basis.py`
- `tests/unit/test_demand_target_label_mapper.py`

Scientific actual-PostgreSQL step (`Actual PostgreSQL weather-model fit tests`,
writing `postgres.xml`):

- `tests/integration/test_weather_archive_persistence_postgres.py`

The archive PostgreSQL module is also registered in the full PostgreSQL CI step
(`PostgreSQL migrations, registered tests, and API auth smoke`, via
`scripts/ci/run_postgres_ci.sh`), alongside the existing registered modules.

Each new module has a distinct required identity in the JUnit zero-skip gate:

| Gate key | Exact module path |
| --- | --- |
| `weather_archive_persistence` | `tests/unit/test_weather_archive_persistence.py` |
| `weather_label_basis` | `tests/unit/test_weather_demand_label_basis.py` |
| `demand_target_label_mapper` | `tests/unit/test_demand_target_label_mapper.py` |
| `pg_weather_archive_persistence` | `tests/integration/test_weather_archive_persistence_postgres.py` |

Module evidence continues to come only from a testcase's normalized exact
`file` path and `classname` dotted identity. A testcase name cannot satisfy a
required module. A file/classname identity conflict remains a gate failure. The
gate still rejects any skip, failure, error, or zero test cases, and every
existing required module remains required.

The earlier `WEATHER_MODEL_CI_CONTRACT.md` is intentionally untouched by this
bounded registration; its historical module counts describe the prior
selection. The exact workflow paths and required identities above govern the
added modules.

## Measured evidence and limits

The root review recorded the archive PostgreSQL module at 19 passing tests and a
combined numerical execution at 56 passing tests; those measurements predate this
bounded mapper registration. The root review also recorded 53 passing
mapper/new+existing focused tests: the newly committed label mapper plus its
existing mapper coverage. A separate actual read-only PostgreSQL probe mapped all
17 persisted authentic National Gas REST revisions over five gas days, preserving
revision IDs, ranks, values, and actual-receipt evidence with zero diagnostics and
no writes or model. Those measurements are local mechanics and read-only
source-consumption evidence. They are not a hosted CI result, an actual provider
archive capture, historical-publication proof, genuine out-of-sample evidence, or
a provider-accuracy/model claim.

Windows collection can skip NumPy-dependent cases.
Those Windows skips are not numerical evidence and must not be reported as a
numerical pass. The scientific gate remains zero-skip and the approved NumPy
wheel is installed only in the isolated internal CI environment.

No hosted GitHub Actions run is claimed for this registration until one actually
runs and its evidence is inspected. No commit, push, or credential use is part of
the registration.

## Preserved boundaries

This registration adds test selections and identity expectations only. It does
not change:

- the PostgreSQL service image, service environment, ports, or health checks;
- read-only workflow permissions, pinned action SHAs, checkout SHA behavior, or
  the absence of source/ref inputs and secrets;
- dependency locks, the approved NumPy pin/hash, package metadata, or customer
  runtime/redistribution status;
- database schema, migrations, defaults, archive reads, source activation,
  model eligibility, or production behavior.

The archive tests use synthetic transport/decoder mechanics and disposable
PostgreSQL schemas. The label-basis and mapper tests are pure/synthetic research
mechanics. None of these sets demonstrates provider history, retrospective-label
acceptance, forecast accuracy, regional calibration, or customer readiness.

## Contract coverage

`tests/contract/test_weather_model_ci.py` keeps the existing exact-selection,
zero-skip, identity-conflict, and parser-execution checks. It additionally
requires the archive PostgreSQL path in the full PostgreSQL CI script and all
four module paths registered here, including the mapper's exact unit selection
and gate identity, while preserving the existing required modules and scientific
contract document assertions.

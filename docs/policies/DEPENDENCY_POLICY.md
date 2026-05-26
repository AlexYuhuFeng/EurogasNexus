# Dependency Policy

## Allowed Default Stack

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- HTTPX
- pandas
- NumPy
- PyArrow
- python-dateutil
- PyYAML
- pytest
- Ruff

## Bootstrap Dependency Scope

The bootstrap milestone uses the smallest useful subset:

- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- HTTPX
- pytest
- Ruff

Heavy optional dependencies are deferred until a milestone proves they are
needed.

## Restricted Licenses

Do not add dependencies under GPL, LGPL, AGPL, SSPL, BUSL, Elastic,
Redis-RSAL, Commons-Clause, or PolyForm terms without explicit review.

## Review Requirements

Every new dependency must document:

- purpose;
- license;
- runtime or development scope;
- why the standard library or existing dependency is insufficient;
- whether it introduces network, process, data, or deployment risk.


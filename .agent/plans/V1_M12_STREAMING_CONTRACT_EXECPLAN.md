# V1 Milestone 12 Streaming Contract ExecPlan

## 1. Goal
Harden streaming boundary with explicit optional-contract tests and placeholder message envelope type.

## 2. Non-goals
- No Kafka dependency.
- No producer/consumer runtime implementation.
- No background services.

## 3. Product Boundary
Contract-only streaming shell to preserve "not source of truth" guarantee.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M12_STREAMING_CONTRACT_EXECPLAN.md`
- `src/eurogas_nexus/streaming/contracts.py`
- `src/eurogas_nexus/streaming/__init__.py`
- `docs/contracts/12_STREAMING_KAFKA_CONTRACT.md`
- `docs/contracts/19_FUNCTION_SIGNATURE_CATALOG.md`
- `tests/streaming/test_streaming_contracts.py`
- `docs/operations/VALIDATION.md`

## 5. Dependency Policy
No new dependencies.

## 6. Data Policy
Streaming remains non-authoritative; PostgreSQL remains source of truth.

## 7. API Impact
None.

## 8. DB Impact
None.

## 9. Tests
- `tests/streaming/test_streaming_contracts.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/workflow tests/streaming
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Streaming shell types are import-safe and dependency-free.
- Contract tests enforce no kafka dependency and non-authoritative policy language.

## 12. Rollback Notes
Revert streaming shell files/tests and docs updates.

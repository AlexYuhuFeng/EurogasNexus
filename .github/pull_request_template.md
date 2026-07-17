## Summary

- 

## Scope Check

- [ ] This change stays inside the approved milestone scope.
- [ ] No business features were added without a milestone document.
- [ ] No external APIs, LLM providers, live connectors, or live infrastructure are called by tests or import-time code.
- [ ] No Docker startup or live DB migration was run as part of this change.

## Public Repository Data Warning

This is a public repository. Do not commit secrets, real vendor data, internal
commercial data, raw market data, contracts, or real business strategy
parameters.

## Validation

- [ ] `ruff check .`
- [ ] `pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security`
- [ ] `python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"`

# apps/api

FastAPI process entrypoint.

## Owns

- ASGI app import path: `from apps.api.main import app`
- deployment/runtime entrypoint for the backend API service

## Does Not Own

- route implementation details;
- domain logic;
- DB sessions;
- connector execution.

Those belong under `src/eurogas_nexus`.

## Validation

```powershell
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

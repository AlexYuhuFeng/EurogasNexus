# apps

Process entrypoints live here.

## Current

- `api/`: active FastAPI backend service entrypoint.

## Reserved

- `worker/`: future background worker process.
- `scheduler/`: future scheduled job process.

Do not add business logic directly under `apps/`. Entrypoints should delegate
into `src/eurogas_nexus`.

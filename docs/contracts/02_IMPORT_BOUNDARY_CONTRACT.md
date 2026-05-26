# Import Boundary Contract

## Direction

Preferred import direction:

```text
apps -> api -> application -> domain -> core
api -> core
application -> infrastructure interfaces only
infrastructure -> core
tests -> any package under test
```

## Import-Safe Rule

Importing `apps.api.main` must not:

- open database connections;
- open network sockets;
- call external APIs;
- call LLM providers;
- read secrets from remote stores;
- submit orders or nominations;
- mutate persistent state.

## Dependency Boundaries

- `core` must not import `api`, `db`, `infrastructure`, or domain modules.
- `domain` must not import FastAPI, SQLAlchemy sessions, HTTP clients, or
  infrastructure adapters.
- `api` may import application services, core models, and route registration.
- `db` owns SQLAlchemy mapping and migration support, but import must remain
  side-effect free.
- `infrastructure` owns adapters, but V1.0 may only define inert boundaries.
- SDK and CLI code must call the backend API rather than importing internal
  domain modules.
- Connectors must not perform analytics.

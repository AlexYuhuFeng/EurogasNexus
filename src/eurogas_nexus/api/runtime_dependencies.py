"""Deterministic, import-only initialization of the runtime dependency graph.

Evidence
--------
CI run ``36878083383`` (baseline ``58afd8a``) failed the in-process API load
smoke with a CPython 3.11 ``_ModuleLock('sqlalchemy.exc')`` import deadlock:
the first concurrent requests reached the lazily imported runtime database
layer from FastAPI's worker threads at the same time. The route handlers keep
their database imports lazy on purpose - importing the API must not load the
DB layer (``tests/contract/test_db_foundation.py``) - so the fix is not to
make those imports eager per module, but to complete them once, on a single
thread, during application startup, before the ASGI server accepts requests.

What this module does
---------------------
:func:`initialize_runtime_dependencies` imports the runtime database
dependency graph (the modules the request paths would otherwise import
lazily) and records that it ran. It is idempotent and called from the
application lifespan startup, which every documented deployment server
(uvicorn) runs before it serves its first request.

What this module must never do
------------------------------
It must not resolve a database URL, create an engine or session factory, open
a connection or socket, run migrations, or write any state. Importing the
graph only defines SQLAlchemy mappings, which is what makes it safe to run on
startup in every profile - including DB-less ones.
"""

from __future__ import annotations

import importlib
import threading

#: Runtime dependency modules that request paths reach lazily. Only required
#: (never optional-extra) dependencies belong here, and every entry must be
#: import-safe: importing it performs no I/O. ``sqlalchemy.exc`` and
#: ``sqlalchemy.orm`` are named explicitly because the evidenced deadlock
#: ended in ``sqlalchemy.exc`` even though the entry point was the DB package.
RUNTIME_DEPENDENCY_MODULES: tuple[str, ...] = (
    "sqlalchemy.exc",
    "sqlalchemy.orm",
    "eurogas_nexus.db",
    "eurogas_nexus.db.session",
    "eurogas_nexus.db.models",
)

_INITIALIZED = False
_LOCK = threading.Lock()


def initialize_runtime_dependencies() -> None:
    """Import the runtime dependency graph once, before concurrent requests.

    Idempotent and thread-safe: the first caller imports the graph on its own
    thread while later callers wait, so no two threads can enter the import
    machinery for the same modules concurrently. Returns after the modules are
    in ``sys.modules``; a failed import propagates and fails startup loudly
    rather than leaving a half-initialized process.
    """

    global _INITIALIZED
    if _INITIALIZED:
        return
    with _LOCK:
        if _INITIALIZED:
            return
        for module_name in RUNTIME_DEPENDENCY_MODULES:
            importlib.import_module(module_name)
        _INITIALIZED = True


def runtime_dependencies_initialized() -> bool:
    """Whether :func:`initialize_runtime_dependencies` has completed."""

    return _INITIALIZED

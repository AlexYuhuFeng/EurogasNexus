"""No synchronous database call runs on the API's event loop.

The event loop serves every request and every live-update stream of a process: a blocking
database call in an ``async def`` handler, dependency, middleware or lifespan hook stalls all
of them (the demo measured 4 to 6 s pages and 502 errors when the streams did this). Blocking
work goes to the thread pool (``run_in_threadpool``), into a plain ``def`` handler (the
framework runs those in the pool), or to the process's stream poller (``api.stream_hub``).

This scan looks at the body of every ``async def`` under ``src/eurogas_nexus/api`` (nested
plain functions excluded: they are what gets handed to the pool) for calls that open or use a
database session.
"""

from __future__ import annotations

import ast
from pathlib import Path

API = Path(__file__).resolve().parents[2] / "src" / "eurogas_nexus" / "api"

#: Calls that open or use a database session or engine.
BLOCKING_NAMES = frozenset(
    {
        "get_session_factory",
        "_session_factory",
        "session_scope",
        "get_engine",
        "record_audit_event",
        "fail_orphaned_jobs_quietly",
        "dispose_cached_engines",
    }
)
#: Methods that, called on a session or engine, block.
BLOCKING_METHODS = frozenset({"query", "execute", "commit", "flush", "scalar", "scalars"})
SESSION_NAMES = frozenset({"session", "db", "db_session", "connection", "conn", "engine"})


def _calls_outside_nested_functions(node: ast.AST):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Call):
            yield child
        yield from _calls_outside_nested_functions(child)


def _blocking(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name) and func.id in BLOCKING_NAMES:
        return func.id
    if isinstance(func, ast.Attribute):
        if func.attr in BLOCKING_NAMES:
            return func.attr
        owner = func.value
        if (
            func.attr in BLOCKING_METHODS
            and isinstance(owner, ast.Name)
            and owner.id in SESSION_NAMES
        ):
            return f"{owner.id}.{func.attr}"
    return None


def test_no_async_def_in_the_api_calls_the_database_on_the_event_loop() -> None:
    found: list[str] = []
    for path in sorted(API.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for call in _calls_outside_nested_functions(node):
                name = _blocking(call)
                if name:
                    found.append(f"{path.relative_to(API)}:{call.lineno} {node.name} -> {name}")
    assert not found, "blocking database calls on the event loop:\n" + "\n".join(found)


def test_the_scan_sees_a_blocking_call() -> None:
    sample = ast.parse(
        "async def handler():\n"
        "    with get_session_factory()() as session:\n"
        "        session.query(1)\n"
        "    def offloaded():\n"
        "        session.commit()\n"
    )
    handler = sample.body[0]
    names = [_blocking(call) for call in _calls_outside_nested_functions(handler)]
    assert "get_session_factory" in names and "session.query" in names
    assert "session.commit" not in names

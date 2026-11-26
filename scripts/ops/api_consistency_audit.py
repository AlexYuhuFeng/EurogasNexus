"""API consistency audit (QA-03): envelope, errors, pagination, timestamps, money and units.

    python scripts/ops/api_consistency_audit.py [--postgres URL] [--json out.json]

Two passes over the application's own routes:

1. **Static**, every public operation: pagination parameter names (from the OpenAPI
   document), and how each route module raises errors (``HTTPException`` with a string
   ``detail`` or a ``{"code": ...}`` dict).
2. **Probe**, every GET without a path parameter, on the demo desk (``seed_demo_desk``)
   in a disposable store: the response has the ``data``/``meta`` envelope; every
   timestamp-like value (keys ending ``_utc``, ``_at``, ``as_of``, ``timestamp``) is
   ISO-8601 with ``Z`` or an offset; a numeric money or price field has a unit or
   currency beside it (``unit``, ``currency``, or a unit in its own name).

With ``--postgres`` the probe runs on PostgreSQL in a throwaway schema (dropped at the
end), so timestamps come back as the production driver returns them; without it, on
SQLite, where stored timestamps have no offset and the timestamp check is not meaningful
for values read back from the store (the report says so).

Read-only against the application: it writes only the disposable store it creates.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import secrets
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

PAGINATION = {"limit", "offset", "cursor", "page", "page_size", "after", "before",
              "after_id", "before_id", "next", "max_rows", "top"}
TIME_KEY = re.compile(r"(_utc|_at|^as_of|_as_of|timestamp|^observed|^received)$")
ISO_AWARE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONEY_KEY = re.compile(r"(^|_)(price|pnl|exposure|limit|headroom|margin|cost|value|amount|mark)"
                       r"($|_)")
UNIT_IN_NAME = re.compile(r"_(gbp|eur|usd|mwh|gwh|kwh|mcm|mscm|pct|percent|th|p_th|mmbtu|"
                          r"mw|twh|bcm|per_day|d|mwh_d|ratio|count|days|hours|months)($|_)")
UNIT_SIBLINGS = {"unit", "currency", "price_unit", "quantity_unit", "native_unit",
                 "unit_mwh", "comparison_unit", "comparison_currency", "base_currency"}


def static_pass(app) -> dict:
    schema = app.openapi()
    operations = 0
    pagination: dict[str, list[str]] = defaultdict(list)
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operations += 1
            names = {p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"}
            style = tuple(sorted(names & PAGINATION))
            if style:
                pagination[" + ".join(style)].append(f"{method.upper()} {path}")
    errors = {"string_detail": defaultdict(int), "dict_detail": defaultdict(int)}
    for module in sorted((ROOT / "src/eurogas_nexus/api/routes").rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException":
                detail = next((kw.value for kw in node.keywords if kw.arg == "detail"), None)
                name = module.relative_to(ROOT / "src/eurogas_nexus/api/routes").as_posix()
                if isinstance(detail, ast.Dict):
                    errors["dict_detail"][name] += 1
                elif detail is not None:
                    errors["string_detail"][name] += 1
    return {
        "paths": len(schema["paths"]),
        "operations": operations,
        "pagination": {key: sorted(value) for key, value in sorted(pagination.items())},
        "errors": {kind: dict(sorted(counts.items())) for kind, counts in errors.items()},
    }


def _walk(value, path, findings, *, check_time: bool):
    if isinstance(value, dict):
        keys = set(value)
        for key, item in value.items():
            here = f"{path}.{key}"
            if (check_time and isinstance(item, str) and TIME_KEY.search(key)
                    and not ISO_AWARE.match(item) and not ISO_DATE.match(item)):
                findings["timestamp"].add((re.sub(r"\[\d+\]", "[]", here), item[:32]))
            if (isinstance(item, int | float) and not isinstance(item, bool)
                    and MONEY_KEY.search(key) and not UNIT_IN_NAME.search(key)
                    and not key.endswith(("row_limit", "_score", "_count"))
                    and not keys & UNIT_SIBLINGS):
                findings["unitless_money"].add(re.sub(r"\[\d+\]", "[]", here))
            _walk(item, here, findings, check_time=check_time)
    elif isinstance(value, list):
        for index, item in enumerate(value[:50]):
            _walk(item, f"{path}[{index}]", findings, check_time=check_time)


def probe_pass(postgres: str | None) -> dict:
    from sqlalchemy import event, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.session import get_engine

    def create_engine(target):  # a bounded connect and keepalives, no statement limit
        return get_engine(target, one_off=True, statement_timeout=None)

    schema = None
    if postgres:
        schema = f"api_audit_{uuid4().hex[:12]}"
        url = postgres

        @event.listens_for(Engine, "connect")
        def _search_path(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute(f"SET search_path TO {schema}")
            cursor.close()

        bootstrap = create_engine(url)
        with bootstrap.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
        bootstrap.dispose()
    else:
        url = f"sqlite+pysqlite:///{tempfile.mkdtemp()}/audit.sqlite"
    # A throwaway deployment token for this process only (the legacy single-trust view).
    token = secrets.token_hex(16)
    os.environ.update({"RUNTIME_STORE_DATABASE_URL": url, "EUROGAS_NEXUS_DEMO_MARKS": "true",
                       "EUROGAS_NEXUS_ENV": "development",
                       "EUROGAS_NEXUS_PUBLIC_API_TOKEN": token})
    for name in ("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        os.environ.pop(name, None)
    import eurogas_nexus.db.models  # noqa: F401
    from eurogas_nexus.db.base import Base

    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
        spec = importlib.util.spec_from_file_location(
            "seed_demo_desk", ROOT / "scripts/demo/seed_demo_desk.py")
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        with Session(engine) as session:
            seed.seed(session, datetime.now(UTC))
            session.commit()
        from fastapi.testclient import TestClient

        from eurogas_nexus.api.app import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        results = []
        for path, item in sorted(app.openapi()["paths"].items()):
            if "get" not in item or "{" in path or not path.startswith("/api/"):
                continue
            if path.startswith("/api/stream/") or path.startswith("/api/auth/oidc/"):
                continue  # server-sent event streams never end; OIDC redirects are not JSON
            response = client.get(path, headers={"X-Eurogas-Api-Key": token})
            entry = {"path": path, "status": response.status_code}
            try:
                body = response.json()
            except ValueError:
                entry["body"] = "not JSON"
                results.append(entry)
                continue
            findings: dict[str, set] = {"timestamp": set(), "unitless_money": set()}
            if response.status_code == 200:
                entry["envelope"] = isinstance(body, dict) and {"data", "meta"} <= set(body)
                _walk(body.get("data") if isinstance(body, dict) else body, "data", findings,
                      check_time=True)
            else:
                entry["error_keys"] = (
                    sorted(body) if isinstance(body, dict) else type(body).__name__
                )
                entry["detail_type"] = type(body.get("detail")).__name__ if isinstance(
                    body, dict) else None
                detail = body.get("detail") if isinstance(body, dict) else None
                entry["code"] = (detail.get("code") if isinstance(detail, dict) else
                                 body.get("error") if isinstance(body, dict) else None)
            entry["timestamp"] = sorted(findings["timestamp"])[:6]
            entry["unitless_money"] = sorted(findings["unitless_money"])[:6]
            results.append(entry)
        return {"store": "postgresql" if postgres else "sqlite", "probed": results}
    finally:
        engine.dispose()
        if schema:
            event.remove(Engine, "connect", _search_path)
            cleanup = create_engine(postgres)
            with cleanup.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            cleanup.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--postgres", help="PostgreSQL URL; a throwaway schema is used")
    parser.add_argument("--json", type=Path, help="write the full result here")
    args = parser.parse_args(argv)
    from eurogas_nexus.api.app import create_app

    report = {"static": static_pass(create_app()), "probe": probe_pass(args.postgres)}
    text_out = json.dumps(report, indent=1, default=str)
    if args.json:
        args.json.write_text(text_out, encoding="utf-8")
    probe = report["probe"]["probed"]
    print(json.dumps({
        "paths": report["static"]["paths"], "operations": report["static"]["operations"],
        "probed_gets": len(probe),
        "no_envelope": [p["path"] for p in probe if p.get("envelope") is False],
        "non_200": {p["path"]: p["status"] for p in probe if p["status"] != 200},
        "timestamp_findings": {p["path"]: p["timestamp"] for p in probe if p["timestamp"]},
        "unitless_money": {p["path"]: p["unitless_money"] for p in probe if p["unitless_money"]},
        "pagination_styles": {k: len(v) for k, v in report["static"]["pagination"].items()},
    }, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

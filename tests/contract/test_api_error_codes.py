"""Every refusal a route raises names a stable code (backend audit 2026-11-26, finding A2).

A client translates a refusal by its code and the values it names (``params``), keeping the
English text only as a fallback. A route that raised ``HTTPException(404, "Node 'x' not
found.")`` gave the client nothing to translate by: 82 such sites had accumulated because
nothing stopped the next one. This gate does: in ``src/eurogas_nexus``, an
``HTTPException`` whose ``detail`` is a literal, an f-string or ``str(exc)`` is refused
(raise ``api.errors.ApiError``), and a dict ``detail`` must carry ``code``, ``error`` or
``error_code``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "eurogas_nexus"


def _http_exceptions():
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "HTTPException":
                continue
            detail = next((kw.value for kw in node.keywords if kw.arg == "detail"), None)
            if detail is None and len(node.args) >= 2:
                detail = node.args[1]
            yield f"{path.relative_to(ROOT)}:{node.lineno}", detail


def test_no_route_raises_english_text_without_a_code() -> None:
    offenders = [
        f"{where}: {ast.unparse(detail)[:80]}"
        for where, detail in _http_exceptions()
        if isinstance(detail, ast.Constant | ast.JoinedStr | ast.BinOp)
        or (isinstance(detail, ast.Call) and getattr(detail.func, "id", "") == "str")
    ]
    assert offenders == []


def test_a_dict_detail_names_its_code() -> None:
    offenders = []
    for where, detail in _http_exceptions():
        if not isinstance(detail, ast.Dict) or None in detail.keys:
            continue
        keys = {key.value for key in detail.keys if isinstance(key, ast.Constant)}
        if not keys & {"code", "error", "error_code"}:
            offenders.append(f"{where}: {sorted(keys)}")
    assert offenders == []

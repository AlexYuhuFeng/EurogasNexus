#!/usr/bin/env python
"""Generate docs/sdk/REFERENCE.md from the public surface of ``eurogas_nexus_sdk``.

The reference is built from the installed or source SDK, not written by hand, so it cannot
drift from the code. For every public module it lists each public function with its
signature, the HTTP method and ``/api`` path it calls (read from the source), its return
type and the first line of its docstring, followed by the module's public models.

Usage (from the repository root):

    python scripts/docs/generate_sdk_reference.py                  # print to stdout
    python scripts/docs/generate_sdk_reference.py --output docs/sdk/REFERENCE.md
    python scripts/docs/generate_sdk_reference.py --check docs/sdk/REFERENCE.md

``--check`` exits 1 when the file differs from what the code would generate, so CI can
refuse a stale reference. The script needs only the SDK's own dependencies (pydantic and
httpx). It always imports the SDK from ``packages/python-sdk/src`` in this checkout, even
when another copy is installed, so the reference describes the source beside it.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import pkgutil
import re
import sys
import typing
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_SRC = REPO_ROOT / "packages" / "python-sdk" / "src"
PACKAGE = "eurogas_nexus_sdk"

# Modules that are implementation details even though their names are public-looking.
PRIVATE_MODULES = {"_http", "_transport"}

# Names re-exported for convenience at the package root.
ROOT_EXPORTS_NOTE = (
    "`eurogas_nexus_sdk` re-exports `fetch_health`, `HealthPayload`, `SdkResult`, "
    "`ResponseMeta` and `SdkProtocolError`. Everything else is imported from its module."
)

# Functions whose route is chosen at run time, so the source holds no single literal path.
SPECIAL_CALLS = {
    "functional.operate": "one of `functional.OPERATIONS` (`/api/functional-runs`, "
    "`/api/functional-models`, `/api/jobs/{id}/cancel`)",
    "streaming.iter_sse": "none (parses lines you pass in)",
    "streaming.stream_events": "`GET /api/{path}` (an SSE stream such as `stream/quotes`)",
}

_HTTP_VERBS = {"get", "post", "put", "patch", "delete"}
_PATH_RE = re.compile(r"/api/[^\s\"'?`]*")


@dataclass
class Endpoint:
    method: str
    path: str


@dataclass
class FunctionDoc:
    name: str
    signature: str
    returns: str
    summary: str
    endpoints: list[Endpoint] = field(default_factory=list)
    has_docstring: bool = True
    has_annotations: bool = True


@dataclass
class ModelDoc:
    name: str
    summary: str
    fields: list[str]


def _import_sdk():
    """Import the SDK from this checkout, so the reference describes the source beside it."""

    sys.path.insert(0, str(SDK_SRC))
    module = importlib.import_module(PACKAGE)
    origin = Path(module.__file__).resolve()
    if not origin.is_relative_to(SDK_SRC.resolve()):
        raise SystemExit(f"imported {PACKAGE} from {origin}, not from {SDK_SRC}")
    return module


def _first_line(doc: str | None) -> str:
    if not doc:
        return ""
    for line in inspect.cleandoc(doc).splitlines():
        if line.strip():
            return line.strip()
    return ""


def _fstring_text(node: ast.AST) -> str | None:
    """Render a string constant or f-string as text, with ``{...}`` for each placeholder."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                inner = value.value
                # ``{base_url.rstrip('/')}`` is the origin, not a path parameter.
                text = ast.unparse(inner)
                parts.append("" if "base_url" in text else "{" + _placeholder(text) + "}")
        return "".join(parts)
    return None


def _placeholder(expression: str) -> str:
    match = re.search(r"quote\((\w+)", expression)
    if match:
        return match.group(1)
    return re.sub(r"[^\w]", "", expression.split("(")[0].split(".")[-1]) or "value"


def _normalize_path(path: str) -> str:
    # ``.../tso-tariffs{query}``: a placeholder glued to a segment is a query string.
    return re.sub(r"(?<!/)\{[^}]*\}$", "", path).rstrip("/")


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        owner = ast.unparse(func.value)
        return f"{owner}.{func.attr}"
    return ""


def _path_from_call(node: ast.Call) -> str | None:
    """Return the ``/api/...`` path a call builds, if one of its arguments names it."""

    name = _call_name(node)
    for arg in node.args:
        text = _fstring_text(arg)
        if text is None:
            continue
        match = _PATH_RE.search(text)
        if match:
            return _normalize_path(match.group(0))
        if name.endswith(("api_url", "_url")) or name in {"_get", "_post", "_put", "_patch"}:
            if text and not text.startswith("http"):
                return "/api/" + text.lstrip("/")
    return None


def _method_of_call(node: ast.Call, helper_methods: dict[str, str]) -> str | None:
    name = _call_name(node)
    if name.startswith("_http.") and name.split(".", 1)[1] in _HTTP_VERBS:
        return name.split(".", 1)[1].upper()
    if name.startswith("httpx.") and name.split(".", 1)[1] in _HTTP_VERBS:
        return name.split(".", 1)[1].upper()
    if name == "httpx.stream" and node.args:
        text = _fstring_text(node.args[0])
        return text.upper() if text else None
    if name.endswith("get_envelope"):
        return "GET"
    return helper_methods.get(name)


def _helper_methods(tree: ast.Module) -> dict[str, str]:
    """Map module-private helper functions to the HTTP verb they use."""

    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_"):
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                method = _method_of_call(call, {})
                if method:
                    result[node.name] = method
                    break
    return result


def _endpoints(func_node: ast.FunctionDef, helper_methods: dict[str, str]) -> list[Endpoint]:
    """Read the HTTP verb and ``/api`` path a function calls from its source."""

    paths: list[str] = []
    methods: list[str] = []
    docstring_nodes = {
        id(stmt.value)
        for stmt in func_node.body[:1]
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
    }
    for node in ast.walk(func_node):
        if isinstance(node, ast.JoinedStr):
            docstring_nodes.update(id(part) for part in node.values)
    for node in ast.walk(func_node):
        if id(node) in docstring_nodes:
            continue
        if isinstance(node, ast.Call):
            method = _method_of_call(node, helper_methods)
            if method:
                methods.append(method)
            path = _path_from_call(node)
            if path:
                paths.append(path)
        elif isinstance(node, (ast.Constant, ast.JoinedStr)):
            text = _fstring_text(node)
            match = _PATH_RE.search(text or "")
            if match:
                paths.append(_normalize_path(match.group(0)))
    found: list[Endpoint] = []
    seen: set[tuple[str, str]] = set()
    unique_paths = list(dict.fromkeys(paths))
    for index, path in enumerate(unique_paths):
        method = methods[min(index, len(methods) - 1)] if methods else "?"
        key = (method, path)
        if key not in seen:
            seen.add(key)
            found.append(Endpoint(method, path))
    return found


def _called_public_functions(func_node: ast.FunctionDef, public: set[str]) -> list[str]:
    names: list[str] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in public and node.func.id != func_node.name:
                names.append(node.func.id)
    return names


def _format_annotation(annotation: object) -> str:
    if annotation is inspect.Signature.empty:
        return "(not annotated)"
    if isinstance(annotation, str):
        return annotation
    text = inspect.formatannotation(annotation)
    text = re.sub(r"eurogas_nexus_sdk\.[\w.]+\.(\w+)", r"\1", text)
    return text.replace("typing.", "")


def _signature(obj: object) -> str:
    try:
        sig = inspect.signature(obj, eval_str=True)
    except (TypeError, ValueError, NameError):
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            return "(...)"
    text = str(sig).replace("'", "")
    text = re.sub(r"eurogas_nexus_sdk\.[\w.]+\.(\w+)", r"\1", text)
    return text.replace("typing.", "")


def _module_doc(module) -> tuple[list[FunctionDoc], list[ModelDoc]]:
    source_path = Path(inspect.getsourcefile(module))
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    helper_methods = _helper_methods(tree)
    func_nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    # Module-level aliases such as ``compute_x = calculate_x``.
    aliases: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name)
            and node.value.id in func_nodes
        ):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    aliases[target.id] = node.value.id
    public = set(func_nodes)
    functions: list[FunctionDoc] = []
    for name, node in func_nodes.items():
        obj = getattr(module, name, None)
        if obj is None:
            continue
        try:
            hints = typing.get_type_hints(obj)
        except Exception:  # noqa: BLE001 - unresolved forward refs only affect display
            hints = {}
        returns = hints.get("return", inspect.signature(obj).return_annotation)
        functions.append(
            FunctionDoc(
                name=name,
                signature=_signature(obj),
                returns=_format_annotation(returns),
                summary=_first_line(obj.__doc__),
                endpoints=_endpoints(node, helper_methods)
                or [
                    endpoint
                    for callee in _called_public_functions(node, public)
                    for endpoint in _endpoints(func_nodes[callee], helper_methods)
                ],
                has_docstring=bool(obj.__doc__),
                has_annotations=any(arg.annotation for arg in node.args.args) or bool(node.returns),
            )
        )
    by_name = {func.name: func for func in functions}
    for alias, target in aliases.items():
        original = by_name[target]
        functions.append(
            FunctionDoc(
                name=alias,
                signature=original.signature,
                returns=original.returns,
                summary=f"Alias of `{target}`.",
                endpoints=original.endpoints,
                has_docstring=original.has_docstring,
                has_annotations=original.has_annotations,
            )
        )
    models: list[ModelDoc] = []
    for name, obj in vars(module).items():
        if name.startswith("_") or not inspect.isclass(obj) or obj.__module__ != module.__name__:
            continue
        fields = list(getattr(obj, "model_fields", {}) or {})
        if not fields and hasattr(obj, "__dataclass_fields__"):
            fields = list(obj.__dataclass_fields__)
        models.append(ModelDoc(name=name, summary=_first_line(obj.__doc__), fields=fields))
    return functions, models


def _anchor(text: str) -> str:
    return re.sub(r"[^a-z0-9_ -]", "", text.lower()).replace(" ", "-")


def render() -> str:
    sdk = _import_sdk()
    modules = sorted(
        info.name for info in pkgutil.iter_modules(sdk.__path__) if info.name not in PRIVATE_MODULES
    )
    sections: list[str] = []
    index_rows: list[str] = []
    totals = {"functions": 0, "models": 0, "undocumented": 0, "unannotated": 0}
    for name in modules:
        module = importlib.import_module(f"{PACKAGE}.{name}")
        functions, models = _module_doc(module)
        totals["functions"] += len(functions)
        totals["models"] += len(models)
        totals["undocumented"] += sum(not f.has_docstring for f in functions)
        totals["unannotated"] += sum(not f.has_annotations for f in functions)
        purpose = _first_line(module.__doc__) or "(no module docstring)"
        index_rows.append(
            f"| [`{name}`](#{_anchor(name)}) | {len(functions)} | {len(models)} | {purpose} |"
        )
        lines = [f"## {name}", "", purpose, "", f"`from {PACKAGE}.{name} import ...`", ""]
        if functions:
            lines += ["| Function | Calls | Returns | Purpose |", "|---|---|---|---|"]
            for func in functions:
                calls = SPECIAL_CALLS.get(f"{name}.{func.name}") or "<br>".join(
                    f"`{e.method} {e.path}`" for e in func.endpoints
                )
                calls = calls or "none"
                summary = func.summary or "_No docstring._"
                lines.append(f"| `{func.name}` | {calls} | `{func.returns}` | {summary} |")
            lines += ["", "Signatures:", "", "```python"]
            for func in functions:
                lines.append(f"{func.name}{func.signature}")
            lines += ["```", ""]
        if models:
            lines += ["Models:", ""]
            for model in models:
                summary = f" {model.summary}" if model.summary else ""
                lines.append(f"- `{model.name}` ({len(model.fields)} fields).{summary}")
            lines.append("")
        sections.append("\n".join(lines))
    header = [
        "# Python SDK reference",
        "",
        "<!-- Generated by scripts/docs/generate_sdk_reference.py. Do not edit by hand. -->",
        "",
        "Generated from the source of `eurogas_nexus_sdk`. Each function takes the server "
        "origin (`base_url`, for example `http://127.0.0.1:8000`, without `/api`) as its first "
        "argument and returns pydantic models or plain JSON. Authentication headers come from "
        "environment variables; see [Authentication](AUTHENTICATION.md). Errors are raised as "
        "`NexusAPIError` (an `httpx.HTTPStatusError`), `httpx.TransportError`, "
        "`pydantic.ValidationError` or "
        "`SdkProtocolError`; see [Troubleshooting](TROUBLESHOOTING.md).",
        "",
        ROOT_EXPORTS_NOTE,
        "",
        "Field-level descriptions are in each model's docstring: "
        "`help(eurogas_nexus_sdk.market.MarketQuote)`.",
        "",
        f"Surface: {len(modules)} modules, {totals['functions']} public functions, "
        f"{totals['models']} public models. {totals['undocumented']} functions have no "
        f"docstring and {totals['unannotated']} have no type annotations.",
        "",
        "| Module | Functions | Models | Purpose |",
        "|---|---|---|---|",
        *index_rows,
        "",
    ]
    return "\n".join(header) + "\n" + "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--output", type=Path, help="write the reference to this file")
    group.add_argument("--check", type=Path, help="exit 1 if this file is out of date")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = args.check.read_text(encoding="utf-8") if args.check.exists() else ""
        if current != text:
            print(f"{args.check} is out of date; rerun with --output {args.check}")
            return 1
        print(f"{args.check} is up to date")
        return 0
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Architecture V2 architecture fitness functions (static, dependency-free).

Task W0-03 (part 1). This module encodes the Architecture V2 fitness functions
listed in ``docs/engineering/Architecture-V2/10_DOCUMENTATION_NFR_TESTING.md``
section 7 and ``docs/engineering/Architecture-V2/14_VALIDATION_PACK.md``
section A. The matching gap inventory (what is covered, what is an open gap and
why) lives in ``docs/engineering/Architecture-V2/W0-03_FITNESS_GAPS.md``.

Why every check here is static
------------------------------

The module must import and pass with pytest plus the Python standard library, so
it never imports ``fastapi``, ``pydantic``, ``sqlalchemy`` or anything under
``src/``. Repository sources are read as text and parsed with ``ast``, ``re``
and ``json``. Behavioural coverage for the same concerns lives in the runtime
suites cited in the gap inventory (for example
``tests/security/test_permissions_registry.py``,
``tests/security/test_provider_credentials_api.py`` and
``tests/security/test_llm_provider_gate.py``); those suites need the full
dependency stack and are not duplicated here.

Only invariants that genuinely hold at the inspected revision are asserted. A
check that would fail today is recorded as an open gap in the inventory instead
of being written here as a failing test.

Fitness function to test index
------------------------------

* FF1  clients do not import backend internals
* FF2  clients do not call provider/vendor endpoints
* FF3  every public API route has an access declaration
* FF4  credential responses are write-only
* FF5  no critical business computation in the React client
* FF6  Tauri commands stay within a bounded host allowlist
* FF7  backend module dependency direction
* FF8  version/config consistency (already covered elsewhere; not duplicated)
* FF9  ExperienceProfile cannot grant capability (open gap; nothing to assert)
* FF10 AI/agent invocation rechecks authority before calling a provider
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "eurogas_nexus"
WEB_SRC = ROOT / "clients" / "web" / "src"
WEB_TESTS = ROOT / "clients" / "web" / "tests"
DESKTOP_TAURI = ROOT / "clients" / "desktop" / "src-tauri"
FITNESS_GAP_DOC = ROOT / "docs" / "engineering" / "Architecture-V2" / "W0-03_FITNESS_GAPS.md"

# Generated or third-party trees that are never treated as authored source.
_GENERATED_PARTS = frozenset({"node_modules", "gen", "icons", "__pycache__", ".pytest_cache"})
_GENERATED_NAMES = frozenset({"package-lock.json", "Cargo.lock"})


def _read_text(path: Path) -> str:
    """Read a repository file as text without failing on a byte-order mark."""

    return path.read_text(encoding="utf-8-sig", errors="replace")


def _python_tree(path: Path) -> ast.Module:
    """Parse a Python source file into an AST with the file name for context."""

    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_generated(path: Path) -> bool:
    """Whether a path belongs to a generated or vendored tree."""

    return bool(_GENERATED_PARTS.intersection(path.parts)) or path.name in _GENERATED_NAMES


def _client_sources() -> list[Path]:
    """Authored client/host sources in scope for the client-side fitness checks.

    Scope: the shared Web workspace (``clients/web/src``, ``clients/web/tests``),
    the Web build/config files and the Tauri host under
    ``clients/desktop/src-tauri``. Generated trees, lock files, icons and
    client prose (``clients/README.md``) are deliberately out of scope; the gap
    inventory records that limit.
    """

    files: list[Path] = []
    for root in (WEB_SRC, WEB_TESTS, DESKTOP_TAURI / "src", DESKTOP_TAURI / "capabilities"):
        files.extend(sorted(path for path in root.rglob("*") if path.is_file()))
    for extra in (
        ROOT / "clients" / "web" / "index.html",
        ROOT / "clients" / "web" / "vite.config.ts",
        ROOT / "clients" / "web" / "package.json",
        ROOT / "clients" / "desktop" / "package.json",
        DESKTOP_TAURI / "tauri.conf.json",
        DESKTOP_TAURI / "tauri.offline.conf.json",
        DESKTOP_TAURI / "Cargo.toml",
    ):
        if extra.is_file():
            files.append(extra)
    return [
        path
        for path in files
        if path.suffix.lower() in _CLIENT_SOURCE_SUFFIXES and not _is_generated(path)
    ]


_CLIENT_SOURCE_SUFFIXES = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".rs", ".html", ".json", ".css", ".toml"}
)


# ---------------------------------------------------------------------------
# FF1 — clients cannot import backend internals
# ---------------------------------------------------------------------------

# Case-sensitive on purpose: the clients legitimately mention the *environment
# variables* ``EUROGAS_NEXUS_*`` (for example the deployment-config variable in
# ``clients/desktop/src-tauri/src/main.rs`` and the token placeholder in
# ``clients/web/src/components/SettingsCenter.tsx``). Python module names are
# lower case, so a case-sensitive scan separates a real import from a variable.
BACKEND_INTERNAL_TOKENS = (
    "eurogas_nexus",
    "eurogas_nexus_sdk",
    "eurogas-nexus-sdk",
    "packages/python-sdk",
    "src/eurogas_nexus",
)


def test_clients_do_not_import_backend_internals() -> None:
    """FF1: no client source references the backend package, CLI or Python SDK."""

    sources = _client_sources()
    assert len(sources) >= 100, f"client source scope collapsed to {len(sources)} files"
    assert WEB_SRC / "api" / "client.ts" in sources

    offenders = [
        f"{path.relative_to(ROOT).as_posix()} -> {token}"
        for path in sources
        for token in BACKEND_INTERNAL_TOKENS
        if token in _read_text(path)
    ]

    assert offenders == []


# ---------------------------------------------------------------------------
# FF2 — the client cannot call provider/vendor APIs directly
# ---------------------------------------------------------------------------

# Every host below is taken from code or documentation that already exists in the
# repository, so the list is evidence-based rather than guessed. The evidence
# file is asserted to still contain the host, which keeps the list honest when
# backend provider endpoints move.
VENDOR_ENDPOINT_EVIDENCE: dict[str, str] = {
    "api.deepseek.com": "src/eurogas_nexus/llm/deepseek.py",
    "www.ecb.europa.eu": "scripts/ops/ingest_public_sources.py",
    "transparency.entsog.eu": "scripts/ops/ingest_public_sources.py",
    "agsi.gie.eu": "scripts/ops/ingest_public_sources.py",
    "alsi.gie.eu": "scripts/ops/ingest_public_sources.py",
    "bblcompany.com": "src/eurogas_nexus/domain/route_cost/european_public_tariffs.py",
    "fluxys.com": "src/eurogas_nexus/domain/route_cost/european_public_tariffs.py",
    "gasgovernance.co.uk": "src/eurogas_nexus/domain/route_cost/uk_rules.py",
    "eex.com": "docs/ontology/europe-natural-gas.md",
    "theice.com": "docs/ontology/europe-natural-gas.md",
    "argusmedia.com": "docs/product/INDUSTRY_BENCHMARK.md",
    "trayport.com": "docs/product/INDUSTRY_BENCHMARK.md",
    "kpler.com": "docs/product/INDUSTRY_BENCHMARK.md",
}

# Provider identifiers from ``src/eurogas_nexus/api/routes/public/credentials.py``
# (the provider registry). A dependency whose package name carries one of these
# markers would put a vendor integration inside the client.
VENDOR_DEPENDENCY_MARKERS = (
    "entsog",
    "gie",
    "eex",
    "icis",
    "argus",
    "trayport",
    "kpler",
    "platts",
    "spglobal",
    "deepseek",
    "meteo",
)


@pytest.mark.parametrize("host", sorted(VENDOR_ENDPOINT_EVIDENCE))
def test_vendor_endpoint_list_is_anchored_in_repository_evidence(host: str) -> None:
    """FF2 support: every endpoint host in the fitness list is real repository evidence."""

    evidence = ROOT / VENDOR_ENDPOINT_EVIDENCE[host]
    assert evidence.is_file(), f"vendor endpoint evidence file missing: {evidence}"
    assert host in _read_text(evidence), (
        f"{host} is no longer present in {VENDOR_ENDPOINT_EVIDENCE[host]}"
    )


def test_clients_do_not_reference_vendor_endpoints() -> None:
    """FF2: no client source names a provider/vendor endpoint host."""

    sources = _client_sources()
    assert len(sources) >= 100, f"client source scope collapsed to {len(sources)} files"

    offenders = [
        f"{path.relative_to(ROOT).as_posix()} -> {host}"
        for path in sources
        for host in VENDOR_ENDPOINT_EVIDENCE
        if host in _read_text(path)
    ]

    assert offenders == []


def test_client_dependencies_carry_no_vendor_integration() -> None:
    """FF2: no declared client dependency is a provider/vendor integration."""

    packages: list[str] = []
    manifests = (
        ROOT / "clients" / "web" / "package.json",
        ROOT / "clients" / "desktop" / "package.json",
    )
    for manifest in manifests:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies"):
            packages.extend(payload.get(section, {}))

    assert packages, "no client dependencies found; the manifest scope is wrong"
    offenders = [
        name
        for name in packages
        if any(marker in name.lower() for marker in VENDOR_DEPENDENCY_MARKERS)
    ]

    assert offenders == []


# ---------------------------------------------------------------------------
# FF3 — every public API route has an access/permission declaration
# ---------------------------------------------------------------------------

PERMISSIONS_MODULE = SRC / "security" / "permissions.py"
PUBLIC_ROUTES_DIR = SRC / "api" / "routes" / "public"
ROUTE_PERMISSION_DEPENDENCY = SRC / "api" / "dependencies" / "route_permission.py"
ROUTE_PROFILES_MODULE = SRC / "api" / "route_profiles.py"
APP_MODULE = SRC / "api" / "app.py"

_ROUTE_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


def _tuple_entries(node: ast.AST) -> list[tuple[str, ...]]:
    """Flatten a literal tuple of string/enum-attribute tuples into name tuples.

    Handles both 2-tuples ``("path", Permission.X)`` and 3-tuples
    ``("METHOD", "path", Permission.X)``; enum members are recorded by attribute
    name (``PUBLIC``, ``READ``, ...).
    """

    entries: list[tuple[str, ...]] = []
    if not isinstance(node, ast.Tuple):
        return entries
    for element in node.elts:
        if not isinstance(element, ast.Tuple):
            continue
        values: list[str] = []
        for item in element.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)
            elif isinstance(item, ast.Attribute):
                values.append(item.attr)
            else:
                values.append("?")
        entries.append(tuple(values))
    return entries


def _permission_registry() -> tuple[list[str], list[tuple[str, str]]]:
    """Return (path patterns, method-scoped (method, path) overrides) from the registry.

    The registry is read statically so the check does not need to import
    ``eurogas_nexus.security.permissions`` (which is import-safe today, but the
    module must stay independent of ``src/``).
    """

    tree = _python_tree(PERMISSIONS_MODULE)
    patterns: list[str] = []
    method_overrides: list[tuple[str, str]] = []
    for node in tree.body:
        target = getattr(node, "target", None)
        name = getattr(target, "id", None)
        if name == "ROUTE_PERMISSIONS":
            patterns = [entry[0] for entry in _tuple_entries(node.value)]
        elif name == "METHOD_ROUTE_PERMISSIONS":
            method_overrides = [
                (entry[0].upper(), entry[1]) for entry in _tuple_entries(node.value)
            ]
    return patterns, method_overrides


def _registry_pattern_matches(path: str, pattern: str) -> bool:
    """Whether a route path is covered by one declared registry pattern.

    Mirrors ``eurogas_nexus.security.permissions`` matching modes: a pattern that
    ends with ``/`` is a prefix family, any other pattern is an exact match where
    ``{placeholder}`` stands for one path segment.
    """

    if pattern.endswith("/"):
        return path.startswith(pattern)
    parts = re.split(r"(\{[^}]+\})", pattern)
    expression = "".join(
        "[^/]+" if part.startswith("{") else re.escape(part) for part in parts
    )
    return re.compile(f"^{expression}$").match(path) is not None


def _router_prefix(tree: ast.Module) -> str:
    """Return the module-level ``router = APIRouter(prefix=...)`` prefix, if any."""

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if getattr(node.targets[0], "id", None) != "router":
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        for keyword in call.keywords:
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
    return ""


def _route_decorators(path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ((method, absolute path) routes, non-literal decorator arguments)."""

    tree = _python_tree(path)
    prefix = _router_prefix(tree)
    routes: list[tuple[str, str]] = []
    non_literal: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in _ROUTE_METHODS:
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "router":
                continue
            if not decorator.args:
                non_literal.append(f"{node.name}: missing path argument")
                continue
            argument = decorator.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                routes.append((decorator.func.attr, prefix + argument.value))
            else:
                non_literal.append(f"{node.name}: non-literal path")
    return routes, non_literal


def test_every_public_route_has_a_declared_permission() -> None:
    """FF3: every route under ``api/routes/public`` resolves to a registry pattern.

    Static equivalent of the registry coverage test in
    ``tests/security/test_permissions_registry.py``, which needs the FastAPI app;
    this variant also catches a route that is added without touching the
    registry even when the app cannot be imported.
    """

    patterns, _method_overrides = _permission_registry()
    assert len(patterns) >= 100, f"permission registry shrank to {len(patterns)} patterns"

    routes: list[tuple[str, str, str]] = []
    non_literal: list[str] = []
    for path in sorted(PUBLIC_ROUTES_DIR.rglob("*.py")):
        found, unclear = _route_decorators(path)
        non_literal.extend(f"{path.name}: {item}" for item in unclear)
        routes.extend(
            (path.relative_to(ROOT).as_posix(), method, route_path)
            for method, route_path in found
        )

    assert non_literal == [], "route paths must be literal strings for this check"
    assert len(routes) >= 150, f"public route scope collapsed to {len(routes)} decorators"

    unmatched = sorted(
        {
            f"{source} {method.upper()} {route_path}"
            for source, method, route_path in routes
            if not any(_registry_pattern_matches(route_path, pattern) for pattern in patterns)
        }
    )

    assert unmatched == []


def test_release_profile_wires_route_permission_enforcement() -> None:
    """FF3: the declared permission registry is enforced by *every* profile.

    The gap this function used to record - the dependency is only attached when ``require_auth`` is
    true, and only RELEASE set it, so the registry was documentation in development and internal
    (FF3-G2) - is **closed** by owner decision D1: every profile identifies its callers, and the one
    way to relax that is a deployment's own explicit statement
    (``EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS``), which the health payload reports. The assertions
    below therefore pin the closed state rather than the gap, and pin the opt-in as the only
    relaxation so a future profile cannot quietly reintroduce the old default.
    """

    tree = _python_tree(ROUTE_PROFILES_MODULE)
    profiles: dict[str, dict[str, object]] = {}
    for node in tree.body:
        if getattr(getattr(node, "target", None), "id", None) != "API_ROUTE_PROFILES":
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            name = getattr(key, "attr", None)
            if name is None or not isinstance(value, ast.Call):
                continue
            profiles[name] = {
                keyword.arg: getattr(keyword.value, "value", None)
                for keyword in value.keywords
                if keyword.arg is not None
            }

    assert set(profiles) >= {"DEVELOPMENT", "INTERNAL", "RELEASE"}
    # D1: no profile opts out. A profile that does not set the flag inherits the dataclass default,
    # which is True for the same reason.
    for name in ("DEVELOPMENT", "INTERNAL", "RELEASE"):
        assert profiles[name].get("require_auth") in (None, True), name

    profiles_source = _read_text(ROUTE_PROFILES_MODULE)
    assert "require_auth: bool = True" in profiles_source
    # The relaxation is a deployment setting, and it is reported rather than silent.
    assert "anonymous_allowed" in profiles_source

    app_source = _read_text(APP_MODULE)
    assert "Depends(require_route_permission)" in app_source
    assert "if route_profile.require_auth" in app_source

    dependency_source = _read_text(ROUTE_PERMISSION_DEPENDENCY)
    assert "permission_not_declared" in dependency_source


# ---------------------------------------------------------------------------
# FF4 — no plaintext credential response
# ---------------------------------------------------------------------------

CREDENTIAL_ROUTES_MODULE = SRC / "api" / "routes" / "public" / "credentials.py"

# Names that must never appear as a response key or as a returned record field.
FORBIDDEN_CREDENTIAL_RESPONSE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "credential",
        "encrypted_payload",
        "credential_fingerprint",
        "password",
        "plaintext",
        "secret",
        "token",
    }
)

# Keys the credential response builders are allowed to expose.
SAFE_CREDENTIAL_RESPONSE_KEYS = frozenset(
    {
        "configured",
        "credential_required",
        "default_model",
        "display_name",
        "label",
        "last_test_status",
        "last_tested_at_utc",
        "provider_id",
        "redacted_preview",
        "status",
    }
)

_RESPONSE_BUILDERS = ("_credential_status", "_provider_status")
_ENCRYPTION_CALL = "encrypt_credential_payload"


def test_credential_responses_never_expose_plaintext_secret_fields() -> None:
    """FF4: credential responses are metadata-only; the plaintext key is write-only."""

    tree = _python_tree(CREDENTIAL_ROUTES_MODULE)

    encryption_dicts: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != _ENCRYPTION_CALL:
            continue
        for argument in node.args:
            if isinstance(argument, ast.Dict):
                encryption_dicts.add(id(argument))
    assert encryption_dicts, f"{_ENCRYPTION_CALL} call with a dict payload not found"

    encrypted_keys: set[str] = set()
    response_keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        if id(node) in encryption_dicts:
            encrypted_keys |= keys
            continue
        response_keys |= keys

    # The only plaintext field name in the module is the payload handed to the
    # encryptor.
    assert encrypted_keys == {"api_key"}
    assert response_keys.isdisjoint(FORBIDDEN_CREDENTIAL_RESPONSE_KEYS)

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in _RESPONSE_BUILDERS:
            continue
        keys: set[str] = set()
        attributes: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Dict):
                keys |= {
                    key.value
                    for key in child.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
            elif isinstance(child, ast.Attribute):
                attributes.add(child.attr)
        assert keys, f"{node.name} must build an explicit response dict"
        assert keys <= SAFE_CREDENTIAL_RESPONSE_KEYS, f"{node.name} exposes {sorted(keys)}"
        assert keys.isdisjoint(FORBIDDEN_CREDENTIAL_RESPONSE_KEYS)
        assert attributes.isdisjoint({"encrypted_payload", "credential_fingerprint"})


# ---------------------------------------------------------------------------
# FF5 — no critical business calculations in React
# ---------------------------------------------------------------------------

WEB_PACKAGE_JSON = ROOT / "clients" / "web" / "package.json"
WEB_API_CLIENT = WEB_SRC / "api" / "client.ts"

# Solver, optimisation, statistics and numeric-compute packages. Any of these in
# the React client would move a critical calculation out of the deterministic
# backend engines.
FORBIDDEN_CLIENT_COMPUTE_PACKAGES = frozenset(
    {
        "highs",
        "highspy",
        "glpk.js",
        "javascript-lp-solver",
        "js-lp",
        "lp-solver",
        "ortools",
        "pulp",
        "cvxpy",
        "ml-matrix",
        "ml-regression",
        "simple-statistics",
        "mathjs",
        "numeric",
        "numpy",
        "scipy",
        "pandas",
        "polynomial",
        "decision-tree",
        "tensorflow",
        "onnxruntime-web",
    }
)

# Engine-shaped module names: a file with one of these stems would be a local
# optimisation/PnL/backtest implementation rather than a view model.
_ENGINE_FILE_PATTERN = re.compile(
    r"(optimizer|optimiser|solver|engine|linear_program|min_cost|pnl_calculator|backtest_engine)",
    re.IGNORECASE,
)

# Compute families the client must reach through the backend API instead of
# computing locally.
BACKEND_COMPUTE_ENDPOINTS = (
    "/route-cost/recommend",
    "/route-cost/resource-pool/optimize",
    "/strategy-lab/evaluate",
    "/backtest-experiments",
    "/research/netback",
)

_IMPORT_SPECIFIER = re.compile(r"""(?:from\s+|import\()\s*["']([^"']+)["']""")


def _declared_client_packages() -> set[str]:
    """Declared dependency package names of the Web workspace."""

    payload = json.loads(WEB_PACKAGE_JSON.read_text(encoding="utf-8"))
    names: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        names |= set(payload.get(section, {}))
    return names


def _package_root(specifier: str) -> str:
    """Return the npm package root of an import specifier."""

    if specifier.startswith("@"):
        return "/".join(specifier.split("/")[:2])
    return specifier.split("/")[0]


def _client_import_specifiers() -> set[str]:
    """Every module specifier imported by Web workspace source files."""

    specifiers: set[str] = set()
    for path in sorted(WEB_SRC.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".ts", ".tsx"}:
            continue
        specifiers |= set(_IMPORT_SPECIFIER.findall(_read_text(path)))
    return specifiers


def test_react_client_declares_no_compute_engine_dependency() -> None:
    """FF5: the Web workspace declares no solver/optimisation/statistics package."""

    declared = _declared_client_packages()
    assert declared, "no declared client dependencies found"

    offenders = sorted(
        name
        for name in declared
        if _package_root(name) in FORBIDDEN_CLIENT_COMPUTE_PACKAGES
        or name in FORBIDDEN_CLIENT_COMPUTE_PACKAGES
    )

    assert offenders == []


def test_react_client_imports_only_declared_dependencies() -> None:
    """FF5: Web source imports nothing outside its declared dependency set."""

    declared = _declared_client_packages()
    specifiers = _client_import_specifiers()
    assert specifiers, "no import specifiers found; the Web source scope is wrong"

    external = sorted(
        specifier
        for specifier in specifiers
        if not specifier.startswith(".") and not specifier.startswith("@/")
    )
    assert external, "no external import specifiers found; the scan is not reading client sources"

    undeclared = sorted({_package_root(item) for item in external} - declared)

    assert undeclared == []


def test_business_compute_stays_behind_backend_endpoints() -> None:
    """FF5: optimisation/PnL/backtest results are requested from the backend API."""

    api_client_source = _read_text(WEB_API_CLIENT)
    missing = [
        endpoint for endpoint in BACKEND_COMPUTE_ENDPOINTS if endpoint not in api_client_source
    ]

    assert missing == []

    engine_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in WEB_SRC.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".ts", ".tsx"}
        and _ENGINE_FILE_PATTERN.search(path.stem)
    )

    assert engine_files == []


# ---------------------------------------------------------------------------
# FF6 — Tauri commands stay within a bounded allowlist
# ---------------------------------------------------------------------------

TAURI_MAIN_RS = DESKTOP_TAURI / "src" / "main.rs"

# Reviewed native command surface of the desktop host. Changing this list is a
# client/host contract change: it must be updated here, in
# ``clients/desktop/src-tauri/src/main.rs`` and in the Web host-capability module
# in the same review.
HOST_COMMAND_ALLOWLIST = frozenset(
    {
        "read_deployment_config",
        "start_loopback_auth",
        "open_browser_login_and_wait",
        "notify_client_ready",
        "clear_client_session_data",
    }
)

_TAURI_COMMAND_DECLARATION = re.compile(
    r"#\[tauri::command\]\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"
)
_TAURI_GENERATE_HANDLER = re.compile(r"generate_handler!\[(.*?)\]", re.DOTALL)
_INVOKE_WITH_LITERAL = re.compile(r"""\binvoke(?:<[^>]*>)?\(\s*["']([^"']+)["']""")
_COMMAND_CONSTANT = re.compile(
    r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*COMMANDS?[A-Za-z0-9_]*)\s*=\s*\{(.*?)\}",
    re.DOTALL,
)
_STRING_LITERAL = re.compile(r"""["']([^"']+)["']""")


def _tauri_declared_commands() -> set[str]:
    """Native commands declared with ``#[tauri::command]`` in the host."""

    return set(_TAURI_COMMAND_DECLARATION.findall(_read_text(TAURI_MAIN_RS)))


def _tauri_registered_commands() -> set[str]:
    """Native commands registered in ``tauri::generate_handler!``."""

    match = _TAURI_GENERATE_HANDLER.search(_read_text(TAURI_MAIN_RS))
    assert match is not None, "generate_handler! registration block not found in the Tauri host"
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", match.group(1)))


def _client_host_commands() -> set[str]:
    """Native command names the Web workspace can invoke.

    Two discovery sources are combined so the check survives either shape: direct
    ``invoke("<command>")`` literals, and a declared host-command constant such as
    ``HOST_COMMANDS``. A client that no longer declares any native command fails
    the check loudly instead of silently passing.
    """

    discovered: set[str] = set()
    for path in sorted(WEB_SRC.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".ts", ".tsx"}:
            continue
        source = _read_text(path)
        discovered |= set(_INVOKE_WITH_LITERAL.findall(source))
        for _name, body in _COMMAND_CONSTANT.findall(source):
            discovered |= set(_STRING_LITERAL.findall(body))
    return discovered


def test_tauri_commands_match_the_bounded_host_allowlist() -> None:
    """FF6: the Tauri host declares and registers exactly the allowlisted commands."""

    declared = _tauri_declared_commands()
    registered = _tauri_registered_commands()

    assert declared, "no #[tauri::command] functions found in the Tauri host"
    assert declared == set(HOST_COMMAND_ALLOWLIST)
    assert registered == set(HOST_COMMAND_ALLOWLIST)


def test_web_client_invokes_only_allowlisted_host_commands() -> None:
    """FF6: the Web workspace can only invoke allowlisted native commands."""

    discovered = _client_host_commands()

    assert discovered, "no native host command found in the Web workspace"
    assert discovered == set(HOST_COMMAND_ALLOWLIST)


# ---------------------------------------------------------------------------
# FF7 — backend module dependency direction
# ---------------------------------------------------------------------------

# Packages that genuinely respect the target direction today. Each entry lists
# the edges that must never appear.
FORBIDDEN_LAYER_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset({"api", "application"}),
    "db": frozenset({"api", "application"}),
    "security": frozenset({"api"}),
    "optimization": frozenset({"api", "application", "db"}),
}

# Documented reverse edges: application modules that import the API layer. The
# list is frozen so a new reverse edge fails this test instead of being added
# silently; both entries are recorded as gaps in the W0-03 gap inventory.
API_LAYER_IMPORT_EXCEPTIONS = frozenset(
    {
        "application/agents/research_handlers.py",
        "application/dataops_observability.py",
    }
)


def _imported_module_names(path: Path) -> set[str]:
    """Absolute ``eurogas_nexus`` modules imported by one source file.

    Relative imports are resolved against the file's package so
    ``from .models import X`` inside ``eurogas_nexus/optimization/`` is reported
    as ``eurogas_nexus.optimization.models``.
    """

    tree = _python_tree(path)
    package_parts = path.relative_to(SRC).parts[:-1]
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "eurogas_nexus" or alias.name.startswith("eurogas_nexus."):
                    imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                depth = node.level - 1
                base = package_parts[: len(package_parts) - depth] if depth else package_parts
                parts = ("eurogas_nexus", *base)
                if node.module:
                    parts = (*parts, *node.module.split("."))
                module = ".".join(parts)
            else:
                module = node.module or ""
            if not module:
                continue
            if module == "eurogas_nexus":
                imported |= {f"eurogas_nexus.{alias.name}" for alias in node.names}
            elif module.startswith("eurogas_nexus."):
                imported.add(module)
    return imported


def _package_of(path: Path) -> str | None:
    """Top-level package name of a file under ``src/eurogas_nexus``."""

    parts = path.relative_to(SRC).parts
    return parts[0] if len(parts) > 1 else None


def test_backend_packages_respect_forbidden_import_directions() -> None:
    """FF7: the layers that respect the target direction never import upwards."""

    offenders: list[str] = []
    for owner, forbidden in FORBIDDEN_LAYER_IMPORTS.items():
        package_dir = SRC / owner
        assert package_dir.is_dir(), f"package missing: {owner}"
        for path in sorted(package_dir.rglob("*.py")):
            for module in sorted(_imported_module_names(path)):
                target = module.split(".")[1] if len(module.split(".")) > 1 else ""
                if target in forbidden:
                    location = path.relative_to(ROOT).as_posix()
                    offenders.append(
                        f"{location} -> {module} ({owner} must not import {target})"
                    )

    assert offenders == []


def test_api_layer_imports_are_limited_to_documented_exceptions() -> None:
    """FF7: outside ``api/`` only the documented exception modules import ``api``.

    Freezes the current reverse edges. A new module importing
    ``eurogas_nexus.api`` from a non-API package fails here; the two known
    exceptions are recorded as gaps in the W0-03 gap inventory.
    """

    importers: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        if relative.parts[0] == "api":
            continue
        if any(
            module == "eurogas_nexus.api" or module.startswith("eurogas_nexus.api.")
            for module in _imported_module_names(path)
        ):
            importers.add(relative.as_posix())

    assert importers == set(API_LAYER_IMPORT_EXCEPTIONS)


# ---------------------------------------------------------------------------
# FF10 — AI/agent invocation rechecks authority
# ---------------------------------------------------------------------------

ANALYSIS_ROUTE_MODULE = SRC / "api" / "routes" / "public" / "analysis.py"
_PROVIDER_ENTRYPOINT = "def _maybe_invoke_provider"
_PROVIDER_ENTRYPOINT_END = "_LLM_CONTRACT_FINANCIAL_FIELDS"

# Fail-closed ordering inside the provider entrypoint: request intent, environment
# profile gate, entitlement re-check, credential load, provider call.
_PROVIDER_GATE_SEQUENCE = (
    "body.invoke_provider",
    "llm_external_provider_enabled",
    "_snapshot_entitlement_blocker(snapshot)",
    "load_provider_api_key",
    "invoke_deepseek(",
)


def test_ai_provider_invocation_rechecks_authority_before_calling_provider() -> None:
    """FF10: the LLM entrypoint fails closed before any provider call.

    Static ordering check of the invocation path in
    ``eurogas_nexus.api.routes.public.analysis``: the caller must opt in, the
    deployment profile must allow an external provider, the snapshot entitlement
    re-check must pass, and only then may a stored credential be loaded and the
    provider be called. Behavioural coverage of the same path lives in
    ``tests/security/test_llm_provider_gate.py``.
    """

    source = _read_text(ANALYSIS_ROUTE_MODULE)
    assert _PROVIDER_ENTRYPOINT in source
    segment = source[source.index(_PROVIDER_ENTRYPOINT) : source.index(_PROVIDER_ENTRYPOINT_END)]

    positions: list[int] = []
    for marker in _PROVIDER_GATE_SEQUENCE:
        assert marker in segment, f"provider gate step missing from the entrypoint: {marker}"
        positions.append(segment.index(marker))

    assert positions == sorted(positions), (
        "provider invocation must check intent, profile and entitlement before "
        f"loading a credential or calling the provider; observed order {positions}"
    )


# ---------------------------------------------------------------------------
# Deliverable contract: the gap inventory stays in step with this module
# ---------------------------------------------------------------------------


def test_fitness_gap_inventory_covers_every_fitness_function() -> None:
    """The W0-03 gap inventory exists and accounts for all ten fitness functions."""

    assert FITNESS_GAP_DOC.is_file(), f"gap inventory missing: {FITNESS_GAP_DOC}"
    text = _read_text(FITNESS_GAP_DOC)

    # Word boundaries keep FF1 from being satisfied by the FF10 row.
    missing = [
        f"FF{index}" for index in range(1, 11) if re.search(rf"\bFF{index}\b", text) is None
    ]

    assert missing == []

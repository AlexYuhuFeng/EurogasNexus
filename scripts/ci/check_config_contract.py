#!/usr/bin/env python
"""Verify the configuration contract against the code that reads environment variables.

Two failures are possible, and both are delivery defects:

**Undeclared read** -- the code reads a variable that
``eurogas_nexus.core.config_contract`` does not declare. This is how the shipped
``.env.example`` came to omit the runtime DB URL, the credential-encryption key,
the internal API token and the whole OIDC block: nothing connected the template
to the code.

**Dead declaration** -- the contract declares a variable that no code reads, or
the shipped templates set one. ``EUROGAS_NEXUS_ALLOW_FILE_FALLBACK`` was
documented at length and set to ``false`` by ``deploy/runtime/compose.yaml``
while no code ever read it, so an operator believed a safety control was active.

Exit codes: 0 ok, 1 configuration defect, 2 cannot check.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_CONTRACT = REPO_ROOT / "src" / "eurogas_nexus" / "core" / "config_contract.py"

SCAN_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "apps",
    REPO_ROOT / "scripts",
    REPO_ROOT / "packages",
)
SCAN_EXTRA = (REPO_ROOT / "alembic",)

# The contract module names every variable by design; it is not a read site.
SCAN_EXCLUDE = {CONFIG_CONTRACT}

# A variable name is recognised as an env var when it is one of these, or when the
# retrieving call passes a module constant that holds one of these.
_PRODUCT_ENV_PREFIXES = ("EUROGAS_", "WINDOWS_SIGNING_", "GITHUB_")
_PRODUCT_ENV_EXACT = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "GIE_API_KEY",
    "GIE_API_KEY_FILE",
    "FORWARDED_ALLOW_IPS",
)
_HOST_ENV_NAMES = (
    "PYTHONPATH",
    "PATH",
    "HOME",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "LANG",
    "LC_ALL",
    "APPDATA",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "CI",
    "WEB_CONCURRENCY",
    "NO_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
)
ENV_NAME_PATTERN = re.compile(
    r"^(?:"
    + "|".join(re.escape(prefix) + r"[A-Z0-9_]+" for prefix in _PRODUCT_ENV_PREFIXES)
    + "|"
    + "|".join(re.escape(name) for name in _PRODUCT_ENV_EXACT + _HOST_ENV_NAMES)
    + r")$"
)

# Names that are infrastructure rather than product configuration. They are read
# for host reasons (interpreter path, CI identity, proxy settings), so the product
# neither documents nor controls them.
INFRASTRUCTURE_NAMES = {
    "PATH",
    "HOME",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "LANG",
    "LC_ALL",
    "APPDATA",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "PYTHONPATH",
    "NO_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "WEB_CONCURRENCY",
    "CI",
}


def _is_infrastructure(name: str) -> bool:
    return name in INFRASTRUCTURE_NAMES or name.startswith(("GITHUB_",))


def iter_python_files() -> list[Path]:
    """Return every Python file in the scanned roots."""

    files: list[Path] = []
    for root in SCAN_ROOTS + SCAN_EXTRA:
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return [path for path in files if path not in SCAN_EXCLUDE]


def module_env_constants(tree: ast.Module) -> dict[str, object]:
    """Map module-level constant names to what they hold.

    A plain name holding an env var name maps to that name. A name holding a
    tuple/list of env var names maps to the tuple, because iterating such a
    constant (``for name in DB_URL_ENV_VARS: os.getenv(name)``) is a real read
    pattern the product uses to accept aliases.
    """

    constants: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target = node.targets[0].id

        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if ENV_NAME_PATTERN.match(node.value.value):
                constants[target] = node.value.value
            continue

        if isinstance(node.value, (ast.Tuple, ast.List)):
            values = tuple(
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant)
                and isinstance(element.value, str)
                and ENV_NAME_PATTERN.match(element.value)
            )
            if values:
                constants[target] = values
    return constants


def environ_aliases(tree: ast.Module) -> set[str]:
    """Return local names that are bound to ``os.environ``.

    ``env = os.environ if environ is None else environ`` is how the session
    factory takes an injectable environment, and the reads then look like
    ``env.get("NAME")`` rather than ``os.environ.get("NAME")``. Missing this
    pattern would report those variables as never read.
    """

    aliases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        if not isinstance(node.targets[0], ast.Name):
            continue
        if isinstance(node.value, (ast.Name, ast.Attribute)) or isinstance(
            node.value, ast.IfExp
        ):
            if _references_os_environ(node.value):
                aliases.add(node.targets[0].id)
    return aliases


def _references_os_environ(node: ast.expr) -> bool:
    """Whether an expression mentions ``os.environ`` anywhere."""

    if _is_os_environ(node):
        return True
    if isinstance(node, ast.IfExp):
        return _references_os_environ(node.body) or _references_os_environ(node.orelse)
    return False


def _is_environ_receiver(node: ast.expr, aliases: set[str]) -> bool:
    """Whether ``node`` is ``os.environ`` or an alias bound to it."""

    if _is_os_environ(node):
        return True
    return isinstance(node, ast.Name) and node.id in aliases


def loop_env_bindings(
    tree: ast.Module, constants: dict[str, object]
) -> dict[str, tuple[str, ...]]:
    """Map loop variables to every env var name they can take.

    Two shapes both read every member of a set of aliases:

    * ``for env_var in DB_URL_ENV_VARS: env.get(env_var)`` iterates a module
      constant holding the names;
    * ``for env_name in (API_TOKEN_ENV, LEGACY_API_TOKEN_ENV): source.get(env_name)``
      iterates a tuple literal of constants that each hold a name.

    Neither can be resolved from the call site alone, so the loop variable is
    bound to the union of the members it can take.
    """

    bindings: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.AsyncFor)):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        iterated = node.iter

        members: tuple[str, ...] = ()
        if isinstance(iterated, ast.Name):
            resolved = constants.get(iterated.id)
            if isinstance(resolved, tuple):
                members = resolved
        elif isinstance(iterated, (ast.Tuple, ast.List)):
            collected: list[str] = []
            for element in iterated.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    if ENV_NAME_PATTERN.match(element.value):
                        collected.append(element.value)
                elif isinstance(element, ast.Name):
                    resolved = constants.get(element.id)
                    if isinstance(resolved, str):
                        collected.append(resolved)
                    elif isinstance(resolved, tuple):
                        collected.extend(resolved)
            members = tuple(collected)

        if members:
            bindings[node.target.id] = members
    return bindings


def _resolve_arg(
    node: ast.expr,
    constants: dict[str, object],
    loop_bindings: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Return the env var names named by one getenv/environ argument node."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value] if ENV_NAME_PATTERN.match(node.value) else []
    if isinstance(node, ast.Name):
        resolved = constants.get(node.id)
        if isinstance(resolved, str):
            return [resolved]
        if isinstance(resolved, tuple):
            return list(resolved)
        if loop_bindings and node.id in loop_bindings:
            return list(loop_bindings[node.id])
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        resolved = constants.get(node.value.id)
        if isinstance(resolved, tuple):
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, int):
                if 0 <= index.value < len(resolved):
                    return [resolved[index.value]]
            return list(resolved)
    return []


def _is_os_environ(node: ast.expr) -> bool:
    """Whether ``node`` is the expression ``os.environ``."""

    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def env_helper_params(tree: ast.Module) -> set[str]:
    """Return parameter names of local functions that read an env var.

    ``def _env_int(name, default): raw = os.environ.get(name, "")`` makes every
    string literal passed to ``_env_int`` a read site, which is how the DB pool
    settings are configured.
    """

    params: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        argument_names = {
            argument.arg for argument in list(node.args.args) + list(node.args.kwonlyargs)
        }
        if not argument_names:
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call) or not inner.args:
                continue
            func = inner.func
            first = inner.args[0]
            if not isinstance(first, ast.Name) or first.id not in argument_names:
                continue
            reads_env = (
                isinstance(func, ast.Name)
                and func.id in {"getenv"}
            ) or (
                isinstance(func, ast.Attribute)
                and (func.attr == "getenv" or func.attr == "get")
            )
            if reads_env:
                params.add(first.id)
    return params


def helper_call_sites(tree: ast.Module, helper_params: set[str]) -> dict[str, list[int]]:
    """Return ``{env_name: [lines]}`` for literals passed to env helper params."""

    if not helper_params:
        return {}

    functions: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        interesting = {
            argument.arg
            for argument in list(node.args.args) + list(node.args.kwonlyargs)
            if argument.arg in helper_params
        }
        if interesting:
            functions[node.name] = interesting

    found: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        interesting = functions.get(node.func.id)
        if not interesting:
            continue
        for keyword in node.keywords:
            if keyword.arg in interesting and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str) and ENV_NAME_PATTERN.match(value):
                    found.setdefault(value, []).append(keyword.value.lineno)
        for position, argument in enumerate(node.args):
            if not isinstance(argument, ast.Constant):
                continue
            value = argument.value
            if not isinstance(value, str) or not ENV_NAME_PATTERN.match(value):
                continue
            # Accept a literal passed positionally into an env-reading parameter.
            if position < len(interesting) or interesting:
                found.setdefault(value, []).append(argument.lineno)
    return found


def read_sites(path: Path) -> dict[str, list[int]]:
    """Return ``{env_var_name: [line numbers]}`` for one file."""

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return {}

    constants = module_env_constants(tree)
    aliases = environ_aliases(tree)
    loop_bindings = loop_env_bindings(tree, constants)
    found: dict[str, list[int]] = {}

    def record(arguments: list[ast.expr], lineno: int) -> None:
        for argument in arguments:
            for name in _resolve_arg(argument, constants, loop_bindings):
                found.setdefault(name, []).append(lineno)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            # ``os.getenv("NAME")`` -- the attribute is the function name.
            if (
                func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and node.args
            ):
                record([node.args[0]], node.lineno)
            # ``os.environ.get("NAME")`` or ``env.get("NAME")`` -- the attribute is
            # ``get`` and the receiver is the environment mapping or an alias.
            elif func.attr == "get" and _is_environ_receiver(func.value, aliases) and node.args:
                record([node.args[0]], node.lineno)

        # ``os.environ["NAME"]`` / ``env["NAME"]`` is a subscript, not a call.
        if isinstance(node, ast.Subscript) and _is_environ_receiver(node.value, aliases):
            record([node.slice], node.lineno)

    for name, lines in helper_call_sites(tree, env_helper_params(tree)).items():
        found.setdefault(name, []).extend(lines)

    return found


def declared_names() -> tuple[set[str], dict[str, str], set[str]]:
    """Return declared names, their scope, and the ones exempt from a local read site.

    Exempt are declarations flagged ``emitted_only`` (written into a generated
    artifact rather than read here) and those with an ``external_reader`` (read by
    uvicorn, compose or an installer outside this repository's Python).
    """

    try:
        source = CONFIG_CONTRACT.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot check: cannot read {CONFIG_CONTRACT}: {exc}") from exc
    tree = ast.parse(source, filename=str(CONFIG_CONTRACT))

    names: set[str] = set()
    scopes: dict[str, str] = {}
    exempt: set[str] = set()
    aliases_of: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "ConfigVar":
            continue
        name = None
        scope = "OPERATOR"
        no_local_read = False
        declared_aliases: tuple[str, ...] = ()
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                name = keyword.value.value
            if keyword.arg == "scope" and isinstance(keyword.value, ast.Constant):
                scope = keyword.value.value
            if keyword.arg == "emitted_only" and isinstance(keyword.value, ast.Constant):
                no_local_read = no_local_read or bool(keyword.value.value)
            if (
                keyword.arg == "external_reader"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value
            ):
                no_local_read = True
            if keyword.arg == "aliases" and isinstance(keyword.value, (ast.Tuple, ast.List)):
                declared_aliases = tuple(
                    element.value
                    for element in keyword.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
        if name:
            names.add(name)
            scopes[name] = scope
            if no_local_read:
                exempt.add(name)
            aliases_of[name] = declared_aliases
            for alias in declared_aliases:
                # A declared alias is a name the product accepts but resolves
                # through its canonical variable, so it needs no read site of its
                # own -- the SDK reads PUBLIC_API_TOKEN with API_TOKEN as fallback.
                names.add(alias)
                scopes.setdefault(alias, scope)
                exempt.add(alias)
    return names, scopes, exempt


def template_declared_names() -> dict[str, list[str]]:
    """Return env names mentioned in shipped templates/compose, per file."""

    candidates = [
        REPO_ROOT / ".env.example",
        REPO_ROOT / "deploy" / "runtime" / "compose.yaml",
        REPO_ROOT / "docker-compose.yml",
    ]
    candidates.extend(sorted((REPO_ROOT / "deploy").rglob("*.yaml")))
    candidates.extend(sorted((REPO_ROOT / "deploy").rglob("*.yml")))

    found: dict[str, list[str]] = {}
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        names = sorted(
            {
                match.group(1)
                for match in re.finditer(
                    r"\b(EUROGAS_[A-Z0-9_]+|RUNTIME_STORE_DATABASE_URL|FORWARDED_ALLOW_IPS|GIE_API_KEY)\b",
                    text,
                )
            }
        )
        if names:
            found[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = names
    return found


def main() -> int:
    declared, scopes, exempt = declared_names()
    if not declared:
        print("cannot check: the contract module declares no ConfigVar entries")
        return 2

    reads: dict[str, list[str]] = {}
    for path in iter_python_files():
        for name, lines in read_sites(path).items():
            if _is_infrastructure(name):
                continue
            relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for line in lines:
                reads.setdefault(name, []).append(f"{relative}:{line}")

    read_names = set(reads)

    undeclared = sorted(read_names - declared)
    dead = sorted(
        name
        for name in declared - read_names
        if name not in exempt
        # Test-only and build-metadata names are read by the suite and the release
        # tooling respectively; a read site outside the scanned roots is expected
        # for the latter only when the value is injected by CI entirely.
        and scopes.get(name) not in {"TEST_ONLY", "BUILD_METADATA"}
    )

    template_names = template_declared_names()
    template_undeclared: dict[str, list[str]] = {}
    for path, names in template_names.items():
        unknown = sorted(set(names) - declared)
        if unknown:
            template_undeclared[path] = unknown

    print("Configuration contract check")
    print(f"  declared variables : {len(declared)}")
    print(f"  variables read     : {len(read_names)}")
    print(f"  templates checked  : {len(template_names)}")
    print()

    failed = False

    if undeclared:
        failed = True
        print("FAIL undeclared environment variable reads (add a ConfigVar for each):")
        for name in undeclared:
            sites = reads[name][:4]
            suffix = "" if len(reads[name]) <= 4 else f" (+{len(reads[name]) - 4} more)"
            print(f"  {name}")
            print(f"      {', '.join(sites)}{suffix}")
        print()

    if dead:
        failed = True
        print("FAIL declared but never read (dead configuration, or a missing read site):")
        for name in dead:
            print(f"  {name}  [scope={scopes.get(name)}]")
        print()

    if template_undeclared:
        failed = True
        print("FAIL templates set variables the contract does not declare:")
        for path, names in sorted(template_undeclared.items()):
            print(f"  {path}: {', '.join(names)}")
        print()

    if failed:
        print("Configuration contract is not satisfied.")
        return 1

    print("OK every environment variable read is declared, every declaration is read,")
    print("   and no shipped template sets an undeclared variable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""SDK/CLI architecture boundary tests."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SDK_FILES = [
    ROOT / "src" / "eurogas_nexus" / "sdk" / "__init__.py",
    ROOT / "src" / "eurogas_nexus" / "sdk" / "health_client.py",
]
CLI_FILES = [
    ROOT / "src" / "eurogas_nexus" / "cli" / "__init__.py",
    ROOT / "src" / "eurogas_nexus" / "cli" / "health.py",
]

FORBIDDEN_IMPORT_PREFIXES = [
    "eurogas_nexus.domain",
    "eurogas_nexus.application",
]



def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def test_sdk_does_not_import_domain_or_application_modules() -> None:
    imports = set().union(*(_module_imports(path) for path in SDK_FILES))

    for forbidden_prefix in FORBIDDEN_IMPORT_PREFIXES:
        assert not any(name.startswith(forbidden_prefix) for name in imports)


def test_cli_does_not_import_domain_or_application_modules() -> None:
    imports = set().union(*(_module_imports(path) for path in CLI_FILES))

    for forbidden_prefix in FORBIDDEN_IMPORT_PREFIXES:
        assert not any(name.startswith(forbidden_prefix) for name in imports)

"""A byte-order mark must never make a configuration setting disappear.

Why this test exists
--------------------
`load_env_file` read the file with ``encoding="utf-8"``, which leaves a UTF-8 BOM
attached to the first key. A file whose first line was ``EUROGAS_NEXUS_ENV=release``
therefore produced the key ``"\\ufeffEUROGAS_NEXUS_ENV"``. Nothing matched it:

* ``_check_unknown_variables`` only reports names starting with a declared prefix, and
  the BOM sits before the prefix, so the name was not even reported as unknown;
* ``check_environment`` looked up ``EUROGAS_NEXUS_ENV``, found nothing, and defaulted to
  ``development``.

The result was a release environment that resolved as a development one, with the
production guards skipped, and no diagnostic naming the cause. Windows editors write a
BOM routinely when saving "UTF-8", so this was reachable by an ordinary operator
mistake — and the loader's own docstring says silently ignoring a line "would report a
clean preflight for a deployment that never received the setting".

These tests hold the four properties that make the failure impossible:

1. a BOM as the file prefix is stripped, and the first setting survives;
2. the same content with and without a BOM yields the **same** resolved environment;
3. a BOM anywhere inside a key name is refused loudly, never dropped;
4. the exit code does not depend on whether the file carries a BOM.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_CONFIG = REPO_ROOT / "scripts" / "ops" / "check_config.py"

BODY = "\n".join(
    [
        "EUROGAS_NEXUS_ENV=release",
        "EUROGAS_NEXUS_API_PROFILE=release",
        "EUROGAS_NEXUS_SECRET_KEY=G2a_97GkjnYm_Zn_69dTAMZYxdZc-EYcjM_Nalep6wM=",
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN=a-public-api-token-value",
        "",
    ]
)


def _write(tmp_path: Path, name: str, *, bom: bool) -> Path:
    path = tmp_path / name
    data = BODY.encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" + data) if bom else data)
    return path


@pytest.fixture()
def loader():
    """Import the loader from its script location."""

    scripts = REPO_ROOT / "scripts" / "ops"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import check_config  # noqa: PLC0415

    return check_config.load_env_file


def test_a_leading_bom_is_stripped_and_the_first_setting_survives(tmp_path, loader) -> None:
    """The exact failure: `EUROGAS_NEXUS_ENV` must not vanish."""

    values = loader(_write(tmp_path, "bom.env", bom=True))
    assert "EUROGAS_NEXUS_ENV" in values, (
        "the first variable disappeared. A BOM at the start of the file must be "
        f"stripped, not attached to the key. Keys seen: {list(values)[:3]}"
    )
    assert values["EUROGAS_NEXUS_ENV"] == "release"
    assert not any(key.startswith("\ufeff") for key in values), (
        "a key still carries the BOM character"
    )


def test_the_resolved_environment_is_identical_with_and_without_a_bom(tmp_path, loader) -> None:
    """The property that matters: the verdict cannot depend on an invisible byte."""

    plain = loader(_write(tmp_path, "plain.env", bom=False))
    bommed = loader(_write(tmp_path, "bom.env", bom=True))
    assert plain == bommed, (
        "the same file content resolved differently depending on a byte-order mark: "
        f"only-in-plain={sorted(set(plain) - set(bommed))}, "
        f"only-in-bom={sorted(set(bommed) - set(plain))}"
    )


def test_a_bom_inside_a_key_is_refused_rather_than_dropped(tmp_path, loader) -> None:
    """Fail closed on a stray mark the file prefix rule cannot explain.

    The second line carries a real U+FEFF character, not the four characters
    backslash-u-f-e-f-f. Encoding an explicit ``"\\ufeff"`` escape in a source file is
    the natural way to write this and the natural way to get it wrong: the first
    version of this test asserted a refusal that never happened, because the file it
    wrote contained no mark at all.
    """

    path = tmp_path / "midfile-bom.env"
    mark = "\ufeff"
    assert mark != "\\ufeff", "the escape must denote the character, not its spelling"
    path.write_bytes(
        f"EUROGAS_NEXUS_ENV=release\n{mark}EUROGAS_NEXUS_API_PROFILE=release\n".encode()
    )

    # Confirm the file really carries the mark before asserting the behaviour.
    assert b"\xef\xbb\xbf" in path.read_bytes()[1:], (
        "the fixture did not write a real BOM into the middle of the file, so this "
        "test would pass or fail for the wrong reason"
    )

    with pytest.raises(SystemExit) as excinfo:
        loader(path)

    message = str(excinfo.value)
    assert "byte-order mark" in message, (
        f"the refusal does not name the cause, so an operator cannot act on it: {message!r}"
    )
    assert f"{path}:2:" in message


@pytest.mark.parametrize(
    "line", ["test-only-secret-without-assignment", "\ufefftest-only-secret=synthetic-value"]
)
def test_invalid_environment_diagnostics_do_not_echo_input(tmp_path, loader, line) -> None:
    path = tmp_path / "invalid.env"
    path.write_text("# first line\n" + line, encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        loader(path)
    message = str(excinfo.value)
    assert f"{path}:2:" in message
    assert "test-only-secret" not in message
    assert "synthetic-value" not in message


def test_the_exit_code_does_not_depend_on_a_bom(tmp_path) -> None:
    """End to end through the CLI, which is what a release gate invokes."""

    def run(path: Path) -> int:
        result = subprocess.run(
            [sys.executable, str(CHECK_CONFIG), "--env-file", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode

    plain_code = run(_write(tmp_path, "plain.env", bom=False))
    bom_code = run(_write(tmp_path, "bom.env", bom=True))
    assert plain_code == bom_code, (
        "the preflight exit code changed because the file carried a byte-order mark "
        f"(without={plain_code}, with={bom_code}). A gate must not be bypassable by an "
        "invisible byte."
    )


def test_the_reported_environment_matches_with_and_without_a_bom(tmp_path) -> None:
    """The headline symptom: `release` must not be reported as `development`."""

    def environment_of(path: Path) -> str:
        result = subprocess.run(
            [sys.executable, str(CHECK_CONFIG), "--env-file", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in ((result.stdout or "") + (result.stderr or "")).splitlines():
            if "environment :" in line:
                return line.split(":", 1)[1].strip()
        return "(not reported)"

    plain = environment_of(_write(tmp_path, "plain.env", bom=False))
    bommed = environment_of(_write(tmp_path, "bom.env", bom=True))
    assert bommed == plain == "release", (
        f"the file declares a release environment but it was reported as {bommed!r} "
        f"(without a BOM: {plain!r})"
    )

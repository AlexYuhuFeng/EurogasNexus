"""The on-demand provider run (scripts/ai/run_note_eval.py) sends demo or public data only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from eurogas_nexus.application import ai_eval

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ai" / "run_note_eval.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_note_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_run_refuses_anything_but_demo_or_public_data():
    run = _load()
    evidence, _ = ai_eval.load()
    run.assert_demo_only(evidence, environ={})  # the recorded set is demo or public

    for profile in ("trial", "release"):
        with pytest.raises(run.Refused):
            run.assert_demo_only(evidence, environ={"EUROGAS_NEXUS_ENV": profile})

    db = {"RUNTIME_STORE_DATABASE_URL": "postgresql+pg8000://u:p@localhost/customer"}
    with pytest.raises(run.Refused):
        run.assert_demo_only(evidence, environ=db, store_check=lambda _url: False)
    run.assert_demo_only(evidence, environ=db, store_check=lambda _url: True)

    first = next(iter(evidence.values()))
    customer = {"customer": type(first)(**{**first.__dict__, "demo_or_public": False})}
    with pytest.raises(run.Refused):
        run.assert_demo_only(customer, environ={})

"""Job re-run contracts (Architecture V2 Wave 8, the "job replay" question).

Wave 8 left one operations question open: whether a recorded job can be replayed. The answer is a
property of the record rather than a feature, and these tests hold the answer to the schema:

- a job row stores a *hash* of its inputs, a scope and output *references* - so no kind can be
  re-issued from its job row, and a contract that claimed otherwise would contradict the table;
- every declared kind must answer the question, so a new kind cannot be added without deciding;
- a re-run always needs fresh authorisation and is never assumed idempotent;
- recording a snapshot is the one act that cannot be repeated at all.

They also pin the naming: the only public path called "replay" reads a recorded artefact chain, so
nothing in the surface can be mistaken for a re-run.
"""

from __future__ import annotations

from eurogas_nexus.db.models import JobRecord
from eurogas_nexus.domain.operations.jobs import (
    JOB_RERUN_CONTRACTS,
    JobKind,
    JobRerunContract,
    job_rerun_contract,
)


def test_every_declared_kind_answers_the_replay_question() -> None:
    declared = {contract.kind for contract in JOB_RERUN_CONTRACTS}
    assert declared == set(JobKind)
    assert len(JOB_RERUN_CONTRACTS) == len(JobKind)


def test_the_replay_answer_is_a_property_of_the_record_not_a_per_kind_choice() -> None:
    """No kind *can* claim to be replayable, which is why the schema is the real gate.

    A table of per-kind booleans would let a new kind declare itself replayable from a row that
    has nowhere to keep the inputs. The answer is derived from the record instead, and this test
    holds it that way: if a future edit turned `from_job_row` back into a settable field, the
    claim would become per-kind and the schema would have to change with it - which is what the
    neighbouring column test forbids. (The earlier version of this test only read the property
    back, so it could not fail; the assertion that has teeth is the one about the dataclass
    fields.)
    """

    from dataclasses import fields

    assert isinstance(JobRerunContract.from_job_row, property)
    assert "from_job_row" not in {field.name for field in fields(JobRerunContract)}
    assert all(contract.from_job_row is False for contract in JOB_RERUN_CONTRACTS)


def test_the_job_table_holds_no_inputs_container_to_replay_from() -> None:
    # The schema fact behind the rule: the row stores `input_hash` and references, and no column
    # in which a request could be reconstructed.
    columns = {column.name for column in JobRecord.__table__.columns}
    assert "input_hash" in columns
    assert not any("input" in name and name != "input_hash" for name in columns), sorted(columns)


def test_a_rerun_names_the_input_owner_and_the_path_that_issues_it() -> None:
    for contract in JOB_RERUN_CONTRACTS:
        if not contract.rerun_possible:
            # Nothing to re-issue: the act is point-in-time, so it declares neither an owner nor a
            # path rather than naming one that would mislead.
            assert contract.input_owner == "", contract.kind
            assert contract.new_run_path == "", contract.kind
            assert contract.reason, contract.kind
            continue
        # Where a re-run is possible it is issued through the path that owns the inputs, as a new
        # run: a contract without that path would be describing a capability nobody can reach.
        assert contract.input_owner, contract.kind
        assert contract.new_run_path.startswith("/api/"), contract.kind
        assert contract.reason.strip(), contract.kind


def test_every_named_rerun_path_is_a_real_public_path() -> None:
    # A contract that points at a path the deployment does not serve is worse than no contract:
    # the fitness check is against the app's own surface, not against the string's shape.
    from apps.api.main import app

    served = set(app.openapi()["paths"])
    missing = [
        f"{contract.kind}: {contract.new_run_path}"
        for contract in JOB_RERUN_CONTRACTS
        if contract.new_run_path and contract.new_run_path not in served
    ]
    assert missing == [], "a rerun contract names a path the deployment does not serve"


def test_the_snapshot_kind_is_the_one_act_that_is_never_repeated() -> None:
    snapshot = job_rerun_contract(JobKind.SNAPSHOT)
    assert snapshot.rerun_possible is False
    assert "point in time" in snapshot.reason

    # Every other kind can be re-issued, and says where from.
    for kind in JobKind:
        if kind is JobKind.SNAPSHOT:
            continue
        assert job_rerun_contract(kind).rerun_possible is True, kind


def test_an_undeclared_kind_is_a_programming_error_not_a_silent_answer() -> None:
    try:
        job_rerun_contract("NOT_A_KIND")  # type: ignore[arg-type]
        raise AssertionError("expected KeyError")
    except KeyError as exc:
        assert "NOT_A_KIND" in str(exc)


def test_replay_in_the_public_surface_reads_a_chain_and_never_re_runs_work() -> None:
    # `/api/agent/runs/{agent_run_id}/replay` returns the recorded artefact chain. Nothing in the
    # public surface re-issues the work of a recorded job, so the word cannot be read as a re-run.
    from eurogas_nexus.api.routes.public.agents import router as agents_router
    from eurogas_nexus.api.routes.public.jobs import router as jobs_router

    agent_paths = {route.path for route in agents_router.routes}
    assert "/api/agent/runs/{agent_run_id}/replay" in agent_paths
    job_paths = {route.path for route in jobs_router.routes}
    assert job_paths == {"/api/jobs", "/api/jobs/{job_id}", "/api/jobs/{job_id}/cancel"}
    assert not any("replay" in path for path in job_paths)

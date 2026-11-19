"""The ENTSOG tariff read: point by point, paced, each point committed, resumable.

ENTSOG answers through a mock transport in the platform's response shape; the store is an
in-memory SQLite database; every number is made up.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IngestionRunRecord, TsoTariffRecord
from scripts.ops import ingest_public_sources as script
from scripts.ops import run_dataops_scheduler as scheduler
from tests.unit.test_entsog_tariffs import record

STARTED = datetime(2026, 11, 19, 9, tzinfo=UTC)


def _client(answers: dict[str, object], asked: list[str]) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        point = request.url.params["pointKey"]
        asked.append(point)
        query = {key: request.url.params[key] for key in ("pointKey", "from", "to")}
        reply = answers[point]
        if isinstance(reply, int):
            return httpx.Response(reply, json={"message": "No result found"})
        return httpx.Response(
            200,
            json={
                "meta": {
                    "limit": int(request.url.params["limit"]),
                    "offset": 0,
                    "sort": "id",
                    "count": len(reply),
                    "total": len(reply),
                    "query": query,
                },
                "tariffsfulls": reply,
            },
        )

    return httpx.Client(transport=httpx.MockTransport(answer))


def _args(points, **extra):
    return SimpleNamespace(
        entsog_tariff_point=points,
        entsog_tariffs_max_age_hours=24,
        entsog_pace_seconds=0.5,  # below the floor: the read still waits 2 s
        limit=1000,
        entsog_page_size=1000,
        entsog_max_pages=5,
        **extra,
    )


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_a_stopped_read_keeps_what_it_read_and_resumes_at_the_next_point(session, monkeypatch):
    pauses: list[float] = []
    monkeypatch.setattr(script.time, "sleep", pauses.append)
    gts = [record("ITP-10012", "NL-TSO-0001", "exit", 4.0, "2026-01-01", "2027-01-01")]
    asked: list[str] = []
    report: dict = {"sources": {}, "failures": [], "warnings": []}
    with _client({"ITP-10012": gts, "ITP-00063": 404, "ITP-00555": 403}, asked) as client:
        script._ingest_entsog_tariffs(
            client,
            session,
            args=_args(["ITP-10012", "ITP-00063", "ITP-00555"]),
            started=STARTED,
            report=report,
        )
    detail = report["sources"]["ENTSOG-tariffs"]
    assert detail["window"] == {"from": "2026-10-01", "to": "2028-09-30"}
    assert detail["points_read"] == 2 and detail["records"] == 1
    assert [failure["point"] for failure in detail["points_failed"]] == ["ITP-00555"]
    assert detail["status"] == "SUCCEEDED_WITH_WARNINGS"
    # A polite pace: never less than 2 s between two queries.
    assert pauses == [2.0, 2.0]
    assert session.query(TsoTariffRecord).count() == 1
    run = session.query(IngestionRunRecord).filter_by(source_name="ENTSOG-tariffs").one()
    assert run.status == "SUCCEEDED_WITH_WARNINGS"

    # The next run (a scheduled retry) reads only the point it did not finish.
    asked.clear()
    pauses.clear()
    report = {"sources": {}, "failures": [], "warnings": []}
    bene = [record("ITP-00555", "NL-TSO-0001", "exit", 3.0, "2026-01-01", "2027-01-01")]
    with _client({"ITP-00555": bene}, asked) as client:
        script._ingest_entsog_tariffs(
            client,
            session,
            args=_args(["ITP-10012", "ITP-00063", "ITP-00555"]),
            started=STARTED,
            report=report,
        )
    detail = report["sources"]["ENTSOG-tariffs"]
    assert asked == ["ITP-00555"]
    assert detail["points_resumed"] == 2 and detail["points_read"] == 1
    assert detail["status"] == "succeeded"
    assert session.query(TsoTariffRecord).count() == 2


def test_without_a_max_age_every_point_is_read_again(session, monkeypatch):
    monkeypatch.setattr(script.time, "sleep", lambda _: None)
    gts = [record("ITP-10012", "NL-TSO-0001", "exit", 4.0, "2026-01-01", "2027-01-01")]
    for _ in range(2):
        asked: list[str] = []
        report: dict = {"sources": {}, "failures": [], "warnings": []}
        with _client({"ITP-10012": gts}, asked) as client:
            script._ingest_entsog_tariffs(
                client,
                session,
                args=SimpleNamespace(
                    **{**vars(_args(["ITP-10012"])), "entsog_tariffs_max_age_hours": None}
                ),
                started=STARTED,
                report=report,
            )
        assert asked == ["ITP-10012"]
    # A re-read upserts by tariff id: one row, not two.
    assert session.query(TsoTariffRecord).count() == 1


def test_the_scheduler_reads_tariffs_daily_paced_behind_the_entsog_approval():
    assert "entsog-tariffs" in scheduler._SOURCE_ARGS["src-entsog"]
    bounds = dict(scheduler._SOURCE_BOUNDS["src-entsog"])
    assert bounds["--entsog-tariffs-max-age-hours"] == "24"
    assert float(bounds["--entsog-pace-seconds"]) >= 2
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    attempt = scheduler.run_ingestor_attempt(
        runner, entsog_from="2026-11-18", entsog_to="2026-11-19"
    )
    attempt({"source_id": "src-entsog", "run_id": "run-1"}, 1)
    [command] = commands
    assert (
        command[command.index("--source", command.index("entsog-reference") - 1) :].count(
            "entsog-tariffs"
        )
        == 1
    )
    assert command[command.index("--entsog-pace-seconds") + 1] == "2"
    # The ENTSOG approval gate the ingestor applies covers the tariff route.
    assert script.RUN_SOURCE_ID_BY_SOURCE_NAME["ENTSOG-tariffs"] == "src-entsog"

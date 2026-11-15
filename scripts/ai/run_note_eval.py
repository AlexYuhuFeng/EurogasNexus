"""Run the real AI provider over the recorded evaluation set (AI-04), on demand.

    python scripts/ai/run_note_eval.py [--repeat N] [--json report.json]

For every recorded evidence payload in ``tests/evals/ai_note_cases.json`` the command builds
the messages the product would send (the same payload and message builders), calls the
configured provider, and puts the reply through the product's checks. It reports the share
of model outputs that pass, a histogram of refusal reasons, the median latency, and how
often the rule text had to stand (a refusal or a provider failure).

Only demo and public data is ever sent. The command refuses to run:

- if any evidence in the set is not marked ``demo`` or ``public``;
- in a trial or release profile (``EUROGAS_NEXUS_ENV``), where customer data lives;
- if a runtime database is configured and it is not a demo store (a store holding any
  trading book whose id does not start with ``demo-``, the demo seed's convention).

It reads the provider key from the usual provider-key chain and never prints it.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

class Refused(RuntimeError):
    """The run would send data that is not demo or public."""


def assert_demo_only(evidence, environ=None, store_check=None) -> None:
    """Raise :class:`Refused` unless everything this run could send is demo or public."""

    env = os.environ if environ is None else environ
    not_demo = sorted(key for key, ev in evidence.items() if not ev.demo_or_public)
    if not_demo:
        raise Refused(f"evidence not marked demo or public: {', '.join(not_demo)}")
    profile = (env.get("EUROGAS_NEXUS_ENV") or "development").strip().lower()
    if profile in {"trial", "release", "production"}:
        raise Refused(f"refused in the {profile} profile: customer data lives there")
    from eurogas_nexus.db.session import resolve_database_url

    url = resolve_database_url(env)
    if url is not None:
        check = store_check or _store_is_demo
        if not check(url):
            raise Refused("the configured runtime database is not a demo store")


def _store_is_demo(url: str) -> bool:
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if "trading_books" not in inspect(connection).get_table_names():
                return True
            count = connection.execute(
                text("SELECT count(*) FROM trading_books WHERE book_id NOT LIKE 'demo-%'")
            ).scalar_one()
            return int(count) == 0
    finally:
        engine.dispose()


def run(repeat: int = 1) -> dict:
    from eurogas_nexus.application import ai_eval
    from eurogas_nexus.application.ai_style import ANSWER_CALL, ENRICHMENT_CALL, NOTE_CALL
    from eurogas_nexus.llm import invoke_deepseek

    # The product's own budgets for each use.
    settings = {"explain": NOTE_CALL, "brief": NOTE_CALL, "answer": ANSWER_CALL,
                "enrichment": ENRICHMENT_CALL}
    from eurogas_nexus.security.provider_keys import load_provider_api_key

    evidence, _cases = ai_eval.load()
    assert_demo_only(evidence)
    api_key = load_provider_api_key("DEEPSEEK") or load_provider_api_key("LLM")
    if not api_key:
        raise SystemExit("no provider credential configured")
    outcomes = []
    for _round in range(repeat):
        for key, ev in evidence.items():
            started = time.monotonic()
            result = invoke_deepseek(api_key=api_key, messages=ev.messages,
                                     **settings[ev.use])
            latency = time.monotonic() - started
            if result.status != "success":
                outcomes.append({"evidence": key, "use": ev.use, "ok": False,
                                 "check": f"provider:{result.error_code or result.status}",
                                 "latency_s": latency, "output": None})
                continue
            verdict = ai_eval.verdict(ev, result.content)
            outcomes.append({"evidence": key, "use": ev.use, "ok": verdict.ok,
                             "check": verdict.check, "detail": verdict.detail,
                             "latency_s": latency, "output": result.content})
    total = len(outcomes)
    model_outputs = [o for o in outcomes if not o["check"].startswith("provider:")]
    passed = sum(1 for o in outcomes if o["ok"])
    by_use: dict[str, dict] = {}
    for use in sorted({o["use"] for o in outcomes}):
        rows = [o for o in outcomes if o["use"] == use]
        by_use[use] = {"calls": len(rows), "passed": sum(1 for o in rows if o["ok"])}
    return {
        "calls": total,
        "model_outputs": len(model_outputs),
        "passed": passed,
        "pass_share_of_model_outputs": (
            round(sum(1 for o in model_outputs if o["ok"]) / len(model_outputs), 3)
            if model_outputs else None
        ),
        "rule_text_stood_share": round((total - passed) / total, 3) if total else None,
        "refusal_reasons": dict(Counter(o["check"] for o in outcomes if not o["ok"])),
        "median_latency_s": round(statistics.median(o["latency_s"] for o in outcomes), 2)
        if outcomes else None,
        "by_use": by_use,
        "outcomes": outcomes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=1, help="rounds over the set")
    parser.add_argument("--json", type=Path, help="write the full report here")
    args = parser.parse_args(argv)
    try:
        report = run(repeat=max(1, args.repeat))
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    summary = {key: value for key, value in report.items() if key != "outcomes"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

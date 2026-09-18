# W6-01 — Decision Case and Decision Record

Status: **delivered (Wave 6, domain + persistence + API + product surface)**. Authority:
[08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) section 1,
[03_TARGET_PLATFORM_ARCHITECTURE.md](03_TARGET_PLATFORM_ARCHITECTURE.md) section 3, and
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rules 3-4, 32-33 and 43.

## 1. What a Decision Case is

The container that turns analysis into reviewable, human-owned decision evidence:

```text
Decision Case
  Objective -> Active Context -> Analysis Snapshot -> Assumptions -> Alternatives
  -> Scenarios -> Economics/Optimisation -> Risk/Constraints -> Evidence
  -> AI Findings/Challenge -> Human Review -> Decision Record
```

Two rules are structural, enforced in code rather than documented only:

1. **A Decision Record is evidence and rationale, never execution approval.**
   `DECISION_RECORD_IS_NOT_EXECUTION` is `True`; nothing on this surface enters orders, routes them,
   submits nominations or settles.
2. **A case cannot be decided without evidence.** `case_is_decidable()` refuses an empty container,
   and the API answers `409 case_not_decidable` with the blocker codes rather than recording a
   decision taken on nothing. `record_decision()` returns a *new* case, so the original container and
   its history are untouched.

## 2. Layers

| Layer | Module | Content |
|---|---|---|
| Domain | `src/eurogas_nexus/domain/decision/case.py` | Immutable `DecisionCase`, `DecisionAssumption`, `DecisionAlternative`, `DecisionEvidence`, `DecisionRecord`; lifecycle (`DRAFT`, `OPEN`, `UNDER_REVIEW`, `DECIDED`, `REOPENED`, `RETIRED`); decidability and blocker rules; compact summary |
| Vocabulary | `src/eurogas_nexus/domain/ontology/vocabulary.py` | `DecisionCaseStatus`, `DecisionEvidenceKind`, `DecisionAssumptionSource` — beside the existing `ReviewDecisionValue`/`ReviewEntityType`, as the ontology gate requires |
| Persistence | `db/models/decision.py`, `db/repositories/decision.py`, `alembic/versions/0035_decision_cases.py` | Two tables (`decision_cases`, `decision_case_records`), expand-only and non-destructive; records are separate rows because they are the audit-relevant part and a case may be reopened without losing history |
| API | `api/routes/public/decision_cases.py` | `GET/POST /api/decision-cases`, `GET /api/decision-cases/{case_id}`, `POST …/evidence`, `POST …/decisions`, `POST …/reopen` |
| Client contract | `clients/web/src/api/client.ts` | DTOs plus `createDecisionCase`, `attachDecisionCaseEvidence`, `recordDecisionCaseDecision(Outcome)`, `reopenDecisionCase`, `decisionCase(s)` |
| Product surface | `clients/web/src/components/DecisionCasePanel.tsx`, `clients/web/src/app/model/decisionCaseModel.ts` | The panel mounted on the Decision primary's review task: open a case from the Active Context, attach evidence, record or reopen a decision, and read the history. Availability comes from the payload (`decidable`, `blockers`), the actor stays with the backend, failures render through the product error taxonomy, and the no-execution boundary is stated on the surface |

Authorisation follows the existing registry: opening a case and attaching evidence are `GOVERNED`
(ANALYST floor), recording or reopening a decision is `REVIEW` (reviewer floor), reading a case keeps
the `READ` floor — the same treatment as `/api/review/decisions`.

## 3. Rules worth stating twice

1. **The actor is the authenticated identity**, never a request-body field. A spoofed `actor` in the
   body is ignored (covered by a test), so a record always names who actually decided.
2. **Evidence is deduplicated** by kind and reference, and the first evidence moves the case from
   `DRAFT` to `OPEN`.
3. **Reproducibility is explicit.** A case is `reproducible` when it carries an Analysis Snapshot
   reference (its own or through evidence), and when it does not, `decision_blockers()` says so
   rather than implying a reproducibility the platform cannot provide.
4. **Audit is part of the write.** Create, record and reopen each append an audit event in the same
   transaction.
5. **An AI interpretation is evidence of an interpretation.** The chain names an
   `AI Findings/Challenge` stage, and `DecisionEvidenceKind.AI_ANALYSIS` is what holds it: a Copilot
   run is cited by reference beside the deterministic artefacts, never as a number's authority. The
   panel offers the run the identity just completed instead of asking for an identifier, and the case
   still needs evidence and a human decision like any other.

## 4. Compatibility

- Additive API: five new paths, pinned in `tests/contract/test_api_surface_stability.py`, recorded in
  `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`, counted in the security acceptance bound.
- New migration `0035_decision_cases` is expand-only: it creates two tables and their indexes,
  alters nothing existing, needs no backfill, and is safe while the application serves traffic.
  `src/eurogas_nexus/release/constants.py::DB_SCHEMA_REVISION` reported `0035_decision_cases` when
  this slice landed and reports `0036_job_records` today (the Wave 8 job-lifecycle revision moved the
  head on), and the release-metadata test asserts that value equals the real Alembic head, so the
  constant cannot drift again - it tracks the head rather than this revision.
- No permission widening: the commercial boundary, role floors and entitlement filtering are
  unchanged.
- The panel is additive on the review task; the existing review-decision flow is untouched, and the
  two coexist until the older evidence list is folded into the case container.

## 5. Verification

- `tests/unit/test_decision_case_domain.py` — decidability, blocker codes, named-human requirement,
  note bounds, structure validation, reopen history, evidence deduplication.
- `tests/api/test_decision_cases_api.py` — 409 before evidence with blockers, evidence → decision →
  reopen flow, evidence deduplication, the actor coming from the identity rather than the body, and
  404/422 behaviour.
- `tests/unit/test_decision_case_migration.py` — the migration applying for real: the draft's
  `upgrade()`/`downgrade()` run against a throw-away SQLite database, the created tables/columns/
  indexes, that nothing pre-existing is touched, and that a decision record cannot name a case that
  does not exist (and is removed with its case). This file was added because the line it replaces -
  "the migration actually applying on SQLite" listed under the API suite - was not true: that suite
  builds its schema with `Base.metadata.create_all` and nothing anywhere read revision `0035`.
- `clients/web/tests/decisionCaseSurface.test.ts` — availability only when the payload says
  decidable, reproducibility and decidedness read from the payload, list splitting, stable label keys
  for unknown blockers, Active-Context-suggested references, the actor never being sent, failures
  rendered through the taxonomy, the stated no-execution boundary and bilingual vocabulary.
- Full suites: `python -m pytest tests -q --ignore=tests/integration` (green) and
  `node --test "tests/*.test.ts"` in `clients/web` (286 passed); the migration contract and release
  tests pin the schema head.

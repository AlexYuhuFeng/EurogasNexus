# ExecPlan: Split `domain/analysis.py` into a package (code-standards milestone)

Status: COMPLETE
Author: agent
Date: 2026-08-16
Related: `docs/engineering/CODING_STANDARDS.md` §6 (module single responsibility,
~700-line cap), previous rounds of docstring/comment standardization.

## 1. Goal

Split the 1303-line monolith `src/eurogas_nexus/domain/analysis.py` into a
single-responsibility package `src/eurogas_nexus/domain/analysis/`, and bring
every function/class in it up to the documented standard: Google-style
docstrings (English) + Chinese inline "why" comments, without changing any
public behaviour.

## 2. Non-goals

- No behaviour, payload, or API changes. Every public symbol keeps its name,
  signature, and exact output.
- No changes to `api/routes/public/analysis.py`, `glossary.py`, or other
  importers (they keep importing from `eurogas_nexus.domain.analysis`).
- No new dependencies. No DB/network access.

## 3. Product boundary

Pure domain logic: LLM-ready analysis/report contracts, deterministic report
builders, glossary term-context resolution. No web framework imports (kept
import-safe as today).

## 4. Files to create/modify

Create package (7 files):

- `domain/analysis/__init__.py` — re-export public API (backward compatible).
- `domain/analysis/contracts.py` — `AnalysisTask`, `AnalysisRequest`,
  `PortfolioReportRequest`, `AnalysisSnapshot`, `ReportSection`,
  `AnalysisResult`, `GlossaryContext` (lines 1-117).
- `domain/analysis/builders.py` — `business_logic_ontology`,
  `build_analysis_result`, `build_portfolio_report`, `_default_sections`,
  `_deterministic_answer_en`, `_deterministic_answer_zh`,
  `_missing_inputs_for_task`, `_snapshot_citations` (lines 119-425).
- `domain/analysis/glossary_context.py` — `build_glossary_context`,
  `_duration_payload`, `_first_capacity`, `_capacity_usage`, `_related_prices`,
  `_related_live_marks`, `_related_routes`, `_related_contracts`,
  `_context_warnings` (lines 201-320, 697-910, 1240-1244).
- `domain/analysis/glossary_profile.py` — `_resolved_glossary_context_profile`,
  `_matching_glossary_rows`, `_term_operational_keys`, `_infer_context_type`,
  `_context_description`, `_glossary_context_profile` (lines 428-694).
- `domain/analysis/glossary_entities.py` — `_matched_entities`,
  `_entity_payload`, `_unique_entities`, `_sources_from_matched_entities`,
  `_entity_summary`, `_context_metrics`, `_context_data_quality`,
  `_context_sections` (lines 912-1237).
- `domain/analysis/_common.py` — `_contains_any`, `_row_matches_duration`,
  `_first_datetime`, `_parse_datetime`, `_unique` (lines 1247-1303).

Delete: `domain/analysis.py`.

Modify: `tests/contract/test_docstring_policy.py` — add the new modules to
`CHECKED_MODULES`.

## 5. Dependency policy

No new dependencies (stdlib + pydantic as today).

## 6. Data policy

No data access; pure functions over supplied snapshots.

## 7. API impact

None. `eurogas_nexus.domain.analysis` re-exports every public symbol, so all
existing importers (`api/routes/public/analysis.py`,
`api/routes/public/glossary.py`, `tests/security/test_llm_provider_gate.py`)
keep working unchanged. OpenAPI path set must stay 91.

## 8. DB impact

None (no models, no migrations).

## 9. Tests

- Existing suites cover behaviour: `tests/api`, `tests/security` (LLM gate),
  `tests/unit` (analysis/glossary contexts), `tests/contract`.
- Contract test extension covers the new modules' docstrings.
- Full regression: 945 passed + 4 skipped baseline must hold.

## 10. Validation commands

```powershell
$env:PYTHONPATH = "$PWD\.deps"; ruff check src tests docs .agent
$env:PYTHONPATH = "$PWD\.deps;$PWD\src;$PWD"; python -m pytest -p no:cacheprovider tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security tests/streaming tests/workflow tests/workflows -q --tb=line
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"   # must print 91
```

## 11. Acceptance criteria

1. `domain/analysis.py` deleted; package exists with the 7 files above.
2. Every function/class in the new modules has a docstring; key logic carries
   Chinese "why" comments; no behaviour change (byte-for-byte function bodies).
3. All importers unchanged and green; full suite passes; OpenAPI stays 91.

## 12. Rollback notes

Package split is additive (new package + re-export `__init__.py`). Rollback =
restore `domain/analysis.py` from git (no commits exist this session; file
content preserved in this plan's line map) and delete the package directory.

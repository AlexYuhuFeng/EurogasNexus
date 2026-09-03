# RFC 0001: Repository Documentation And UI Baseline

- Status: `Accepted`
- Date: 2026-09-02
- Owner: repository maintainers

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this RFC are to be
interpreted as described in RFC 2119 and RFC 8174.

## Summary

Establish one maintainable baseline for repository documentation and the Web UI
before further feature work: a concise landing README, an authoritative
documentation index, an RFC/ADR/archive lifecycle, an automated Markdown link
gate, and a small shared UI primitive boundary.

## Context and problem

- The root README mixes landing, status, setup, database operations, source
  configuration, and troubleshooting material.
- `docs/` contains overlapping current, historical, planning, release,
  architecture, and client-design documents without one authoritative index.
- `PROJECT_DIRECTORY.md` names stale paths and mixes intent with the real tree.
- UI guidance overlaps across `CLIENT_DESIGN_SYSTEM.md` and the `UI_UX_STYLE_GUIDE`
  variants.
- `SourceCenter` and `RuntimeWorkspace` duplicate tabs, panel headers, metric
  strips, and status-badge class generation.
- There is no archive policy, RFC process, ADR index, or automated link check.

## Decision

1. Root `README.md` MUST remain a concise GitHub landing page. Detailed
   operations and references MUST live in `docs/` and be reached by links.
2. `docs/README.md` MUST be the authoritative documentation index and MUST label
   normative/current documents, runbooks, design references, and historical or
   archived material.
3. `PROJECT_DIRECTORY.md` MUST describe the real tree and ownership boundaries
   without listing every file.
4. Cross-cutting engineering changes MUST follow
   `docs/engineering/RFC_PROCESS.md`.
5. Architecture decisions MUST be indexed in
   `docs/architecture/ARCHITECTURE_DECISION_RECORD.md`; no additional ADR
   authority file may be created.
6. Obsolete or completed documents MUST be archived through
   `docs/policies/ARCHIVE_POLICY.md`. Only unambiguous candidates may be moved;
   uncertain material MUST NOT be mass-moved.
7. Internal Markdown links MUST pass
   `scripts/ci/check_markdown_links.py`. External URLs and generated/untracked
   directories are excluded.
8. Shared Web primitives MUST live under `clients/web/src/components/ui`.
   The phase-one set is `WorkspaceTabs`, `PanelHeader`, `StatusBadge`, and
   `MetricStrip`; a new primitive MAY be added only when it removes real
   duplication in more than one active workspace.
9. `SourceCenter` and `RuntimeWorkspace` MUST consume those primitives while
   preserving existing CSS classes, ARIA tab semantics, keyboard behavior, and
   runtime behavior.
10. No UI framework or runtime dependency MAY be added for this baseline, and
    `clients/web/src/styles/app.css` MUST NOT be broadly rewritten.
11. `docs/clients/UI_CONTENT_STANDARDS.md` MUST be the single authoritative
    UI/content standard. `CLIENT_DESIGN_SYSTEM.md` is archived, and the EN/CN
    style guides remain bilingual companions with no independent authority.

## Consequences

- New or moved files: root `README.md`, `docs/README.md`,
  `PROJECT_DIRECTORY.md`, RFC/ADR/archive governance, link-check script and
  test, UI primitive components, and focused UI tests.
- Obsolete documents are removed after current references are updated; internal
  milestone evidence is not part of the public release repository.
- `npm run test` runs the Node built-in test runner; no new frontend dependency
  is introduced.
- CI and local validation include the Markdown-link gate.

## Non-goals

- No whole-repository rewrite.
- No `app.css` split or broad CSS refactor.
- No changes to Strategy work in progress, shared API/store files, database
  schema, API contracts, topology semantics, simulation provenance, or business
  calculations.
- No commit, push, or release action from the implementing agent.

## References

- `README.md`
- `docs/README.md`
- `docs/architecture/ARCHITECTURE_DECISION_RECORD.md`
- `docs/policies/ARCHIVE_POLICY.md`
- `docs/clients/UI_CONTENT_STANDARDS.md`
- `clients/web/src/components/ui/`

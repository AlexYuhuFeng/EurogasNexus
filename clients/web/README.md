# clients/web

Future Eurogas Nexus web client.

## Blueprint

Read `docs/architecture/WEB_CLIENT_IMPLEMENTATION_BLUEPRINT.md` before adding
code here.

Also read:

- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

## Target

Browser-based, map-centric research workspace that consumes backend `/api`
contracts.

## First Web Milestone

- React + TypeScript + Vite shell.
- `/api/health` client.
- Runtime status view.
- Reference-network map layout with mocked data until backend contracts are
  ready.
- Source, warning, missing-input, lineage, `research_only`, and
  `human_review_required` states.

## Rules

- No direct DB access.
- No vendor API calls from the browser.
- No browser-side secrets.
- No historical UI copy-paste; redesign the workflow.

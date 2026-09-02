# Future Client UX Reference

## Status

Reference only for backend milestones. Web and Windows runtime implementation
belongs in selected client milestones, not in backend foundation work.

Client design authority now lives in:

- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

## Known Local References

Historical Windows demo executables were found under:

- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\builds\v0.5.0\`
- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\desktop-builds\`
- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus\src-tauri\target\`

The user also noted a Desktop shortcut/demo named like `eurogas nexus.exe`.
That demo may be used later to understand general workflow intent, not to copy
UI/UX or implementation.

## How To Use The Demo Later

When a future client milestone is approved:

1. Launch the demo only in a local exploratory session.
2. Capture workflow observations, not source code.
3. Record user tasks the demo suggests:
   - map workspace navigation;
   - route/corridor inspection;
   - facility, hub, and market-area context;
   - scenario composition;
   - result comparison;
   - reporting/research output review.
4. Redesign the UX around API-backed V1 contracts.
5. Do not copy desktop-specific runtime assumptions.

## UX Direction To Preserve

- Map-centric workspace.
- Context rails for selected assets, hubs, routes, and markets.
- Research workflow progression from input to resolved context to output.
- Visible data freshness, source, lineage, and warning states.
- Human-review-required output posture.

## UX Direction To Redesign

- Visual hierarchy.
- Navigation density.
- Data-entry ergonomics.
- Error, warning, and missing-input states.
- Report/export flows.
- Accessibility and keyboard behavior.
- API/runtime status visibility.

## V1 Boundary

The backend milestones should expose stable, documented API contracts that web
and Windows clients can consume later in V1. Backend milestones should not add
React, Tauri, Electron, Node, or desktop packaging. Client milestones may add
approved React/Vite or Tauri/Rust tooling when selected. Electron is not
approved for V1.

# Client Design System

## Design Goal

Eurogas Nexus visual clients should feel like dense, reliable research
workspaces, not marketing pages. The interface should help analysts scan market
context, physical context, warnings, and assumptions quickly.

SDK and CLI clients should follow the same information hierarchy in textual
form: status first, warnings early, assumptions and source references preserved.

## Personality

- professional;
- quiet;
- information-dense;
- map-centric;
- explicit about uncertainty;
- fast to scan;
- conservative with color.

## Layout Principles

- First screen is the workspace, not a landing page.
- Map or primary work surface occupies the largest area.
- Navigation is persistent and compact.
- Runtime status is always visible.
- Warnings and missing inputs are never hidden behind decorative UI.
- Details live in a right-side inspector.
- Comparisons and research outputs live in a bottom panel.
- Avoid nested cards.
- Cards use 8px radius or less.
- Avoid decorative gradients, orbs, and stock imagery.

## Internationalization And Theme

Required:

- English `en-US`;
- Mandarin Chinese `zh-CN`;
- light theme;
- dark theme;
- system theme mode.

Implementation authority:

- `docs/clients/CLIENT_I18N_THEME_SPEC.md`
- `docs/clients/CLIENT_TECH_STACK.md`

All user-visible Web and Windows strings must go through localization resources.
Theme must use CSS custom properties, not a heavy design framework.

## Color Tokens

Use a balanced palette:

| Token | Use |
| --- | --- |
| `surface.base` | app background |
| `surface.panel` | sidebars, inspectors, toolbars |
| `surface.raised` | repeated items and modals |
| `text.primary` | main text |
| `text.secondary` | metadata |
| `border.subtle` | grid and panel separators |
| `accent.action` | primary commands |
| `status.ok` | healthy state |
| `status.warning` | stale, missing, partial |
| `status.critical` | unavailable, restricted, failed |
| `map.pipeline` | route and segment lines |
| `map.lng` | LNG assets |
| `map.storage` | storage assets |
| `map.hub` | hub and market nodes |
| `map.capacity` | capacity and contract overlays |
| `analysis.llm` | LLM analysis and citation badges |

Do not let the app become a one-color blue, purple, beige, or dark-slate theme.

## Typography

- Use a system UI font stack unless the selected client stack has a local design
  system.
- Do not scale font size with viewport width.
- Use compact headings inside panels.
- Reserve large display type for a true product header only; normal workspace
  screens should use practical panel headings.
- Letter spacing is `0`.

## Controls

Use familiar controls:

- icon buttons for map tools and layout controls;
- segmented controls for map modes;
- checkboxes or switches for layer toggles;
- sliders or number inputs for numeric filters;
- menus for option sets;
- tabs for inspector sections;
- tables for comparisons;
- badges for source, entitlement, freshness, and runtime state.

Every icon-only control needs an accessible label or tooltip.

## Required States

Every screen must design for:

- loading;
- empty;
- degraded backend;
- DB unavailable;
- missing inputs;
- stale data;
- restricted data;
- partial feature;
- error with safe details;
- research-only output.

## Accessibility

- Do not rely on color alone for warnings.
- Keyboard focus must be visible.
- Tables and map controls must be reachable by keyboard.
- Text must not overflow buttons, cards, rails, or result rows.
- Small screens must keep navigation, status, and primary action reachable.

## Copy Rules

Use:

- research output;
- candidate;
- scenario;
- assumption;
- warning;
- missing input;
- human review required;
- indicative.

Do not use:

- trade signal;
- execute;
- order;
- approve trade;
- official recommendation;
- auto-trade.

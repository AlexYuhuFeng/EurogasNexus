# Strategy price catalogue acceptance — 2026-10-23

The strategy design panel now selects canonical price series from the existing
entitlement-filtered normalized market response. Hub selection uses the loaded
market hubs and preserves the stored draft value. Each price leg filters choices
by the selected hub and day-ahead/within-day tenor; labels expose source, hub,
tenor and currency/unit. Checkbox choices wrap on narrow screens. Existing names
absent from the current bounded market view remain visible and editable, rather
than being silently replaced or treated as proof that historical data is absent.

Market discovery and historical evidence loading share the same canonical naming
and fallback tenor functions. No additional data request or entitlement is added.
The backend response adds optional `price_name`; older clients remain compatible.

The UI explicitly describes intraday minus day-ahead economics. It does not claim
support for single-price signals, arbitrary baskets, or source-specific binding.
Historical target declarations, temporal selection and entitlement checks remain
authoritative. Current market choices are discovery, not historical coverage proof.

## Validation

- Backend normalized API, entitlement and target-selection selection: 43 passed;
  after extracting shared tenor fallback and adding the API name assertion, the
  affected API/target selection rerun: 39 passed (overlapping selections).
- Full Web regression: 942 passed, 3 skipped; production build passed.
- Catalogue unit tests: 3 passed, including hub/leg mismatch and missing names.
- Linux Chromium with the synthetic analyst session: catalogue loads, a checkbox
  toggles and restores; 1440/768/390 viewport document widths equal viewport widths;
  no unhandled page errors. Screenshots inspected at 390px.
- Keyboard acceptance rerun: 8 passed, including Ctrl navigation, focus retention,
  IME guard and palette dismissal. These are browser checks, not native login proof.
- Evidence: ignored `.local-runtime/ux-audit/catalogue-*`, `efficiency-results.json`
  and `strategy-catalogue-build.log`.

## Outstanding delivery work

This is a bounded improvement, not a delivery approval. Source-specific evidence
binding, richer strategy semantics and contract/strategy/backtest/review scenario
acceptance remain open. The catalogue currently uses the bounded loaded observation
view; quote-only/historical catalogue discovery is not implemented. The native
package has not yet been rebuilt for this UI revision or authenticated with the
test account. Windows/Ubuntu target acceptance and signing are not claimed.
Regional transport remains deferred and disabled. No publication or push occurred.

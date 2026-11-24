# 11 Commercial quality standard

One yardstick for every part of Eurogas Nexus: engines, data, screens, the SDK and the
documentation. A part is commercial grade when it meets every **must** below for the roles
that use it. Reviews score against these IDs so that results are comparable across parts
and over time. Findings and evidence go to
[13_PERSONA_AND_PRACTICE_REVIEW.md](13_PERSONA_AND_PRACTICE_REVIEW.md).

The bar is set by what the people who use the product already work with every day:
Bloomberg and ICE terminals, Platts and Argus assessments, Kpler and Vortexa for cargoes,
Endur and Allegro for trades, and the desk tools of firms such as Jane Street and HRT,
where every number on screen is trusted because it is traceable and current.

## Severity

| Level | Meaning | Release rule |
| --- | --- | --- |
| S1 | Wrong or misleading figure, broken control, a role cannot finish its core task, data loss, security or segregation-of-duties failure | Blocks release |
| S2 | The task can be finished but is slow, confusing or needs a workaround; a figure is right but cannot be traced | Fix before release unless accepted in [08](08_DECISION_LOG.md) |
| S3 | Polish: alignment, wording, motion, consistency | Fix when the area is next touched |

## Roles and their first minute

Every role must reach its core answer within one minute of signing in, without help.

| Role | Core question in the first minute | Must see without scrolling (1440x900) |
| --- | --- | --- |
| Gas trader (NWE hubs) | Where are prices and spreads now, and what changed? | Hub board with last, change vs close, age of each price |
| LNG trader | Where are my cargoes, are slots safe, are hedge months right? | Cargo board: ETA, slot status, next action, last change |
| Pipeline scheduler | What must be nominated before the next deadline? | Gas-day clock, open nominations, imbalance |
| Risk controller | Are we inside limits, and is any figure stale? | Limit utilisation, breaches, data freshness |
| Desk head / team lead | What needs my decision today? | Approvals waiting, top opportunities, P&L by book |
| Quant / analyst | Can I get the data and run my model? | SDK quickstart works; data catalogue with sources |
| Administrator | Are feeds, users and jobs healthy? | Source status, alerts, user and key management |

## A. Data (applies to every figure on screen, in the API and in the SDK)

| ID | Must | How it is checked |
| --- | --- | --- |
| A1 | Every figure names its source, unit and as-of time, on hover or in the row | Hover each figure in a screenshot session; read the API `meta` |
| A2 | A figure older than its source's expected cadence looks stale (colour plus text, not colour alone) | Age a source in the test store; compare screenshots |
| A3 | Simulated, demo, assumed and estimated values are labelled as such everywhere they travel, including into derived results | Trace one demo value to every screen and export that uses it |
| A4 | The same measure shows the same number, unit and rounding on every screen; different measures have different labels | Cross-check one hub, one book, one cargo across screens |
| A5 | Units follow the ontology: no silent unit or currency conversion; GBp/th and GBP/th never confused | Unit probes from the ontology review |
| A6 | Times are shown in the user's zone with the zone named; gas days follow 06:00 CET | Compare a gas-day boundary on screen with the domain rule |
| A7 | Bad input is refused or quarantined with a reason: negative or 100x prices, future timestamps, unknown hubs | API probes; importer probes |
| A8 | A figure on screen reconciles to its stored source within its rounding | Read the stored row and compare to the screenshot |

## B. Engines and calculations

| ID | Must | How it is checked |
| --- | --- | --- |
| B1 | Each result lists its inputs with their sources, and a missing input is named, never filled silently | API response review; unit tests |
| B2 | Results are reproducible: same inputs give the same output; a replay matches | Repeat calls; outbox replay |
| B3 | One definition per measure (P&L, exposure, freshness, VaR horizon) | Code search for duplicate implementations |
| B4 | A hand-worked example matches to the stated tolerance for every engine | Domain tests per engine |
| B5 | Advice is advice: nothing trades, nominates, books or settles | Route and permission review |
| B6 | A change in an input reaches the affected results within the published latency (seconds for decision support) | Latency measurement from event to screen |
| B7 | Controls hold: four-eyes where stated, no self-approval, limits checked where a decision is proposed | Role-switching browser sessions; API probes |

## C. Screens and interaction (web and desktop)

| ID | Must | How it is checked |
| --- | --- | --- |
| C1 | The role's core answer is above the fold at 1440x900 and 1920x1080 | Screenshot per role landing |
| C2 | Numbers are right-aligned, with thousands separators and consistent decimals per measure; negatives and changes carry sign and direction | Screenshot review; formatter tests |
| C3 | Every interactive element has hover, focus and pressed states; tooltips appear within 500 ms and do not hide the value they describe | Pointer and keyboard session per page |
| C4 | Charts support hover read-out (crosshair or tooltip with value, unit and time), zoom or range choice, and a legend that toggles series | Pointer session over each chart |
| C5 | Every task can be done from the keyboard; the command palette finds pages and instruments; focus order follows the reading order | Keyboard-only session per role |
| C6 | Live values update without a reload; a change flashes with direction (up/down), never on a tab or tenor switch | Watch a page while publishing a price |
| C7 | Motion is purposeful, 200 ms or less for page and panel changes, and off under reduced-motion settings | Screen recording; reduced-motion run |
| C8 | Empty, loading and error states say what happened and what to do; no raw status codes or stack traces | Force each state |
| C9 | WCAG 2.2 AA: contrast, target size, labels, no colour-only meaning | Automated audit plus manual check |
| C10 | Performance: first useful paint under 2 s and interaction response under 100 ms on the reference laptop with the demo store | Browser timing |
| C11 | Density suits a desk: compact rows available; no wasted chrome on data screens | Screenshot review |
| C12 | Sign-in and installer look and behave like a commercial product: crisp at high DPI, signed, clear errors | Installer and sign-in session |

## D. SDK, API and integration

| ID | Must | How it is checked |
| --- | --- | --- |
| D1 | A new user installs, authenticates and makes a first call by following the quickstart verbatim | Fresh venv run of the quickstart |
| D2 | Every public path is in the API reference with request, response, errors and permission | Contract tests; generated reference check |
| D3 | Errors carry a stable code and a message that says what to do | Error catalogue review |
| D4 | Breaking changes follow the contract evolution policy and are listed in the changelog | Contract tests |
| D5 | Trades and positions import from an ETRM without double counting, with an audit trail and snapshot semantics | Import probes |
| D6 | Exports carry units, sources and as-of times | Export review |

## E. Documentation

| ID | Must | How it is checked |
| --- | --- | --- |
| E1 | Organised by need (tutorial, how-to, reference, explanation) and by role | Index review |
| E2 | Every command and code block runs as written | Doc example tests |
| E3 | English and Chinese versions say the same thing | Pairwise review |
| E4 | No broken links or stale code paths | Link checker |
| E5 | Troubleshooting covers the errors a new user meets first | Fresh-install session |

## F. Operations and controls

| ID | Must | How it is checked |
| --- | --- | --- |
| F1 | Every scheduled job is actually scheduled and reports when it fails | Scheduler review |
| F2 | Stale feeds, dead letters and backlogs raise one alert each and clear on recovery | Monitoring tests (M6) |
| F3 | Every change to reference data, limits, marks and hedges is audited with who and when | Audit table review |
| F4 | Oversight roles can read the audit trail; no role can approve its own work | Role sessions |

## How a review is run

1. **Per role, in a real browser.** Drive the web client (and the desktop shell where it
   differs) with Playwright against the demo store, as that role, at 1440x900 and
   1920x1080, in light and dark themes.
2. **Like a person.** Click through the role's daily workflow, hover every figure and
   chart, use the keyboard and the command palette, drag and zoom charts, switch pages,
   leave a page open while a price is published, and sign out and in.
3. **Screenshots read twice.** Once for display and UX (C criteria). Once for the data:
   is each figure correct against its stored source (A8), traceable (A1), current (A2),
   labelled if simulated (A3), consistent with other screens (A4), and useful for the
   decision the role is making.
4. **Record.** Each finding gets an ID, the criterion, severity, the screenshot or
   reproduction, and the fix. S1 and S2 are fixed in the programme; S3 are listed.
5. **Re-run after the fix** and keep before and after evidence in
   [09](09_VALIDATION_EVIDENCE.md).

Where the user's suggestions and established practice differ, practice wins and the
reason is logged in [08](08_DECISION_LOG.md); the user asked for this on 2026-11-24.

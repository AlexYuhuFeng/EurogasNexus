# DRAFT ADR: Role model with segregation of duties; scopes and audit enforced by structure

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) section 3.8. On acceptance it is appended to
[ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md). It amends Decision 30
(SCHEDULER) and Decision 32 (who approves which change) and builds on the security remediation of
findings H1 to H7, which is in progress and not re-planned here. Rule 7 (persona and work mode
never grant authority) is unchanged and remains machine-checked.

**Context.** There are six ranked roles (`security/identity.py`: VIEWER, SCHEDULER, REVIEWER,
ANALYST, OPERATOR, ADMIN) and a set of named permissions (`portfolio.read`, `portfolio.write`,
`review.record`, `gas_day.record`, `audit.read`, `identity.manage` and others). One REVIEWER role
serves market risk, compliance and the head of desk, so compliance can set credit lines and
approve firm marks, and the head of desk can approve his own desk's marks (middle-office review).
The audit trail is readable only by ADMIN (`security/permissions.py:86`). A single ranking cannot
express segregation: risk is not "above" a trader, it is beside him with different rights. Book
scope is opt-in per query and off by default (H1, being fixed in the data-access layer); the
application connects as the database owner (H5); one administrator can switch four-eyes off and
provision a second account (H7). Regulators and auditors expect segregation of duties (SoD: no
one person both makes and approves a control-relevant change), information barriers between
entities and desks, and an audit trail the application itself cannot rewrite.

**Decision.**

1. **Roles are named bundles of permissions, not ranks.** Route and handler checks ask for a
   permission. The rank remains only to sort a principal's primary role for display.
2. **Role set**:

   | Role | Purpose | May | May not |
   | --- | --- | --- | --- |
   | VIEWER | Read-only desk and market data in scope | read | write anything |
   | TRADER | Front office | read book in scope, run what-ifs, create decision cases, propose changes | approve marks, limits, credit, hedge bands |
   | ANALYST | Research and fundamentals | research, datasets, reports, scenarios | read books unless granted a book scope |
   | SCHEDULER | Gas-day operations | record nomination and terminal status (`gas_day.record`) | edit contracts or positions |
   | DESK_HEAD | Desk management | read the desk's book and management pack, approve decision cases | approve marks, limits or credit for the own desk |
   | MARKET_RISK | Market risk control | approve limits, mandates, hedge bands; run and attest risk; model register entries | propose trades or decisions |
   | CREDIT_RISK | Credit control | approve credit lines, collateral, netting terms | approve market-risk limits |
   | PRODUCT_CONTROL | Valuation control | approve firm marks (IPV), attest a close | change limits |
   | COMPLIANCE | Surveillance and records | read audit and surveillance, disposition alerts, keep the inside-information register | approve any commercial change |
   | DATA_OPERATOR | Source operations (was OPERATOR) | run sources, imports, certification | read books; write licensed price families |
   | PLATFORM_ADMIN | Runtime administration (was ADMIN, platform part) | runtime settings, releases, health | read commercial data; grant roles |
   | IDENTITY_ADMIN | Access administration (was ADMIN, identity part) | propose grants, disable users | approve own proposals; hold a commercial role at the same time |

3. **Segregation rules, enforced in code and tested**: the proposer of a change never approves
   it; an identity's creator never approves that identity's proposals; front-office roles never
   approve marks, limits or credit; grants of roles and scopes need a second identity
   administrator and the business owner named for the role; changing a four-eyes setting is
   itself four-eyed; break-glass accounts are sealed, hardware-key protected and alert
   compliance on use. Every privileged change notifies compliance.
4. **Scopes**: data scopes by legal entity, desk and book, default-deny, enforced in the one
   data-access layer (the remediation); then **PostgreSQL row-level security** on book-scoped
   tables as a second layer, set per transaction from the caller's scope, once the database roles
   are split. A query outside a request context sees no rows.
5. **Database roles**: migration owner (DDL), application (DML, no DDL, `INSERT` only on audit),
   read-only reporting (replica and Excel), audit reader (compliance exports).
6. **Audit**: each row carries the previous row's hash and its own; a signed daily digest; a daily
   write-once export to object storage; a stream to the firm's SIEM; retention at least five
   years, configurable upward; pruning only under four eyes and only of exported days.
7. **Access requests and recertification**: a request flow approved by the business owner, and
   a quarterly access-recertification report per role and scope.
8. **Mapping**: an installation's existing REVIEWER principals are mapped to MARKET_RISK by a
   reviewed migration file that the customer's administrator confirms per person; ADMIN is split
   into PLATFORM_ADMIN and IDENTITY_ADMIN the same way. Group-to-role maps for single sign-on use
   explicit, application-prefixed group names only.

**Alternatives.** (a) Keep ranked roles and add more ranks: cannot express "beside, not above".
(b) Attribute-based policies in a policy engine (for example OPA): powerful but a new component
and a second language for rules; the permission bundles cover the need. (c) Separate
installations per desk to enforce barriers: splits the book and duplicates data and licences
(rejected in Decisions 22 and 26).

**Consequences.** More roles to administer, matching how trading firms already organise access
in their ETRM. Demo accounts gain MARKET_RISK, COMPLIANCE, PRODUCT_CONTROL, SCHEDULER and DESK_HEAD
users with their own homes. Row-level security adds a small cost per query, measured before it is
turned on per table.

**Migration.** (1) Permission bundles behind the current roles (no behaviour change). (2) New
roles and the SoD rules, with an authorisation-matrix test over every route and role in CI.
(3) Compliance audit read. (4) Database roles and the audit chain (remediation). (5) Row-level
security per table family, measured. (6) Role mapping for existing installations.

**Tests that make it observable.** The authorisation matrix in CI; a test that a DESK_HEAD cannot
approve a mark for the own desk; a test that the application role cannot `UPDATE` or `DELETE`
audit rows; a hash-chain verification test; a query outside a request returns no book-scoped rows.

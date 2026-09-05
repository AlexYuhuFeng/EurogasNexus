# RFC Process

## Purpose and authority

An RFC is a short, reviewable proposal for a cross-cutting or normative change.
Use an RFC when a change affects a product boundary, public API contract, data
governance rule, shared client standard, or another decision consumed by more
than one owner.

README files and indexes are descriptive navigation. They do not override a
policy, contract, accepted RFC, or ADR. Normative requirements use the key
words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** as
described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

## When an RFC is required

An RFC is REQUIRED before implementation when a change:

- changes a normative boundary or accepted product decision;
- changes a stable API, data contract, entitlement rule, or source-governance
  rule; or
- introduces a shared standard that multiple clients, services, or teams must
  follow.

A narrow implementation that follows an existing contract MAY use an ExecPlan
without a new RFC. An ADR records an accepted architecture decision; an RFC is
the proposal and review record that may lead to a new or superseding ADR.

## Lifecycle

1. Copy [RFC_TEMPLATE.md](RFC_TEMPLATE.md) and add the proposal to the registry
   in [RFC_INDEX.md](RFC_INDEX.md).
2. Write the problem, decision, alternatives, owners, non-goals, compatibility
   impact, data/security impact, and acceptance criteria.
3. Request review from every affected owner. The proposal is `draft` until the
   reviewers can evaluate those sections.
4. Mark it `accepted`, `rejected`, or `superseded` in the index. An accepted
   architecture decision MUST also be appended to the ADR record in the same
   change; existing ADR meaning MUST NOT be silently rewritten.
5. Link the accepted RFC from the affected contract and update tests and
   documentation in the same implementation change.

## Scope and retention

RFCs in this public repository contain only reusable product and engineering
decisions. Do not add credentials, licensed vendor payloads, confidential
contracts, customer details, or private milestone evidence. Deleted internal
plans and private historical records are not restored or archived here.

## Review checklist

- [ ] The proposal uses normative language only where a requirement is intended.
- [ ] Affected owners, alternatives, non-goals, and rollback are explicit.
- [ ] API, database, client, data-rights, and security effects are identified.
- [ ] Acceptance tests or observable verification are named.
- [ ] The RFC index, affected contracts, and ADR record are updated together.

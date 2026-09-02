# RFC Process

## Status

This process is normative for cross-cutting engineering changes in Eurogas
Nexus: repository documentation structure, shared API/client boundaries, UI
system changes, and other changes that affect more than one owner.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be
interpreted as described in RFC 2119 and RFC 8174. Do not use those terms in
casual README or landing-page prose; they belong in engineering specifications
like this document.

## When an RFC is required

An RFC MUST be created when a change:

- reorganizes documentation authority or archive policy;
- introduces or removes a shared client primitive boundary;
- changes the public `/api` or SDK surface;
- changes the product boundary or deployment posture;
- adds a cross-cutting dependency or toolchain gate;
- changes source-of-truth or provenance semantics.

Routine bug fixes, isolated runbook corrections, and single-owner maintenance
changes do not require an RFC.

## File layout

Proposals live under [`docs/engineering/rfc/`](rfc/README.md) and use the
numbering pattern `NNNN-slug.md`. The RFC index MUST be updated in the same
change that introduces or changes an RFC.

## Required sections

Each RFC MUST contain:

1. **Status** — `Draft`, `Review`, `Accepted`, `Rejected`, or `Superseded`.
2. **Summary** — one paragraph.
3. **Context and problem** — observed duplication, drift, or risk.
4. **Decision** — the approved baseline and its normative constraints.
5. **Consequences** — files, processes, tests, and owners affected.
6. **Non-goals** — bounded scope explicitly excluded.
7. **References** — authoritative documents.

## Process

1. Write a small proposal with one bounded problem and one decision. It MUST
   not bundle unrelated rewrites.
2. Mark it `Draft`, then move it to `Review`. Reviewers are the repository
   maintainers; the supervising Codex agent may review milestone work.
3. A reviewer changes the status to `Accepted` only when the proposal has:
   - a clear owner;
   - non-goals;
   - validation or contract-test consequences;
   - no new datastore and no dependency addition unless separately approved.
4. Accepted RFCs are immutable baselines. A later change that alters an
   accepted RFC MUST either supersede it explicitly or write a new RFC that
   references it.
5. Rejected RFCs are retained in place with the reason recorded in the index.

## Relation to ADRs

An RFC decides a bounded cross-cutting baseline. An ADR records a durable
architecture decision in
[`docs/architecture/ARCHITECTURE_DECISION_RECORD.md`](../architecture/ARCHITECTURE_DECISION_RECORD.md).
When an accepted RFC changes architecture, the ADR index MUST be updated in the
same change.

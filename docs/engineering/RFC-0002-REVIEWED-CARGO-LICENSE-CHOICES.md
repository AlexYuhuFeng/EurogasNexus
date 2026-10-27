# RFC-0002: Reviewed Cargo License Choices

Status: **Accepted for bounded implementation, 2026-10-28; release legal clearance remains open.**

Owner: Architecture and security review (root)

Reviewers: Root owner; security reviewer; release engineer; legal reviewer
(advisory)

Date: 2026-10-27

Decision class: dependency-policy and CI-gate exception mechanism

Related records:

- [Dependency Policy](../policies/DEPENDENCY_POLICY.md)
- [RFC process](RFC_PROCESS.md)
- [RFC template](RFC_TEMPLATE.md)
- [Dependency audit gate](../../scripts/ci/audit_dependencies.py)
- [SBOM and notice generator](../../scripts/release/generate_sboms.py)
- [Rust license-gate tests](../../tests/security/test_rust_license_audit.py)
- [npm license-gate tests](../../tests/security/test_npm_license_audit.py)
- [SBOM generation tests](../../tests/release/test_sbom_generation.py)
- [Python license text collector](../../scripts/release/collect_python_license_texts.py)
- Desktop lock: [`clients/desktop/src-tauri/Cargo.lock`](../../clients/desktop/src-tauri/Cargo.lock)

## Summary

CI currently refuses two transitive Rust crates because their exact upstream
declaration is `MIT OR Apache-2.0 OR LGPL-2.1-or-later`: `r-efi` 5.3.0 and
`r-efi` 6.0.0. The policy deliberately rejects a restricted term anywhere in a
declared expression, so the gate does not accept the permissive MIT branch
merely because it exists.

This RFC proposes a narrow, reviewable alternative to skipping the gate:
a public record of exact crate identities and exact declared expressions that
selects `MIT` for those identities only. The record would bind name, version,
canonical crates.io source, Cargo.lock SHA-256 checksum, exact expression,
chosen license, and the SHA-256 of the exact MIT text. Any unknown, changed or
mismatched field fails closed. The original expression and the chosen license
remain visible in the SBOM and notices.

This is not legal clearance and not a general SPDX `OR` parser. No record is
approved by this draft: the upstream MIT text bytes and hash could not be
collected in the review environment, so the example records below are
deliberately marked `proposed` with a null text hash.

## Problem and evidence

### CI failure

The reported failing CI commit is
`09e8ac919d0cf05a6470ae813bee2c79106aa4e0`; the inspected worktree HEAD is
`eb68fadc33aec4d44124a02f4eb09c2ce2138a18`, whose history contains that
commit. The `Dependency license & CVE audit` job runs:

```text
python scripts/ci/audit_dependencies.py --cargo-lock clients/desktop/src-tauri/Cargo.lock
```

The release `Dependency vulnerability scan` job (`dependency-scan`) runs the
same Cargo command before publishing scan evidence. Neither job has
`continue-on-error`; the gate is required by the existing CI/release path.

CI reports that only these two crates fail the declared-license check:

| Crate | Version | Lock source | Lock checksum (SHA-256 of the crate archive) | Reported declared expression |
| --- | --- | --- | --- | --- |
| `r-efi` | 5.3.0 | `registry+https://github.com/rust-lang/crates.io-index` | `69cdb34c158ceb288df11e18b4bd39de994f6657d83847bdffdbd7f346754b0f` | `MIT OR Apache-2.0 OR LGPL-2.1-or-later` |
| `r-efi` | 6.0.0 | `registry+https://github.com/rust-lang/crates.io-index` | `f8dcc9c7d52a811697d2151c701e0d08956f92b0e24136cf4cf27b57a6a0d9bf` | `MIT OR Apache-2.0 OR LGPL-2.1-or-later` |

The local lock confirms both identities, sources and checksums at
`clients/desktop/src-tauri/Cargo.lock` lines 2329-2339. It also confirms the
reverse edges: `getrandom` 0.3.4 depends on `r-efi` 5.3.0, and `getrandom`
0.4.2 depends on `r-efi` 6.0.0 (lines 1018-1041).

### Why the gate fails

`FORBIDDEN_LICENSE_TERMS` includes `lgpl`
(`scripts/ci/audit_dependencies.py` lines 88-99). The shared
`_declared_license_problem()` lowercases the whole declared value and rejects a
restricted term anywhere in the value, including inside `OR`, `AND` or `WITH`
(lines 292-322). `audit_cargo_lock()` applies that shared check to every
third-party `cargo metadata` package, after matching the `Cargo.lock`
inventory by exact name/version/source identity (lines 691-931).

This is intentional. The npm tests pin `MIT OR GPL-3.0-only` as a failure, and
the Rust tests pin the same shared checker. The gate is a review-required
detector, not a legal interpreter. Its documented scope explicitly says it
does not interpret `OR`/`WITH` and does not clear redistribution obligations
(`docs/policies/DEPENDENCY_POLICY.md`, "Rust crate graph" and "What the audits
do not cover").

### Why the dependency cannot simply be removed from the graph

`r-efi` is a target-specific transitive dependency used by `getrandom` for UEFI
targets. It is not expected to be linked into the Windows or Linux desktop
binary, but the policy deliberately audits the full resolved graph:
`cargo metadata --locked --format-version 1 --all-features`, with no
`--no-deps` and no target filter. The audit's own output labels this as
"conservative full-graph coverage", not shipped-artifact proof. Only the
dependency edges are locally verified here; the exact target configuration in
the cached `getrandom`/`r-efi` manifests could not be re-read, so the
non-shipment expectation is not used as a legal basis for this proposal.

Consequences:

- Editing `Cargo.lock` to delete the `r-efi` entries is not a fix. It breaks
  `--locked` resolution, hides a dependency the resolver still requires, and is
  exactly the kind of manual lock surgery the policy and release gates exist to
  prevent.
- A target-filtered audit would omit an inactive-target crate. That is a broad
  policy change, not a bounded license review, and would let other
  target-specific restricted licenses escape the full-graph gate.
- Patching `getrandom` to remove its UEFI dependency, forking the crate, or
  adding a `[patch.crates-io]` fork creates a new supply-chain and maintenance
  problem. It does not make the upstream license question disappear for every
  other consumer or future lock refresh.
- Upstream could narrow its declaration to `MIT`, but that is outside this
  repository's control and cannot unblock the current CI.
- A UEFI runner would not make the finding disappear: the full-graph audit
  already includes the crate from any host, and the policy deliberately does
  not reduce coverage to the host target.

The bounded question is therefore not "how do we remove the crate?" but "can
we record a specific, exact, reviewed choice of the upstream MIT alternative
without weakening the gate for anything else?"

### Evidence status

| Claim | Status in this review |
| --- | --- |
| CI at `09e8ac9` fails the Rust license gate | Reported by the owner; GitHub Actions logs were not fetchable in this environment, so not independently reproduced. |
| Only `r-efi` 5.3.0 and 6.0.0 fail | Reported by CI; a full `cargo metadata` re-run was not possible here, so not independently confirmed for every other node. |
| Both `r-efi` identities, sources, checksums and reverse edges are in the lock | Verified by direct read of `clients/desktop/src-tauri/Cargo.lock`. |
| The gate rejects the LGPL branch and does not interpret `OR` | Verified by direct read of `scripts/ci/audit_dependencies.py`. |
| The gate and its negative tests are wired into CI and release | Verified by direct read of both workflows and the test files. |
| Upstream declares exactly `MIT OR Apache-2.0 OR LGPL-2.1-or-later` | Reported by the owner and supported by the CI failure; the upstream `Cargo.toml` and docs.rs pages could not be fetched in this environment. |
| Exact MIT text bytes and SHA-256 | Not collected. The WSL cargo cache was inaccessible and public web fetch returned a non-public-address error. No digest is invented here. |
| The proposed records are approved | No. This document is a draft; the example records are `proposed`. |

The review environment's shell was blocked by the known temporary ACL lock, and
the WSL share reset. No shell-ACL bypass was attempted. Public web fetches for
GitHub, docs.rs, crates.io and static.crates.io were refused by hostname
resolution, so upstream text and docs.rs source pages must be checked by the
root reviewer in a normally network-enabled review session.

## Decision

If accepted, this RFC adds a **reviewed-choice record** mechanism for Cargo
declared-license failures. It is not a skip, not a warning-only path, and not a
general allowlist.

### The record

The public, reviewed data lives at:

```text
docs/policies/reviewed-cargo-license-choices.json
```

The exact MIT text is stored next to it for evidence and notice generation, for
example:

```text
docs/policies/licenses/r-efi-5.3.0-MIT.txt
docs/policies/licenses/r-efi-6.0.0-MIT.txt
```

The file is public, contains only upstream license metadata and public URLs,
and contains no credentials, private registry URLs or personal paths.

A record has these required fields:

| Field | Requirement |
| --- | --- |
| `schema_version` | Exactly `1`. |
| `records[].id` | Stable public record id, unique in the file. |
| `records[].state` | `proposed` or `approved`. Only `approved` can exempt. |
| `package.name` | Exact crate name, case-sensitive. |
| `package.version` | Exact version, no ranges, no wildcards, no "latest". |
| `package.source` | Exact canonical crates.io source string from the lock. |
| `package.checksum_sha256` | 64 lowercase hex characters; must equal the Cargo.lock checksum. |
| `declared_expression` | Exact value `cargo metadata` reports for the package, which must equal the reviewed upstream `license` string; no normalization or reordering. |
| `expression_terms` | Human-authored, ordered flat list of exact license identifiers. |
| `chosen_license` | Exactly `MIT` for this RFC. |
| `license_text.repo_path` | Repo-relative path under `docs/policies/licenses/`; no absolute path, `..`, symlink, junction or backslash. |
| `license_text.sha256` | 64 lowercase hex characters when `state` is `approved`; `null` for an unapproved proposal. |
| `license_text.upstream_url` | Public HTTPS evidence URL for the exact upstream text file; a source directory is acceptable only in a `proposed` record whose exact file name is still being confirmed. |
| `review.approved_by` | Roles, not personal names; empty until approved. |
| `review.approved_on` | ISO date, or `null` until approved. |
| `review.reference` | Public approval/record reference, or `null` until approved. |

The proposed initial records are exactly these two:

| Field | `r-efi` 5.3.0 | `r-efi` 6.0.0 |
| --- | --- | --- |
| Name | `r-efi` | `r-efi` |
| Version | `5.3.0` | `6.0.0` |
| Source | `registry+https://github.com/rust-lang/crates.io-index` | `registry+https://github.com/rust-lang/crates.io-index` |
| Checksum SHA-256 | `69cdb34c158ceb288df11e18b4bd39de994f6657d83847bdffdbd7f346754b0f` | `f8dcc9c7d52a811697d2151c701e0d08956f92b0e24136cf4cf27b57a6a0d9bf` |
| Declared expression | `MIT OR Apache-2.0 OR LGPL-2.1-or-later` | `MIT OR Apache-2.0 OR LGPL-2.1-or-later` |
| Terms, in order | `MIT`, `Apache-2.0`, `LGPL-2.1-or-later` | `MIT`, `Apache-2.0`, `LGPL-2.1-or-later` |
| Chosen license | `MIT` | `MIT` |
| Text SHA-256 | **not recorded in this draft** | **not recorded in this draft** |

### Matching contract

The audit MUST treat a record as an exact identity, not as a license-name
allowance:

1. Load the record file from a fixed repository-relative path. There is no
   environment variable, CLI flag or alternate path for adding approvals. An
   absent file means zero exemptions; once present, malformed content fails
   closed.
2. Reject malformed JSON, unknown schema versions, duplicate record ids,
   duplicate `(name, version, source)` identities, unknown fields, invalid
   types and invalid checksum/path/hash shapes.
3. A record is effective only when `state` is `approved`, the text hash is
   present, and the referenced text file exists, is a regular file, is not a
   symlink or junction, and hashes to the recorded digest.
4. Match a record to the `Cargo.lock` inventory and `cargo metadata` entry only
   by exact `(name, version, source)`. The lock checksum must match, and the
   exact metadata `license` value must equal `declared_expression`.
5. Require `" OR ".join(expression_terms) == declared_expression`. This is a
   fixed, human-authored flat disjunction, not an SPDX parser. Reject
   parentheses, `AND`, `WITH`, `LicenseRef-`, unknown placeholders, empty
   terms, repeated terms, or any term that is not an exact identifier.
6. Require `chosen_license == "MIT"` and require it to be one of the terms.
   The chosen license must also pass the existing generic permissive check.
7. Do not require or imply that the other terms are permissive. They remain in
   the original expression and are not approved. Only the exact package version
   is allowed to proceed, and only for the chosen MIT branch.
8. If a record exists for an identity but any field mismatches, fail closed.
   Do not silently fall back to the generic license path and do not ignore the
   record.
9. If an approved record is not matched exactly once in the audited graph, fail
   closed as a stale record. Removing a crate or changing the lock requires the
   record set to be updated and re-reviewed.
10. Do not apply records to git, path, alternate-registry or non-crates.io
    packages. Those continue to fail the existing provenance-review path.
11. Do not apply records to npm or Python modes. Those gates keep their current
    strict behavior; the record mechanism is Cargo-only.
12. Do not change the generic `_declared_license_problem()` behavior. Packages
    without an exact approved record continue to fail on any restricted term,
    including `MIT OR GPL-3.0-only`, `MIT AND BUSL-1.1`, `... WITH ...`,
    `LicenseRef-`, `UNKNOWN` and file-only references.

The audit MUST report reviewed choices as a separate category, not as packages
that "passed the declared-license check". The final message must distinguish
"no unreviewed restricted terms detected" from "N exact reviewed choices
applied"; it must never claim that the restricted branch itself was approved.

### SBOM and notice contract

The existing generated evidence must remain the single source of truth:

- `licenseDeclared` in the SPDX package MUST be the original upstream
  expression, e.g. `MIT OR Apache-2.0 OR LGPL-2.1-or-later`. It MUST NOT be
  replaced by `MIT`.
- `licenseConcluded` MUST be `MIT` for an approved exact record, with a
  `licenseComments` value naming the record id, the exact expression, the
  chosen license and the text SHA-256. It is a project-selected compliance
  branch, not a legal conclusion. The original expression remains in
  `licenseDeclared`; neither field may be omitted.
- The Cargo.lock checksum remains the SPDX package checksum.
- `THIRD_PARTY_NOTICES.md` MUST list both the original expression and the
  selected license, for example:
  `r-efi 5.3.0 - declared: MIT OR Apache-2.0 OR LGPL-2.1-or-later; selected:
  MIT (record RCLC-...; text SHA-256 ...)`.
- The exact MIT text and copyright notice MUST be delivered as notice
  evidence, not merely named. The repo copy MUST be byte-for-byte the exact
  upstream text selected by the reviewer; do not reformat, rewrap or
  regenerate it. Reuse the existing text-collection standards from
  `scripts/release/collect_python_license_texts.py` and
  `scripts/release/verify_python_license_texts.py`: repo-relative paths, exact
  bytes, SHA-256, size, no traversal or symlink, and a manifest binding the text
  to the record. Do not invent a second evidence format.
- The release SBOM manifest MUST record the text file hash and size. The
  release artifact/installer must include the MIT text and notice with the
  desktop artifact. A record alone does not satisfy MIT's notice obligation.
- If a record is `proposed`, has a null hash, or its text file is missing,
  tampered or extra, SBOM/notice generation MUST fail rather than emit a
  partial or misleading notice.

The existing `scripts/release/generate_sboms.py` already has the right identity
and checksum inputs (`rust_packages()`), but currently emits `NOASSERTION` for
all Rust packages because `Cargo.lock` carries no license field. This proposal
does not change that default for unrecorded packages. It adds a narrow
annotation path for approved records only, using one shared loader so the audit
and SBOM generator cannot disagree about what matched.

### Review and approval

A change to a record or its text is a policy-level change, not a routine
dependency bump. At minimum:

- root owner approval;
- security reviewer concurrence;
- release-engineer confirmation that the text and notice are packaged;
- advisory legal review of the selected branch and notice obligation;
- a public `review.reference` that a reviewer can inspect.

CI can verify exact matching and hashes; it cannot verify human intent. A person
with commit access can propose a malicious record. The controls are the exact
checksum/source/expression/text hash, the public review record, and required
root/security review, not an automated claim that a record is legitimate.

### What the decision does not do

- It does not approve `LGPL-2.1-or-later` or `Apache-2.0` for this crate or any
  other crate. It selects MIT and preserves the other branches only as the
  upstream declaration.
- It does not approve any future `r-efi` version, any other crate, any other
  registry, any other source, or any future expression. A new version or
  expression requires a new reviewed record.
- It does not allow `AND`, `WITH`, nested expressions, `LicenseRef-`, unknown
  placeholders or file-only references.
- It does not skip the license gate, remove it from CI, add
  `continue-on-error`, rename the required job, or change the stable gate
  policy.
- It does not edit `Cargo.lock` or `Cargo.toml`, downgrade `getrandom`, vendor
  or patch `r-efi`, or change the desktop build.
- It does not assert that `r-efi` is absent from the shipped artifact. The
  full-graph gate still covers it, and notice packaging must not rely on
  non-shipment without evidence.
- It does not provide legal advice, legal clearance, a patent analysis, a
  trademark analysis, or a conclusion about combined works or LGPL relinking.
- It does not waive MIT's copyright-notice and permission-notice obligation,
  or any other obligation that applies to the distribution.

## Alternatives considered

| Alternative | Why it is not selected |
| --- | --- |
| Mark the Rust gate `continue-on-error`, delete the step, or skip the job | Hides the finding and all future findings; weakens the release gate; does not create review evidence. |
| Edit `Cargo.lock` to remove the `r-efi` entries | Breaks `--locked` consistency, hides a resolver-required crate, and is manual lock surgery. |
| Run the audit only for the host target, or use `cargo metadata --filter-platform` | Broad policy change; lets target-specific restricted licenses escape full-graph coverage; contradicts the documented conservative scope. |
| Fork/patch `getrandom` or `r-efi` to drop UEFI support | New supply-chain surface, maintenance burden, and an unreviewed fork; does not solve the upstream declaration. |
| Add a global SPDX `OR` parser that accepts any permissive branch | Broad legal interpretation; would auto-approve unknown combinations, `AND`/`WITH`, and future restricted expressions without per-crate review. |
| Add a blanket allowlist for `MIT`, `Apache-2.0`, `LGPL-2.1-or-later` names, or a wildcard `r-efi` rule | Approves unrelated crates/versions and fails the "explicit review" requirement. |
| Use `cargo-deny` exceptions or a new license tool | New tool/configuration surface; exceptions are typically name/version based, not bound to exact text hash and SBOM/notice evidence; does not replace the existing gate. |
| Ask upstream to relicense to MIT only | Reasonable long-term request, but outside repository control and cannot unblock current CI. |
| Keep the gate red until upstream changes | Safe but blocks all delivery for a target-inactive dependency; the bounded reviewed choice is the smaller, reversible change. |

## Scope and non-goals

### In scope

- The dependency-policy decision and record format for exact reviewed Cargo
  license choices.
- The exact two `r-efi` identities and the MIT branch.
- The audit, SBOM, notice, test and acceptance changes needed to make that
  choice reviewable.
- Public evidence references and an explicit record of what remains
  unverified.

### Non-goals

- No change to `Cargo.lock`, `Cargo.toml`, Tauri configuration, desktop
  runtime code, API, database, Web client or Python/npm dependencies.
- No new service, datastore, license service, network call at audit time, or
  new runtime dependency.
- No general license-allowlist program.
- No legal clearance or redistribution approval.
- No RFC index, ADR, policy, CI or implementation edit in this review task.
  Those follow only after root review.

## Owners and responsibilities

| Role | Responsibility |
| --- | --- |
| Root owner / architecture reviewer | Accepts or rejects this RFC; confirms the upstream expression; approves or rejects each record; owns the final policy decision. |
| Security reviewer | Checks the exact-match and fail-closed invariants, the text-path safety, and that no wildcard/broad approval path exists. |
| Release engineer | Confirms the MIT text and notice are packaged with the desktop artifact and that SBOM/notice hashes are bound into the release evidence. |
| Dependency-policy maintainer | Keeps the record schema, policy text and gate tests aligned; rejects stale or duplicate records. |
| Legal reviewer (advisory) | Reviews the selected MIT branch, notice obligation, patent consideration and any distribution-specific question. This role does not convert the record into legal clearance. |

Root acceptance through the autonomy policy is permitted only after substantive
review of the actual upstream `Cargo.toml`, exact MIT text, hashes and tests.
This draft does not self-accept.

## Security and legal boundaries

### Security

- The record is public source, not runtime configuration. There is no hidden
  environment override and no network lookup during the audit.
- Exact source and checksum bind the record to the published crate archive.
  A republished, mirrored or alternate-registry crate with the same
  name/version cannot use the record.
- Exact expression binding prevents a silent relicense from inheriting an old
  approval.
- Text hash and path checks prevent a record from pointing at an arbitrary or
  swapped file. Refuse absolute paths, `..`, backslashes, symlinks and
  junctions.
- Stale and duplicate records fail closed, so an approval cannot lie dormant
  and later apply to a different graph without review.
- Cargo failure output remains sanitized; this proposal does not add raw tool
  output or credentials to logs.
- The CVE audit, npm audit, Python metadata audit and provenance-review path
  remain separate and unchanged.
- Record changes require root/security review. CI's exact matching is a
  technical control, not a substitute for review of a malicious commit.

### Legal

- The record asserts a factual reading: the exact upstream package version
  offers MIT as one alternative, and the project chooses to comply with MIT
  for that version. It does not assert that the other alternatives are
  unavailable.
- MIT requires the copyright notice and permission notice to accompany copies
  or substantial portions. The record binds the exact text, and release
  packaging must include it. Naming "MIT" in a record or SBOM is not enough.
- The Apache-2.0 patent grant is not selected by choosing MIT. Reviewers should
  consider whether that matters for the distribution. This RFC does not give a
  patent conclusion.
- No statement is made about LGPL relinking, combined works, reverse
  engineering, trademarks, export control or enforceability.
- The record and its SBOM/notice output are technical review evidence. They are
  not a legal opinion, not a commercial clearance, and not a certification that
  redistribution obligations are fully satisfied.

## Compatibility and migration

- No dependency, lockfile, build or runtime behavior changes. The same crate
  bytes are already in the graph; this is an audit/evidence decision only.
- The existing CI job name `Dependency license & CVE audit` and the release
  `dependency-scan` producer remain in place. Stable-gate required job names do
  not change.
- The audit's output gains a separate reviewed-choice category. Existing
  "restricted terms" failures remain failures. No package is reclassified
  unless it has an exact approved record.
- The SPDX Rust document changes only for approved records: original
  `licenseDeclared`, selected `licenseConcluded`, explanatory
  `licenseComments`, unchanged checksum. Other Rust packages remain
  `NOASSERTION` until separately reviewed.
- `THIRD_PARTY_NOTICES.md` content and hashes change, so release manifests,
  checksums and signatures that bind those files must be regenerated. That is
  expected evidence refresh, not a policy weakening.
- Record/schema changes require a policy-level review; a version bump that
  changes the lock checksum invalidates the record and returns CI to red until
  re-reviewed.
- No database, API, SDK, Web, CLI or Tauri migration is involved.

## Rollback

- Remove the two records, or set them back to `proposed`: the gate returns to
  its current fail-closed behavior and CI is red on `r-efi` again. No dependency
  or runtime rollback is needed.
- Revert the audit/SBOM/tests changes: the previous gate and `NOASSERTION`
  notices return. The release remains blocked until the license question is
  resolved again.
- Do not roll back by editing the lock, deleting `r-efi`, filtering the target,
  disabling the gate, or adding a broad license-name allowance.
- A tampered or missing MIT text, hash mismatch, stale record or source/version
  change is an automatic rollback-to-fail-closed condition.

## Tests and acceptance criteria

### Focused tests to add or extend

In `tests/security/test_rust_license_audit.py`:

- Exact approved record for both `r-efi` versions passes the audit, and the
  output reports two reviewed choices separately from ordinary passes.
- Version, source, checksum, `declared_expression`, `expression_terms` order and
  `chosen_license` mismatches each fail closed.
- A record for a git, path or alternate-registry package is refused.
- `AND`, `WITH`, parentheses, `LicenseRef-`, `UNKNOWN`, `NOASSERTION`, a
  file-only reference and a non-MIT chosen license are refused.
- A record with a missing/incorrect text hash, a missing text file, a symlink,
  a traversal path or a non-canonical path is refused.
- Duplicate records, duplicate identities and stale approved records are
  refused.
- A proposed record does not exempt; a malformed record file fails closed.
- An unrecorded `MIT OR GPL-3.0-only` package still fails, proving the generic
  gate was not weakened.
- npm and Python modes ignore the Cargo record file and retain their existing
  strict tests.

In `tests/release/test_sbom_generation.py`:

- An approved record produces `licenseDeclared` equal to the original
  expression, `licenseConcluded` equal to `MIT`, a record/hash comment, and the
  unchanged Cargo.lock checksum.
- The notice lists both the original expression and the selected MIT branch.
- The exact MIT text is copied/verified, its hash and size are recorded, and a
  tampered or missing text fails generation.
- A proposed record or null hash fails generation instead of emitting a
  partial notice.
- An unrecorded Rust package remains `NOASSERTION`; no unrelated package
  changes.

In the workflow-wiring tests:

- The Cargo gate still runs in `.github/workflows/ci.yml` and
  `.github/workflows/release.yml` before evidence publication.
- No `continue-on-error`, skip, target filter or new required job name is
  introduced.
- The record file is a reviewed input, not a runtime override.

The existing Rust test module states that `cargo` is not installed in the test
environment and that live `cargo metadata` acceptance is pending. The fixture
tests prove the matching boundary; the real CI job remains the live acceptance
check. This review could not execute that live check because the shell was
blocked by the known temporary ACL issue.

### Acceptance criteria

- [ ] Root reviewer confirms the exact upstream `Cargo.toml` expression for
      both versions from the primary repository and/or docs.rs exact-version
      source, without normalizing or reordering it.
- [ ] Root reviewer records the exact upstream text URL, exact MIT text bytes
      for both versions, writes byte-identical version-specific text files, and
      records matching SHA-256 values in the two records.
- [ ] Record state is `approved` with root/security roles and a public review
      reference; no record is approved by this draft.
- [ ] The audit matches only the exact name/version/source/checksum/expression/
      terms/MIT choice and fails closed on every mismatch.
- [ ] The generic restricted-term gate remains unchanged for all unrecorded
      packages; npm/Python modes are unaffected.
- [ ] SBOM and notices retain the original expression and the chosen MIT
      license, include the exact MIT text, and bind the text hash.
- [ ] The desktop release artifact includes the MIT text and notice, or the
      release remains blocked with an explicit evidence gap.
- [ ] The successor CI run at the reviewed commit has the required
      `Dependency license & CVE audit` job green, with no skip or
      `continue-on-error`.
- [ ] No legal-clearance claim is made in release notes, notices or this RFC.
- [ ] Rollback is tested by removing/altering the record and observing the gate
      return to failure.

## Implementation and verification

This task is read-only diagnosis and proposal. No code, policy, CI, RFC index,
ADR, commit, push, secret, worker or environment credential was changed. The
only produced file is this RFC.

If root accepts the direction, a separate bounded ExecPlan should cover:

1. Add the two approved records and their exact MIT text files, if and only if
   root/security review has completed.
2. Add one shared record loader/validator used by
   `scripts/ci/audit_dependencies.py` and
   `scripts/release/generate_sboms.py`.
3. Extend the Cargo audit output, SBOM package fields, notices and SBOM
   manifest with the reviewed-choice evidence.
4. Add the focused tests above and update expected counts/text only where the
   approved records change them.
5. Update `docs/policies/DEPENDENCY_POLICY.md` with the narrow mechanism and its
   limits, in the same reviewed change as the implementation.
6. Add the RFC to `docs/engineering/RFC_INDEX.md` only after acceptance, and
   append the architecture decision only if root decides an ADR is required.
7. Re-run CI and the release `dependency-scan` job; do not claim a pass from a
   local fixture run.

No implementation should start from this draft alone.

## Evidence references

### Local evidence inspected

- `docs/policies/DEPENDENCY_POLICY.md`, "Restricted Licenses", "Rust crate
  graph (cargo mode)" and "What the audits do not cover".
- `scripts/ci/audit_dependencies.py`, `FORBIDDEN_LICENSE_TERMS`,
  `_forbidden_hit()`, `_declared_license_problem()` and
  `audit_cargo_lock()`.
- `scripts/release/generate_sboms.py`, `rust_packages()`, `_add_packages()`
  and `notices()`.
- `scripts/release/collect_python_license_texts.py` and
  `scripts/release/verify_python_license_texts.py`, for the text-evidence
  path/hash/size invariants reused above.
- `clients/desktop/src-tauri/Cargo.lock` lines 1018-1041 and 2329-2339.
- `THIRD_PARTY_NOTICES.md` lines 256-257, which currently record both `r-efi`
  versions as `NOASSERTION`.
- `tests/security/test_rust_license_audit.py`, `tests/security/test_npm_license_audit.py`,
  `tests/security/test_dependency_audit.py`,
  `tests/release/test_sbom_generation.py`.
- `.github/workflows/ci.yml` `dependency-audit` job and
  `.github/workflows/release.yml` `dependency-scan` job.
- `docs/engineering/RFC_PROCESS.md` and `docs/engineering/RFC_TEMPLATE.md`.

### Primary upstream references

- Upstream repository: <https://github.com/r-efi/r-efi>
- `r-efi` 5.3.0 docs.rs: <https://docs.rs/crate/r-efi/5.3.0>
- `r-efi` 5.3.0 Cargo.toml source:
  <https://docs.rs/crate/r-efi/5.3.0/source/Cargo.toml>
- `r-efi` 6.0.0 docs.rs: <https://docs.rs/crate/r-efi/6.0.0>
- `r-efi` 6.0.0 Cargo.toml source:
  <https://docs.rs/crate/r-efi/6.0.0/source/Cargo.toml>
- crates.io API, 5.3.0: <https://crates.io/api/v1/crates/r-efi/5.3.0>
- crates.io API, 6.0.0: <https://crates.io/api/v1/crates/r-efi/6.0.0>
- Crate archive, 5.3.0:
  <https://static.crates.io/crates/r-efi/r-efi-5.3.0.crate>
- Crate archive, 6.0.0:
  <https://static.crates.io/crates/r-efi/r-efi-6.0.0.crate>

These are review references. They were not fetched in this environment; the
root reviewer must open them and copy the exact expression and text bytes into
the approved records.

## Appendix A: Proposed machine-readable records

These examples show the proposed shape and the exact identity/checksum values.
They are deliberately `proposed` and use `null` for the text hash. They MUST NOT
be copied into an `approved` record until the exact text bytes and hashes have
been collected and reviewed.

```json
{
  "schema_version": 1,
  "records": [
    {
      "id": "RCLC-0001",
      "state": "proposed",
      "package": {
        "name": "r-efi",
        "version": "5.3.0",
        "source": "registry+https://github.com/rust-lang/crates.io-index",
        "checksum_sha256": "69cdb34c158ceb288df11e18b4bd39de994f6657d83847bdffdbd7f346754b0f"
      },
      "declared_expression": "MIT OR Apache-2.0 OR LGPL-2.1-or-later",
      "expression_terms": ["MIT", "Apache-2.0", "LGPL-2.1-or-later"],
      "chosen_license": "MIT",
      "license_text": {
        "repo_path": "docs/policies/licenses/r-efi-5.3.0-MIT.txt",
        "sha256": null,
        "upstream_url": "https://docs.rs/crate/r-efi/5.3.0/source/"
      },
      "review": {
        "approved_by": [],
        "approved_on": null,
        "reference": null
      }
    },
    {
      "id": "RCLC-0002",
      "state": "proposed",
      "package": {
        "name": "r-efi",
        "version": "6.0.0",
        "source": "registry+https://github.com/rust-lang/crates.io-index",
        "checksum_sha256": "f8dcc9c7d52a811697d2151c701e0d08956f92b0e24136cf4cf27b57a6a0d9bf"
      },
      "declared_expression": "MIT OR Apache-2.0 OR LGPL-2.1-or-later",
      "expression_terms": ["MIT", "Apache-2.0", "LGPL-2.1-or-later"],
      "chosen_license": "MIT",
      "license_text": {
        "repo_path": "docs/policies/licenses/r-efi-6.0.0-MIT.txt",
        "sha256": null,
        "upstream_url": "https://docs.rs/crate/r-efi/6.0.0/source/"
      },
      "review": {
        "approved_by": [],
        "approved_on": null,
        "reference": null
      }
    }
  ]
}
```

## Appendix B: Gate invariants

A conforming implementation has these properties:

- `records` is an array; every record has exactly the fields above; unknown
  fields are rejected.
- `id` values and `(name, version, source)` identities are unique.
- `source` is one of the exact canonical crates.io source strings already
  recognized by `cargo_origin()`; no alternate registry is accepted.
- `checksum_sha256`, when approved, equals the Cargo.lock checksum and matches
  `^[0-9a-f]{64}$`.
- `declared_expression` is an exact string, not a normalized or reordered
  expression.
- `expression_terms` is an ordered flat list of exact identifiers; joining it
  with `" OR "` must reproduce `declared_expression` exactly. Parentheses,
  `AND`, `WITH`, `LicenseRef-`, unknown placeholders and empty/repeated terms
  are rejected.
- `chosen_license` is exactly `MIT` for this RFC and is present in
  `expression_terms`.
- `license_text.repo_path` is a repo-relative regular file under
  `docs/policies/licenses/`; absolute paths, traversal, backslashes, symlinks
  and junctions are rejected.
- An approved record requires a 64-hex text hash; the file must exist and
  match it.
- A record that does not match exactly once fails the audit; a record that
  matches an unapproved identity fails; a proposed record does not exempt.
- The generic restricted-term check still runs for every package without an
  exact approved record. `AND`, `WITH`, `LicenseRef-`, unknown placeholders and
  file-only references remain failures everywhere else.
- The audit output distinguishes reviewed choices from ordinary permissive
  passes and never claims the restricted branch was approved.
- The SBOM keeps the original expression in `licenseDeclared` and sets
  `licenseConcluded` to `MIT` for an approved record, only with the record
  comment and text hash.
- Notices contain both the original expression and the selected MIT branch,
  plus the exact MIT text and copyright notice evidence.
- There is no environment variable, CLI flag, wildcard, name-only rule,
  version range or alternate record path that can add an approval.

If any of these invariants cannot be implemented without a general SPDX
expression evaluator, the proposal should be rejected rather than widened.

## Root decision and independent evidence — 2026-10-28

Accepted under Architecture V2 `AUTONOMOUS_EXECUTION_POLICY.md` sections1-3
by the root architecture/integration reviewer after examining the actual CI
job122349588582, exact lock identities, source archives and upstream AUTHORS
texts. This is a technical dependency choice and notice-retention decision;
no separate human, legal, customer or redistribution-clearance review is claimed.
The draft-only/unavailable-evidence statements above preserve the worker review
history; this independent evidence supersedes those limitations for these two
public package artifacts only.

Root downloaded the exact archives from static.crates.io and checked each
SHA-256 against Cargo.lock before reading files without extracting paths.
Both AUTHORS files explicitly offer the MIT alternative and include its text
and copyright notices. Retain the **complete original AUTHORS bytes**, rather
than copying just a generic MIT template. Those public texts are at:

| Identity | Retained upstream AUTHORS SHA-256 | Reviewed choice |
| --- | --- | --- |
| r-efi5.3.0 | ff92bed461f50338dd703a9ba9aee496a425957873df1d91192776e4bdf5dda7 | MIT |
| r-efi6.0.0 | d027e91dbc9cdbb2f1190068e498bd6b61cff022b6a032b191021ba658d96111 | MIT |

Evidence paths: `docs/policies/licenses/r-efi-5.3.0-AUTHORS.txt` and
`docs/policies/licenses/r-efi-6.0.0-AUTHORS.txt`. Original archive checksums and
registry identities remain exactly those in Appendix A. Public source URLs:
https://static.crates.io/crates/r-efi/r-efi-5.3.0.crate and
https://static.crates.io/crates/r-efi/r-efi-6.0.0.crate.

Implementation MUST validate both the committed retained-text hash and the
actual Cargo-resolved package AUTHORS file hash before applying the choice.
SBOM/notice generation MUST retain original licenseDeclared, identify the MIT
choice and include the complete retained text and record identity. Other crates
and all mismatch/malformed/missing/unknown/custom/AND/WITH cases retain current
fail-closed behavior. No dependency versions or lock bytes change. Tests must
cover each identity/checksum/expression/text drift and unrelated restricted crate.

The retained text filename above supersedes Appendix A's proposed MIT-only
filename; the proposed/null approval examples are historical illustrative data,
not executable approved records. Only the reviewed, validated machine-readable
record produced by implementation may be used by the gate.

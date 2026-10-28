# RFC-0004: Multi-surface development and delivery pipelines

Status: accepted for implementation, 2026-10-28, root architecture review under
the autonomous execution policy and the owner's explicit cross-platform
maintenance requirement. Hosted results remain separate evidence.

## Problem and decision

PR-only duplicated desktop build definitions drifted from manual acceptance.
The portable binary was overwritten by a non-embedded Cargo build. Source SDK
tests did not prove the installed customer wheel worked outside the checkout.

Use one reusable native build workflow for Windows x64, Linux x64 and Linux
ARM64; use one reusable installed-wheel SDK workflow for Linux and Windows.
Main-branch pushes, PRs and manual CI call these workflows. Retain the shared
React Web client, existing Web build/browser tests and one FastAPI contract.
SDK adapters remain typed; no generator or duplicate business engine is added.

Native evidence binds source, locks, toolchains and artifact hashes. SDK evidence
binds the actual source HEAD, wheel hash, isolated import origin and six real
HTTP checks against the existing stateless economics endpoints. Neither is
installed GUI acceptance, signing or provider certification.

## Release gate alignment

G1 must require successful actual Actions leaf jobs for all three native matrix
members and both installed SDK members, in addition to its existing required
jobs. Reusable caller names alone are not API leaf job names. Missing, skipped,
failed or pending members remain failures under the existing same-SHA verifier.
The policy lists exact hosted names, and a structural contract follows reviewed
same-repository reusable calls and their explicit matrix members to detect drift.
It must reject unresolved expressions or unreviewed workflow references.

This strengthens G1. It does not authorize publication, change external
approvals, waive signing, or replace security, DR and artifact acceptance gates.
Existing release producers remain intact. Native release packaging must later
adopt the proven canonical Windows Python bootstrap without weakening its gates.

## Validation and maintenance

Keep one canonical toolchain declaration set. Rust action-pin contracts inspect
called workflows rather than assuming two steps reside in the parent file.
Feature changes carry backend, SDK and shared Web adapters plus exact values,
refusal, authorization and temporal tests for every affected access surface.
Record actual hosted jobs and artifacts before claiming pipeline acceptance.

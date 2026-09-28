# Container Image Promotion Plan

Date: 2026-09-28. Baseline `3bf13a6` (clean, equal `origin/main`). Read-only
assessment plus a repository-specific design proposal; nothing was executed
against a registry or GitHub and nothing is implemented. It is not a claim
about GHCR platform guarantees (tag/visibility/immutability/API behaviour is
stated from repository usage only, to be verified against the registry before
implementation is accepted) and not an approval or commercial/legal advice.

Parent register: [First customer pilot plan](FIRST_CUSTOMER_PILOT_PLAN.md)
(PILOT-C residual: `runtime-image` writes GHCR before the bundle gates exist).
Gate policy: [GA release gates](GA_RELEASE_GATES.md) (G19).

Status: the bounded implementation slice is now in code (§9). Section 1-8
remain the read-only baseline assessment and the design the slice implements;
§9 records what is implemented, what it deliberately does not claim, and which
registry behaviours still need a controlled rehearsal.

## 1. Current pipeline (evidence at this baseline)

`.github/workflows/release.yml` (line numbers at `3bf13a6`):

| Job | Lines | What it writes |
| --- | --- | --- |
| `resolve` | 33-65 | `release-context.json`: channel, `release_version`, app version, SHA |
| `validate` | 67-146 | G2 envelope; G1 via read-only same-SHA CI verification |
| `runtime-image` | 471-549 | pushes the API image to GHCR; `packages: write` |
| `deployment` | 552-595 | operator ZIP + `release-identity.json` (`repo@sha256:`) |
| `container-acceptance` | 827-873 | G19 envelope bound to the image digest |
| `assemble` | 683-801 | manifest/checksums/SBOM carrying the image digest |
| `attest` | 802-826 | OIDC attestation over `release-final` |
| `publish-preview-rc` / `publish-stable` | 874-1031 | gate, then `gh release create` (refuses an existing release) |
| `post-publish-verify` | 1032-1063 | re-download, checksums, attestations, digest-only image inspect |

`runtime-image` builds `deploy/runtime/Dockerfile.api` for
`linux/amd64,linux/arm64` and pushes two tags at build time: the semantic
channel tag (`X.Y.Z` stable, `X.Y.Z-preview` / `X.Y.Z-rc` otherwise - from
`app_version` + `channel`, never `release_version`) and the SHA-named
`sha-<full GITHUB_SHA>`, both from `validate` alone, before every remaining
job. The digest then travels as `image-metadata` into the ZIP identity
(`scripts/release/package_deployment_bundle.py:347`), G19, the manifest and
post-publish verification.

### Early customer tags today, and all consumers

| Early tag | Written by | Before which gates | Consumers |
| --- | --- | --- | --- |
| `X.Y.Z-preview` / `X.Y.Z-rc` | `runtime-image` | every job listed above except `validate`/`resolve` | installer source-development fallback (`scripts/install/windows/Install-EurogasNexusServerRuntime.ps1:143-155`); operators following `docs/release/RELEASE_READINESS.md` (~169), `docs/release/RELEASE_ENGINEERING_SPEC.md` §12, `docs/deployment/HANDOVER_INDEX.md:43` |
| `X.Y.Z` (stable) | `runtime-image` | as above | as above; the same fallback builds `X.Y.Z-stable`, a tag the workflow never publishes (recorded, not fixed here) |
| `sha-<full SHA>` | `runtime-image` | as above | documented rollback identity (SPEC §12/§15); no code consumer |

The semantic tag is not release-unique: a repeat dispatch or retry at the same
`app_version` + channel reuses and can overwrite it; the per-release GitHub tag
is the canonical `release_version` (`src/eurogas_nexus/release/versioning.py`).
Digest consumers (bundle identity, both install entry points, compose, manifest,
`post_publish_verify.py`) never depend on the semantic tag.

## 2. The gap

A run that later blocks (missing G5/G8/G10/G11, a failed gate, a refused
release) still leaves the customer-facing `X.Y.Z[-channel]` tag on GHCR as the
bytes of an unapproved attempt. `post_publish_verify.py` inspects the digest
only, so nothing ties the tag to the tested digest; `container-acceptance` logs
in to no registry, so G19 passes only while anonymous inspect is possible - the
package-visibility question is external and is not assumed here. Existing
published tags are acknowledged as-is: this plan deletes and overwrites
nothing.

## 3. Constraints binding the design

- Promotion changes status, not source: no rebuild, no re-push of layers
  (SPEC §6, §9); a rebuild would be a new release with new provenance.
- Published semantic tags are never silently replaced with different source
  (SPEC §15, `docs/release/SUPPLY_CHAIN.md`); deploy by `@sha256:` digest.
- The tag write must sit behind the same fail-closed validator every publish
  path runs (PILOT-C, no bypass flag, no exemption, no fabricated PASS), and no
  new datastore, service or gate vocabulary is introduced here.

## 4. Alternatives considered

| Option | Verdict |
| --- | --- |
| A. Status quo | Rejected: publishes the semantic tag pre-gate; no tag/digest check. |
| B. Retire semantic tags; digest-only distribution | Viable fallback: smallest registry surface, but changes the documented tag policy and leaves already-published tags untouched; revisit if promotion cannot be made safe. |
| C. Rebuild at promotion time | Rejected: different bytes than the G19-tested digest; not a promotion. |
| D. `pull`/`push` retag | Not preferred: risks losing the multi-platform index. Any manifest-copy alternative must prove exact digest preservation in a controlled registry test. |
| E. Candidate tags at build + gate-first manifest copy (preferred) | Build once; approved version tags are written only after gates pass. Candidates may still be visible. |

## 5. Preferred lifecycle (bounded implementation steps)

1. `runtime-image` stops pushing the semantic tag, keeps `packages: write` and
   pushes only run-attempt-unique candidates, e.g. `candidate-<run_id>-<attempt>`.
   Do not update `sha-<full SHA>` before acceptance: a rebuild of the same source
   need not have the same digest. Candidate exposure is staging, never approval.
2. Gate and release jobs are unchanged: G19 by digest, assemble, attest,
   `validate_stable_release.py`, `gh release create` with its existing
   refusal of an existing release.
3. New `promote-image` job, after the successful publish job (same `always()`
   + result pattern as `post-publish-verify`): download `release-final`,
   re-run the same validator on it (so the tag write itself is behind the
   gate), read the tested digest from the bundle's `image-metadata.json`
   (never a step output), log in to GHCR with the job-scoped `github.token`,
   then: inspect `$NAME:$CHANNEL_TAG` (any outcome other than a confirmed
   absence or a digest fails closed with no write); present with the tested
   digest -> no-op PASS (idempotent retry); present with a different digest ->
   FAIL, refuse, no write, escalate, never overwrite or delete; absent ->
   `docker buildx imagetools create --tag $NAME:$CHANNEL_TAG
   $NAME@$TESTED_DIGEST` (proposed manifest copy: registry write, no rebuild); then
   re-inspect and require exact digest equality with the G19/manifest digest
   and both `linux/amd64` and `linux/arm64` (parseable CLI form fixed in the
   implementation brief; ambiguous output fails closed). A mismatch after the
   write stops the run and escalates - the workflow holds no deletion authority.
4. Record the promotion result (run identity, tags, digests, outcome) as a
   workflow artifact; `post_publish_verify.py` may additionally assert
   tag -> digest when visibility and token scope are decided (D4).

Ordering and failure semantics (no false atomicity): GHCR and GitHub Releases
are separate systems with no shared transaction. The release write comes
first; the tag write is a convenience pointer recoverable by re-running the
promote job, and a release whose tag is missing never blocks installation
because the ZIP pins the digest.

| Crash state | Release | Channel tag | Recovery |
| --- | --- | --- | --- |
| After release, before tag | exists | absent | re-run `promote-image` |
| Tag equals tested digest | exists | correct | no-op PASS |
| Tag differs | exists | wrong | refuse; owner/incident decision (no deletion) |

Concurrency/idempotency: the existing workflow group
`eurogas-nexus-release-${{ github.ref }}` does not serialize promotion across
different refs and check-then-write is not atomic; no compare-and-swap is
assumed. Require repository-wide promotion serialization with cancellation off;
hold it across inspect/write/verify. Restrict other registry writers operationally:
this lock cannot prevent external writes. Matching tags are no-ops; mismatches
block. Apply these rules to any promoted SHA alias too (D6).

Minimum token permissions (per job, nothing else added):

| Job | contents | actions | packages |
| --- | --- | --- | --- |
| `runtime-image` (candidate) | read | - | write (unchanged) |
| `promote-image` | read | read (G1 re-derivation) | write |
| publish jobs, `post-publish-verify` | unchanged (`write`/`read`) | unchanged | none added |

## 6. Focused negative-test matrix (for the implementation turn)

Reuse existing patterns: `tests/release/test_publication_gate_enforcement.py`
(workflow parse, executed gate, mocked step replay) and
`tests/release/test_release_engineering.py` (permissions, pinning). No registry call.

| Case | Expected |
| --- | --- |
| Candidate tags list contains no semantic tag | workflow contract fails on drift |
| Inspect fails (auth/network) | no create call, non-zero, fail closed |
| Tag exists with a different digest | refusal, create never invoked (fake runner argv) |
| Tag exists with the tested digest | no-op PASS, idempotent re-run |
| Digest in `image-metadata.json` vs manifest/G19 disagree | refuse before any write |
| Post-write re-inspect shows another digest or a missing platform | FAIL, no further writes, escalation text |
| Promote job ordering vs publish job; no `continue-on-error`/bypass flag | parsed-job assertions |
| `packages: write` only in candidate + promote jobs | parsed permission map |
| Promote step must not contain `docker build`/`docker push`/build-push action | no-rebuild contract |
| Retry-state replay (release/tag combinations, above) | only the recoverable states write |

## 7. Remaining operational decisions (owner/operator)

- D1 GHCR package visibility and read principals verified externally; the
  workflow cannot prove it, and "not public" is not assumed.
- D2 Whether stable promotion of the tag reuses `environment: production`
  (second approval) or runs as a plain job after the approved publish.
- D3 Disposition of any pre-existing semantic tag whose digest does not match
  a future candidate (incident/version policy; no deletion, no overwrite).
- D4 Where tag -> digest verification lives (promotion job evidence vs
  `post_publish_verify.py`) and the token scope it requires.
- D5 The installer source-development fallback tag, including the
  `X.Y.Z-stable` mismatch - its own bounded brief; this plan does not touch it.
- D6 Confirm exclusive registry writers, promoted SHA-alias policy and candidate
  retention. Workflow serialization is mandatory, not an optional substitute
  for controlling external writers. No cleanup now.
- D7 Whether the promotion result becomes evidence in a future gate or stays a
  workflow artifact; no gate ID is invented here.

## 8. What this plan does not claim

No implementation, release, registry change, deletion or approval; no claim
that GHCR enforces immutable tags, private visibility or digest stability; no
pilot, production, commercial or legal certification. Candidate tags remain
pre-approval exposure for every principal that can read the package.

## 9. Implementation state

Bounded slice implemented in code and focused tests,
`tests/release/test_container_promotion.py`: the candidate-only build, the
gate-first serialized promotion jobs, and the fail-closed promotion tool. It
has **not** been exercised against a live registry, GitHub Release or workflow
dispatch, and no release was published for it.

### 9.1 Candidate-only build tags

`runtime-image` pushes exactly one staging tag per attempt:
`candidate-<run_id>-<attempt>` (`candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`).
The semantic channel tag (`X.Y.Z` / `X.Y.Z-<channel>`) and the `sha-<full SHA>`
alias are no longer written at build time. `sha-<commit>` alias naming is
retired for this slice rather than promoted: a rebuild of the same source need
not have the same digest, so an alias would be ambiguous. The immutable
identity remains the `@sha256:` digest recorded in `image-metadata.json` /
`release-manifest.json` and pinned inside the operator ZIP; every digest
consumer already uses the digest, not a tag. Candidate exposure is staging,
never approval: any principal that can read the package can see it.

### 9.2 Gate-first serialized promotion

Two new jobs run only after a successful publish **and** its post-publication
verification (explicit `needs` on `post-publish-verify`, so promotion cannot
race it):

- `promote-image` (preview/RC), and
- `promote-image-stable` (stable), which keeps the same `environment:
  production` boundary the stable publish uses.

Each job, in order: re-runs the same fail-closed
`scripts/release/validate_stable_release.py` gate on the same `release-final`
bundle (the tag write sits behind the gate; no bypass flag, and deliberately
no `--reject-existing-tag`, because the release must already exist at this
point), confirms the release read-only with `gh release view` (so a failed-job
rerun after release creation still reaches promotion, and no tag is written
without a successful release and gate), logs in to GHCR with the job-scoped
`github.token`, and runs `scripts/release/promote_image.py`. Job permissions
are exactly `contents: read`, `actions: read` (the gate's G1 re-derivation)
and `packages: write`. The promotion result (image, tag, tested digest,
observed digest, outcome, commands) is uploaded as the
`release-promotion-result` artifact.

### 9.3 Fail-closed promotion tool

`scripts/release/promote_image.py` reads the tested digest from the bundle's
`image-metadata/image-metadata.json` (never from a step output) and:

1. validates image, digest, channel tag and timeout before any command runs -
   refusing `latest`, `candidate-*` and the retired `sha-*` prefixes, and
   requiring a finite positive timeout (the library entry point validates too,
   not only the CLI); every command is an argv list (no shell) with a hard
   timeout, so validated inputs are never re-parsed as shell text;
2. inspects the tested digest with the documented `--raw` original-manifest
   output of `docker buildx imagetools inspect` and hashes the served bytes -
   never a reformatted rendering such as `--format '{{json .Manifest}}'`,
   because a Go-marshalled reconstruction is not the content-addressed
   original - requiring that hash to equal the tested digest, allowing for
   exactly one CLI-appended trailing newline; the interpretation that matched
   is applied to the tag in the same run so both digests share one explicitly
   verified basis;
3. parses those same bytes as JSON and requires a real image index
   (`application/vnd.oci.image.index.v1+json` or the Docker manifest-list
   media type) whose descriptors carry valid `sha256:` digests and report real
   `linux/amd64` and `linux/arm64` platforms; `arm64/v8` counts as arm64,
   `unknown/unknown` attestation descriptors are allowed and ignored, and any
   absent or ambiguous field refuses the run;
4. inspects the target tag and classifies the outcome over the full stdout and
   stderr before any display truncation - only an explicit registry
   manifest-missing marker (`MANIFEST_UNKNOWN` / "manifest unknown" wording,
   optionally "manifest not found") counts as absence; a generic "not found" -
   which can also mean a missing binary, an unreadable credential config or an
   unclassified registry failure - refuses with no write, as do
   authentication, permission, network, contextual HTTP 5xx, timeout and
   unparseable or unclassified output;
5. matching digest -> idempotent no-op PASS; a different observed digest ->
   refuse the conflict untouched. Refusing is policy, not capability: the
   registry credential itself is not restricted from overwriting the tag, and
   an external writer racing the inspect/copy pair is not excluded;
6. absent -> `docker buildx imagetools create --tag <name>:<channel>
   <name>@<tested digest>` (manifest copy: no rebuild, no layer push), then
   re-inspects and requires the exact tested digest with both platforms.

A post-copy inspection that does not confirm the tested digest fails the run
with escalation text instead of a success claim, and it does not prove that
the tag exists: the tag state is UNKNOWN (it may resolve to the tested digest,
to another digest, or not exist), so the run stops for manual inspection
rather than retrying or repairing.

### 9.4 Serialization and no false atomicity

Both promotion jobs share the repository-wide concurrency group
`eurogas-nexus-image-promotion` with `cancel-in-progress: false`, held across
inspect/write/verify. GHCR check-then-write is not atomic and the lock cannot
prevent an external writer: keeping this workflow the **exclusive writer** of
the package (no manual or other-automation pushes to these tags) remains a
documented operational prerequisite, and no atomicity is claimed for the
check/write pair.

### 9.5 Unverified here (open evidence before release acceptance)

- The live behaviour of `docker buildx imagetools create` against GHCR
  (whether the copied tag preserves the exact tested index digest and both
  platforms) **has not been exercised against any registry**. The tool is
  deliberately preparatory and fail-closed: if the copy cannot be verified
  post-write, the run fails instead of claiming a promotion.
- The exact bytes `docker buildx imagetools inspect --raw` prints (including
  whether the CLI appends a trailing newline), the explicit manifest-missing
  wording the registry client surfaces, and GHCR package visibility/read
  principals (§7 D1) still need a controlled registry rehearsal; visibility is
  not assumed, and any output shape the parser cannot classify refuses.
- No workflow run, tag write or release was dispatched for this slice: all
  evidence is code reading plus mocked-runner and workflow-parse tests.

### 9.6 Consequences to reconcile (not fixed here)

- The installer's source-development fallback (`Install-EurogasNexusServerRuntime.ps1`)
  finds `X.Y.Z-preview` / `X.Y.Z-rc` only after a successful promotion (the
  same tag as before, but later); its `X.Y.Z-stable` mismatch is unchanged and
  remains §7 D5.
- Pre-existing GHCR tags are untouched and no cleanup or deletion is
  performed (§7 D3/D6).

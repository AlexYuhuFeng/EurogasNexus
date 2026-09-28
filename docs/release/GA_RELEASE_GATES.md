# GA Release Gates

Machine-readable policy: `scripts/release/policy/stable_gate_policy.json`.
Enforcement: `python scripts/release/validate_stable_release.py`.

| Gate | Meaning | Stable mandatory | CR-12-era state (historical) |
| --- | --- | --- | --- |
| G1 CI | trusted workflow run evidence: same-SHA GitHub API verification of the completed CI run and its required jobs | yes (every published channel) | FAIL/PENDING_EXTERNAL unless the API confirms the run; local dry-run only records PENDING_EXTERNAL |
| G2 Unit/integration | full Python suite | yes | PASS (CR-13: 1316 passed/10 skipped) |
| G3 PostgreSQL migration | migrations + DB smoke on PostgreSQL 16 | yes | PASS (CR-13 fresh scratch 50 integration tests) |
| G4 Frontend build | Web build and packaging | yes | PASS (CR-13 web 50 tests + build) |
| G5 Desktop packaging | NSIS + architecture-specific DEB | yes | PASS (NSIS packaged; Linux matrix in CI) |
| G6 Installer smoke | clean Windows install/launch/uninstall | yes | PENDING_EXTERNAL |
| G7 Upgrade smoke | previous -> new version | yes | PENDING_EXTERNAL |
| G8 Security tests | automated security acceptance | yes | PASS local / external blocked |
| G9 Dependency vulnerability | pip/npm/cargo runtime scans | yes | PASS/PENDING_EXTERNAL per component |
| G10 SBOM | SPDX SBOMs generated | yes | PASS (CR-12 dry-run + CR-13 re-run) |
| G11 Provenance | GitHub OIDC attestation | RC/stable | PENDING_EXTERNAL locally |
| G12 Checksums | final SHA256SUMS verification | yes | PASS (CR-13 dry-run) |
| G13 Backup/restore evidence | automated restore drill | yes | PASS (CR-11 drill) |
| G14 Performance budget | baseline and CI load smoke | yes | PASS inside hard threshold; p95 target exceeded on dense UAT fixture (44.5/1668/3099.5) |
| G15 External security acceptance | real deployment review | yes | PENDING_EXTERNAL |
| G16 Commercial provider certification | licensed provider live acceptance | yes | PENDING_EXTERNAL |
| G17 Code signing | Authenticode-verified Windows installer | yes | PENDING_EXTERNAL |
| G18 UAT | real trader/user acceptance | yes | PENDING_EXTERNAL |
| G19 Container acceptance | immutable image digest inspected (amd64 + arm64) | RC/stable | digest-bound envelope written by the release `container-acceptance` job; not yet exercised by a release run |

The state column above is a historical CR-12/CR-13 slice, not current
disposition; the first-customer pilot plan is the current register.

Gate status vocabulary is only `PASS`, `FAIL`, `PENDING_EXTERNAL`,
`NOT_APPLICABLE`. PILOT-B requires every evidence file to be a schema-version 2
envelope (`scripts/release/evidence_envelope.py`) produced by an authorised
producer profile and bound to the full tested commit SHA, the tested subject
digest(s) for artifact/image-bound gates, the workflow run identity, the
producing environment and a fresh UTC timestamp. Missing evidence stays
PENDING_EXTERNAL; status-only, old-format, foreign, stale, future-dated,
malformed, relabelled or unapproved evidence fails closed. `NOT_APPLICABLE` is
refused unless the policy explicitly allows it for that gate, and external
gates can only become PASS through a bound envelope carrying an approval
identity configured in `authorized_external_approvals` (currently empty, so all
external gates stay PENDING_EXTERNAL). Envelope fields are self-declared text
bound to identity the release run re-derives; that is not cryptographic
provenance. Stable publication therefore fails closed today.

PILOT-B2 adds authoritative same-SHA CI binding for G1.
`scripts/release/write_ci_run_evidence.py` (release `validate` job) records what
the read-only GitHub API reports for the exact release commit's
`.github/workflows/ci.yml` push run, and `validate_stable_release.py`
re-derives that claim from the API in the strict `publish-stable` gate:
completed and successful run, matching run attempt, trusted repository and
workflow path, and every required job - including bilingual browser acceptance
at three viewports - actually successful. Jobs are read from the
attempt-specific jobs endpoint and the run is re-read afterwards, so a re-run
that lands mid-verification (attempt, status, conclusion or head SHA changed)
is refused; the transport refuses every HTTP redirect instead of following it,
so the credential is never forwarded to a `Location` host. A missing, pending,
failed, skipped-job, re-run-to-a-newer-attempt, redirected, malformed or
unreachable result stays blocked, and the local-dry-run flag never relaxes the
API check. The claim is never read from a URL or metadata file supplied by the
evidence: the API decides, so a copied envelope cannot pass on its own.
The jobs carrying `actions: read` are the G1 writer (`validate`) and the two
publish jobs whose gates re-derive the claim; each CI-verification step receives
`GH_TOKEN` and both publish jobs keep `contents: write` for the release write.
This binds the *source commit's* CI run, not acceptance of the packaged artifact
or image (that remains G19/install/upgrade evidence), and the other release-job
envelopes (G2/G3/G4/G12/G19) still carry self-declared producer run identity.

PILOT-C closes the publication path. `publish-preview-rc` now runs the same
`validate_stable_release.py` gate as `publish-stable` before its `gh release
create`, with no allow-missing, local-dry-run, `continue-on-error` or
conditional-step escape, and G1 is required for every published channel.
Preview and RC therefore block on their own channel's mandatory evidence
instead of publishing ungated: no CI job produces G5 (desktop packaging) or G10
(SBOM), and G11 (provenance) has no RC producer, so preview/RC runs fail the
gate and publish nothing until those producers exist. Missing real evidence
blocks; nothing is marked PASS, exempted or fabricated to turn the gate green,
and no release was dispatched to exercise it. Signed attestation remains open.

G8 now has a real CI producer (2026-09-28, baseline `7f36b37`).
`scripts/release/run_security_evidence.py` executes the fixed `tests/security`
suite itself (`sys.executable -m pytest tests/security` with a JUnit XML report
in an owner-only scratch workspace), derives the gate status from that executed
report and its structured selection evidence, and writes the source-bound G8
envelope with the executed counts, selection counts, case identifiers and
report digest. The release `validate` job runs it after the existing tests and
before the `release-validate-evidence` upload, so `security-tests.json` and its
retained `security-tests.junit.xml` companion are carried into the assembled
`release-assets/release-evidence/` directory the publication gate reads. It
fails closed with explicit FAIL evidence and a non-zero exit on a non-zero
pytest exit, an empty suite, any failure/error/skip, any deselection or case
removed by a collection hook, a missing/malformed/count-inconsistent report or
missing selection evidence, a dirty tracked worktree in release context, a
commit that does not match the checked-out HEAD (checked before and after the
run), a timeout or any other tool error; a non-empty
`PYTEST_ADDOPTS`/`PYTEST_PLUGINS` is refused outright and `-o addopts=` pins
the pytest configuration so the suite cannot be filtered, there is no
`--status` input and no way to pass in a pre-existing report, and
`write_gate_evidence.py` refuses any gate that declares an `evidence_runner`.
The checkout binding is source identity, not cryptographic provenance. This is
executed source security-test evidence only - not packaged-artifact security
acceptance, not an installation test and not a penetration test - and it leaves
G15/G16/G18 and every other external gate unchanged and PENDING_EXTERNAL. G5,
G10 and G11 producers remain missing.

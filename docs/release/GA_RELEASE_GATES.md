# GA Release Gates

Machine-readable policy: `scripts/release/policy/stable_gate_policy.json`.
Enforcement: `python scripts/release/validate_stable_release.py`.

| Gate | Meaning | Stable mandatory | CR-12-era state (historical) |
| --- | --- | --- | --- |
| G1 CI | trusted workflow run evidence | yes | PENDING_EXTERNAL (local dry-run only) |
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

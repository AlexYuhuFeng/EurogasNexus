# GA Release Gates

Machine-readable policy: `scripts/release/policy/stable_gate_policy.json`.
Enforcement: `python scripts/release/validate_stable_release.py`.

| Gate | Meaning | Stable mandatory | Current CR-12 state |
| --- | --- | --- | --- |
| G1 CI | trusted workflow run evidence | yes | PENDING_EXTERNAL (local dry-run only) |
| G2 Unit/integration | full Python suite | yes | PASS (local suite) |
| G3 PostgreSQL migration | migrations + DB smoke on PostgreSQL 16 | yes | PASS (CR-11 evidence) |
| G4 Frontend build | Web build and packaging | yes | PASS |
| G5 Desktop packaging | NSIS + architecture-specific DEB | yes | PARTIAL (NSIS local; Linux CI) |
| G6 Installer smoke | clean Windows install/launch/uninstall | yes | PENDING_EXTERNAL |
| G7 Upgrade smoke | previous -> new version | yes | PENDING_EXTERNAL |
| G8 Security tests | automated security acceptance | yes | PASS local / external blocked |
| G9 Dependency vulnerability | pip/npm/cargo runtime scans | yes | PASS/PENDING_EXTERNAL per component |
| G10 SBOM | SPDX SBOMs generated | yes | PASS |
| G11 Provenance | GitHub OIDC attestation | RC/stable | PENDING_EXTERNAL locally |
| G12 Checksums | final SHA256SUMS verification | yes | PASS |
| G13 Backup/restore evidence | automated restore drill | yes | PASS (CR-11 drill) |
| G14 Performance budget | baseline and CI load smoke | yes | PASS (CR-11 budget) |
| G15 External security acceptance | real deployment review | yes | PENDING_EXTERNAL |
| G16 Commercial provider certification | licensed provider live acceptance | yes | PENDING_EXTERNAL |
| G17 Code signing | Authenticode-verified Windows installer | yes | PENDING_EXTERNAL |
| G18 UAT | real trader/user acceptance | yes | PENDING_EXTERNAL |

Gate status vocabulary is only `PASS`, `FAIL`, `PENDING_EXTERNAL`,
`NOT_APPLICABLE`. External gates can only become PASS through an evidence file
referenced by the policy and committed/deployed by the operator; a CLI boolean
cannot mark them complete. Stable publication therefore fails closed today.

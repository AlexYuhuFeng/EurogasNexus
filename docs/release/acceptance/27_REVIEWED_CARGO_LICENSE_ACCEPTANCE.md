# Reviewed Cargo license-choice implementation acceptance

Root verification date:2026-10-28. Authority: accepted RFC-0002 and Decision16.
This is bounded technical evidence, not legal clearance or customer acceptance.

- Rust/npm/SBOM selection: **183 passed**, including exact identity, checksum,
  expression, actual and retained AUTHORS-text drift, malformed/proposed records
  and unrelated restricted declarations. Ruff passed.
- Actual WSL locked full-graph Cargo metadata audit: **434 third-party crates**,
  432 ordinary permissive declarations and the two exact reviewed MIT choices;
  no unreviewed license failures or provenance gaps. Root package is the same
  strictly verified exclusion. No target/feature filtering or gate skip.
- Real source-tree SPDX generation preserves each upstream triple declaration
  in licenseDeclared and records MIT in licenseConcluded for r-efi5.3.0/6.0.0
  only. Both complete original AUTHORS texts are retained in generated notices.
- The shared validator is explicitly included in the existing customer runtime
  tool allowlist and Docker COPY closure because the already shipped SBOM/audit
  tools import it. No tests, development producer or broad scripts tree is added.

Root corrected the worker's missing helper import and a test using `version`
instead of the SPDX `versionInfo` field. A proposed-record refusal test now
asserts the existing detector's exact `gpl` match inside LGPL, rather than an
invented different diagnostic. No approval or failure status was weakened.
Credential-bearing URL validation refuses without echoing the URL.

Ignored local evidence: reviewed-cargo-license-wsl.log and reviewed-license-sbom/
under `.local-runtime/delivery-20261027`. Fresh same-commit CI and final artifact
verification remain separate gates. Other packages, versions, sources, hashes
and expressions receive no approval from these records.

Customer-wheel/runtime import closure plus formerly failing extraction/config
contracts: **30 passed** after installing the unchanged hash-pinned build lock
into the test venv. The installed customer wheel excludes the simulator, preserves
the snapshot metadata seam and imports only the actual allowlisted tool payload.
Whole Python tree Ruff and repository Markdown links pass. The earlier full run
remains recorded as2failed/4288passed/62skipped/3errors; these focused checks
resolve its failures, while a final same-commit full run is still required.

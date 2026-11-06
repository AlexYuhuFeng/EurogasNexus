# Release Signing And Notarization

This document is the release signing pipeline stub. It supports local
validation with self-signed/test certificates and documents the production
signing path.

## Local test signing

Use test certificates only in a local CI/dev environment. Never commit
production private keys.

```bash
bash scripts/release/sign_release_artifacts.sh \
  --artifact release-assets/Eurogas-Nexus-Client-{VERSION}-windows-x64-setup.exe \
  --cert ./test-cert.pfx \
  --password "$TEST_CERT_PASSWORD"
```

## Windows production signing

Required inputs:

- Code-signing certificate / `.pfx` or hardware token
- `signtool` from Windows SDK
- Time-stamp server URL

```powershell
signtool sign /f $env:WINDOWS_SIGNING_CERT `
  /p $env:WINDOWS_SIGNING_PASSWORD `
  /tr http://timestamp.digicert.com `
  /td sha256 `
  /fd sha256 `
  "$artifact"
```

## Linux signing

```bash
gpg --detach-sign --armor --output "$artifact.asc" "$artifact"
```

## Notarization

Windows:

- Submit the signed `.exe` to Microsoft SmartScreen/Defender reputation review
  when required by the deployment owner.

macOS:

- Not currently a release target. If added later:
  - `codesign`
  - `notarytool submit`
  - staple

## CI integration

Add a release-only job that:

1. Downloads release artifacts.
2. Reads signing certificate from GitHub secrets.
3. Signs `.exe` and `.deb` artifacts.
4. Verifies signatures.
5. Uploads signatures alongside artifacts.

Private keys must never be checked into the repository.

## CR-12 policy-aware signer

`scripts/release/sign_release_artifacts.py` records one of the following per
artifact:

- Windows EXE/MSI: `authenticode_verified` (credentials configured, signed,
  timestamped, and verified) or `unsigned_pending_external` (credentials not
  configured). Stable publication is blocked for the latter.
- Linux DEB: `gpg_signed_verified` (key configured and signature verified) or
  `checksum_attestation_baseline` (SHA-256 + GitHub attestation; no APT
  repository is published).

Tauri updater signing is a separate trust mechanism and is not enabled in this
release. Do not confuse updater `.sig` files with Windows Authenticode.

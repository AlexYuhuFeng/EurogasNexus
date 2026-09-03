# Release Signing And Notarization

This document is the release signing pipeline stub. It supports local
validation with self-signed/test certificates and documents the production
signing path.

## Local test signing

Use test certificates only in a local CI/dev environment. Never commit
production private keys.

```bash
bash scripts/release/sign_release_artifacts.sh \
  --artifact clients/desktop/src-tauri/target/release/bundle/nsis/Eurogas-Nexus-Client-0.5.0-x64-setup.exe \
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

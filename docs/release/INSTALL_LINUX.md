# Linux Installation

## Architecture-specific DEB packages

- `Eurogas-Nexus-Client-{VERSION}-linux-x64.deb` (amd64)
- `Eurogas-Nexus-Client-{VERSION}-linux-arm64.deb` (arm64)

ARM64 users must never receive the x64 package; the filenames and Debian
package metadata both carry the architecture.

## Install / upgrade / remove

```bash
sha256sum -c SHA256SUMS
sudo apt install ./Eurogas-Nexus-Client-{VERSION}-linux-x64.deb   # or --reinstall for upgrade
dpkg-deb -I Eurogas-Nexus-Client-{VERSION}-linux-x64.deb | grep -E 'Package|Version|Architecture'
sudo apt remove eurogas-nexus-desktop
```

The package contains the desktop shell, application icon, and desktop entry.
It never contains PostgreSQL credentials or the backend runtime.

## Signing baseline

This repository does not publish an APT repository, so APT metadata signing is
not claimed. DEB integrity baseline is SHA-256 plus GitHub OIDC attestation.
When an operator enables GPG signing (`EUROGAS_NEXUS_GPG_SIGNING_ENABLED=true`),
a detached `.asc` signature is produced and verified; that still does not
create an APT repository.

## Validation matrix

- x64 install/upgrade/remove: validated by release CI packaging; graphical
  launch requires an operator desktop environment.
- ARM64: built on `ubuntu-24.04-arm`; package architecture validation is part
  of packaging acceptance.

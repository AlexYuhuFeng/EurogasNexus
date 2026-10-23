# Debian native acceptance — 2026-10-23

This is disposable Debian 13 amd64 acceptance in `eurogas-native-acceptance`,
using Xvfb/Openbox and WebKit software rendering. It does not establish Ubuntu,
ARM64, Windows, macOS, hardware GPU, signing or customer SSO acceptance.

## Observed native behavior

- Installed DEB launches decorated, windowed at 1440×900.
- Development sign-in through the actual packaged WebKit UI authenticates the
  existing synthetic `linux-analyst` identity. Backend `/api/me` returns 200 and
  the protected workspace renders the analyst identity. No client authority is
  inferred from a successful credential response alone.
- Ctrl+Shift+3 opens Strategy Lab; Ctrl+K opens the command palette. Its help
  displays Ctrl labels and Administration is unavailable for this analyst.
- F11 enters 1600×1000 fullscreen and toggles back.
- Native Rust tests: four passed. Rust formatting check passes.

## Fixture isolation

An ignored development-only API process uses existing local synthetic acceptance
identities and database. Generated credentials are stored only in ignored local
files and never in the package or tracked documentation. A local Docker loopback
forward permits the packaged default `127.0.0.1:8000/api` to reach this isolated
API. The release API and production cookie/CORS/security controls are unchanged.
The observed WebKit session successfully reaches the authoritative identity read;
no SameSite cookie change was needed. This does not validate the real desktop
OIDC issuer/browser exchange.

## Evidence

Ignored `.local-runtime/native-acceptance/` contains:

- `native-delivery-final-build.log`, `web-latest-build.log`;
- `delivery-install-reinstall.log`;
- `native-delivery-final-tests.log`, `native-delivery-fmt-final.log`;
- `native-delivery-login.png`, `native-delivery-palette.png`,
  `native-delivery-fullscreen.png`, `delivery-fullscreen-final.txt`;
- `dev-api.log` with native development login and authoritative API requests.

Final Web build and native rebuild passed; final package installed and reinstalled
successfully (`delivery-final-install-reinstall.log`). Package SHA-256:
`bb334b5490a5135260f6e78241782af1825ff99cdf91e18de312ca114015d519`.
The final installed package was launched and captured in `native-final-launched.png`.

Trivy recognized the final Cargo.lock as a Cargo target and reported zero
HIGH/CRITICAL findings using the existing local advisory database on 2026-10-23
(`rust-runtime-scan.json`). This is a lock dependency scan, not a scan of the
Debian GTK/WebKit runtime or a cargo-audit result.

Final package launch restored the authenticated synthetic analyst workspace.
Package removal passed and `/usr/bin/eurogas-nexus-desktop` was absent afterwards
(`delivery-final-uninstall.log`). Native network-view layout still shows crowded
empty-data overlays in the captured fixture; broader native visual parity is not
claimed by login/keyboard acceptance.

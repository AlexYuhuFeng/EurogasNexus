# macOS Installation

## Package

- `Eurogas-Nexus-Client-{VERSION}-macos-universal.dmg`: one disk image for Apple
  silicon and Intel Macs (a universal binary), macOS 13 or later.

## Install / upgrade / remove

```bash
shasum -a 256 -c SHA256SUMS --ignore-missing
open Eurogas-Nexus-Client-{VERSION}-macos-universal.dmg   # drag Eurogas Nexus to Applications
```

To upgrade, replace the app in Applications with the new one. To remove, delete it from
Applications. The app never contains database credentials or the backend runtime.

## Deployment settings

IT places the deployment file (API address, sign-in mode) at
`/Library/Application Support/Eurogas Nexus/Client/deployment.json`, readable by all users,
or pushes it with the firm's MDM. Its format is the same as on Windows and Linux.

## Signing and Gatekeeper

Code signing is the deploying firm's decision, as on Windows
(`docs/operations/RELEASE_SIGNING.md`):

- **Developer ID signed and notarised** (`developer_id_notarized_verified` in the release's
  `signing-state.json`): the release job had the firm's Developer ID certificate and App
  Store Connect key. The app opens normally.
- **Ad-hoc signed** (`unsigned_pending_external`): no Apple keys were configured. The app
  is intact (SHA-256 and GitHub attestation cover it) but Gatekeeper does not know the
  publisher. On first launch, open **System Settings > Privacy & Security** and choose
  **Open Anyway** for Eurogas Nexus, or have IT approve it through MDM. Do not disable
  Gatekeeper.

## Validation matrix

- Every push to `main` builds the universal disk image on `macos-14` (native acceptance),
  checks both architecture slices, the code signature and the image, and records its
  SHA-256. That is build evidence, not an installed-UI acceptance.
- Install, first launch under Gatekeeper, sign-in and upgrade need a recorded check on a
  real Mac for each release.

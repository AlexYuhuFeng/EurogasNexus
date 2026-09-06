# Release Channels

Canonical channels: `preview`, `rc`, `stable`.

| Channel | Purpose | Typical consumer | Tag | Dispatch |
| --- | --- | --- | --- | --- |
| preview | engineering/internal evaluation | maintainers, pilot operators | `vX.Y.Z-preview.N.<shortsha>` | main only |
| rc | candidate for user acceptance/deployment validation | UAT environment, deployment owners | `vX.Y.Z-rc.N` | main or tag |
| stable | commercial GA after all mandatory gates | customers | `vX.Y.Z` | pushed tag only |

The application receives `version`, `channel`, and `commit` as separate build
metadata (`GET /api/runtime/release`, client `releaseMetadata.ts`). No code
parses a channel from a filename.

A preview is never labelled signed/commercial, an RC is never published as
`--latest`, and a stable client never consumes preview update metadata
(no updater ships in CR-12; the future updater endpoint selection must be
channel-gated per `UPDATE_POLICY.md`).

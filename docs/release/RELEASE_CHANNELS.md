# Versions, channels and releases

Eurogas Nexus follows [Semantic Versioning 2.0](https://semver.org/). The version in
`pyproject.toml` is the single source; every other copy (Python, web, desktop,
lockfiles, README) is written from it by `scripts/release/bump_version.py`, and
`scripts/release/check_version_consistency.py` fails CI when a copy diverges.

A version is `X.Y.Z`, or a beta of it. A beta is the one pre-release that is itself a
product version, because customers run it in acceptance. Each ecosystem spells it its own
way, and all spellings come from one parser (`eurogas_nexus.release.versioning`):

| Where | Spelling of the first 1.0.0 beta |
| --- | --- |
| `pyproject.toml` (PEP 440) | `1.0.0b1` |
| Runtime (`APPLICATION_VERSION`, `/api/runtime/release`), npm, Cargo, Tauri | `1.0.0-beta.1` |
| What people read: About box, sign-in, `/api/health`, documents, CHANGELOG | `1.0.0-beta` |
| Linux `.deb` control `Version` (`scripts/release/set_deb_version.py`) | `1.0.0~beta1`, which dpkg sorts before `1.0.0` |
| Windows NSIS installer | `1.0.0-beta.1` (Tauri's NSIS bundle accepts a SemVer pre-release; an MSI would not, and none is built) |

| Part | Raised when |
| --- | --- |
| Major `X` | A deployed installation needs a manual migration step or the public `/api` contract breaks. Stays `0` until the first GA release. |
| Minor `Y` | New capability: a data source, workflow, analysis or route. |
| Patch `Z` | Fixes only, no new capability, no schema change that needs operator action. |

## Channels

| Channel | Purpose | Identifier | Tag | GitHub Release |
| --- | --- | --- | --- | --- |
| preview | Engineering build of any `main` commit for internal testing | `X.Y.Z-preview.N.<sha>` | none | none: the tested bundle is the workflow run's `release-final` artifact |
| beta | Beta for customer acceptance; the version files carry the beta (`X.Y.ZbN`) | `X.Y.Z-beta.N` | `vX.Y.Z-beta.N` (`vX.Y.Z-beta` is accepted as the alias of `-beta.1`) | pre-release |
| rc | Release candidate for user acceptance and deployment rehearsal | `X.Y.Z-rc.N` | `vX.Y.Z-rc.N` | pre-release |
| stable | Commercial release after all gates | `X.Y.Z` | `vX.Y.Z` | release, marked latest |

The application reports `version`, `channel` and `commit` as separate fields
(`GET /api/runtime/release`, client `releaseMetadata.ts`); nothing is derived from a file
name. A preview is never labelled signed or commercial, a beta or an RC is never marked
latest, and a stable client never consumes preview update metadata (`UPDATE_POLICY.md`).

A beta publishes exactly as an RC does (the same `publish-preview-rc` job, the same gates,
x64 and arm64 Linux built). The two never mix: a beta version (`1.0.0b1`) releases only on
the beta channel, and an RC or stable release needs the final version (`1.0.0`), so
`scripts/release/resolve_release_context.py` refuses `v1.0.0-rc.1` or `v1.0.0` while
`pyproject.toml` says `1.0.0b1`, and refuses a beta tag whose number differs from it.

## What a release contains

| Asset | For |
|---|---|
| `Eurogas-Nexus-Client-<version>-windows-x64-setup.exe` | Windows desktop client (connects to a server; installs no backend) |
| `Eurogas-Nexus-Client-<version>-linux-x64.deb`, `-linux-arm64.deb` | Linux desktop client |
| `Eurogas-Nexus-Server-<version>.zip` | Server operators on Linux or Windows: Compose file, HTTPS gateway configuration, configuration template, Windows installer scripts, deployment guides, and `release-identity.json` naming the exact API image digest |
| `eurogas-nexus-web-<version>.tar.gz` | The web client, for hosting behind the gateway |
| `eurogas-nexus-sboms-<version>.tar.gz` | Software bills of materials (Python, npm, Rust, container) |
| `release-manifest.json`, `SHA256SUMS` | What was built from which commit, and checksums for every asset |
| API container image `ghcr.io/<owner>/eurogasnexus-api@sha256:...` | The server runtime, pulled by digest; build provenance is attested |

There is no all-in-one workstation installer: a client and a server are separate roles,
and an evaluation server runs from the same Compose bundle on one machine.

## Cutting a release

1. Day to day, every user-visible change adds a line under `## [Unreleased]` in
   `CHANGELOG.md` (Added, Changed, Fixed, Security). Engineering detail goes in
   `docs/release/notes/`.
2. When the release scope is complete:

   ```bash
   python scripts/release/bump_version.py 0.6.0     # all version surfaces + CHANGELOG
   bash scripts/ci/pre_push_check.sh
   git commit -am "release: 0.6.0" && git push origin main
   git tag -a v0.6.0-rc.1 -m "Eurogas Nexus 0.6.0 RC1" && git push origin v0.6.0-rc.1
   ```

   The tag runs `.github/workflows/release.yml`: build, sign, test, attest, and publish
   a GitHub pre-release with the changelog section as its notes.
3. Fixes found in acceptance land on `main` and ship as `v0.6.0-rc.2`, and so on.

   A beta instead: `bump_version.py 1.0.0b1`, commit, push, then
   `git tag -a v1.0.0-beta.1 -m "Eurogas Nexus 1.0.0 beta" && git push origin v1.0.0-beta.1`
   (or dispatch the workflow with `release_channel: beta`). The next beta is
   `bump_version.py 1.0.0b2` and `v1.0.0-beta.2`; after acceptance, `bump_version.py 1.0.0`
   and the RC/stable steps.
4. When an RC is accepted, tag the **same commit** `v0.6.0`. The stable job runs in the
   `production` environment, refuses an existing tag, and publishes the release as latest.
5. Patches to a released version: `bump_version.py 0.6.1`, then RC and stable as above.

Never move or reuse a published tag; never edit a published release's assets. A broken
release is superseded by the next version, not replaced.

## History

The 0.5.0 line was published only as preview builds tagged `v0.5-preview-<run>-<sha>`,
one GitHub pre-release per build. Those tags are historical and rejected for new releases;
`scripts/release/prune_legacy_prereleases.sh` lists them and, after review, deletes the
pre-releases and tags.

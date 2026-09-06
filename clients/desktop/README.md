# clients/desktop

Eurogas Nexus Windows client shell.

## Blueprint

Read `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md` before adding code here.

Also read:

- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/UI_CONTENT_STANDARDS.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`

## Target

Windows-packaged client that reuses the Web workspace and consumes backend
`/api` contracts. The Web client is the single UI/UX source. Any future
layout, theme, i18n, map, or workflow redesign must be implemented in
`clients/web` first so browser and Windows clients stay coherent.

## Stack

Tauri 2 wrapping `clients/web/dist`.

## Production executable build

Use the Tauri CLI for release executables. The commands below assume the
repository root as the working directory.

```powershell
npm --prefix clients/desktop run build -- --no-bundle
```

The Tauri CLI runs the configured `beforeBuildCommand`, which already builds the
Web assets into `clients/web/dist`. The Tauri CLI then invokes:

```text
cargo build --bins --features tauri/custom-protocol --release
```

This project requires `tauri/custom-protocol` for an embedded production
build. A plain `cargo build --release` without that feature produces a
development-configured binary (`cfg(dev)`), which is the observed incorrect
build mode that remained on the splashscreen instead of showing the main
window.

### If a stale dev-mode artifact exists

Close any running Eurogas Nexus instance first. From the repository root, clean
only the desktop package release artifacts:

```powershell
cargo clean --manifest-path clients/desktop/src-tauri/Cargo.toml -p eurogas-nexus-desktop --release
```

Then run the production executable build again:

```powershell
npm --prefix clients/desktop run build -- --no-bundle
```

### Launch the verified production executable

From the repository root:

```powershell
& .\clients\desktop\src-tauri\target\release\eurogas-nexus-desktop.exe
```

The expected startup sequence is a brief `Eurogas Nexus Loading` splashscreen,
followed by a responsive main window titled `Eurogas Nexus`. The desktop shell
does not start the backend and does not connect to PostgreSQL; it remains an
API-only client.

## Installer packaging

Installer packaging is separate from the no-bundle executable build above and
was not verified during the desktop startup run.

From the repository root:

```powershell
npm --prefix clients/desktop run build -- --bundles nsis
```

## Commands

All commands below assume the repository root as the working directory.

```powershell
npm --prefix clients/desktop install
npm --prefix clients/desktop run check
npm --prefix clients/desktop run build
```

`npm --prefix clients/desktop run build` packages the Windows shell using the
same Web build. It does not start the backend and does not connect to
PostgreSQL.

## Rules

- No direct DB access.
- No vendor API calls from the client.
- No bundled secrets.
- No historical Desktop source copy-paste.
- The old `eurogas nexus.exe` demo is workflow reference only.

## Runtime

The desktop shell loads the Web workspace and relies on Web/API configuration.
It stores no vendor credentials, no DB URL, no market data, and no strategy
parameters.

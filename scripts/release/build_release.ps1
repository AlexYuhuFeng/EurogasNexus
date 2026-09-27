param(
    [switch]$SkipTests,
    [switch]$InstallDependencies,
    [ValidateSet("nsis", "deb", "appimage", "msi")]
    [string]$Bundle = "nsis",
    [string]$ApiImageArchivePath,
    [string]$ApiImage,
    [string]$ApiImageDigest
)

$ErrorActionPreference = "Stop"

$DesktopManifestPath = Join-Path $PSScriptRoot "..\..\clients\desktop\src-tauri\tauri.conf.json"
$DesktopManifest = Get-Content -LiteralPath $DesktopManifestPath -Raw | ConvertFrom-Json
$ResolvedVersion = if ($env:EUROGAS_NEXUS_VERSION) { $env:EUROGAS_NEXUS_VERSION } else { [string]$DesktopManifest.version }
$ReleaseChannel = if ($env:EUROGAS_NEXUS_RELEASE_CHANNEL) { $env:EUROGAS_NEXUS_RELEASE_CHANNEL } else { "preview" }
if ([string]::IsNullOrWhiteSpace($ApiImage)) {
    $ApiImage = "eurogas-nexus-api:${ResolvedVersion}-${ReleaseChannel}"
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$WebDir = Join-Path $RepoRoot "clients\web"
$DesktopDir = Join-Path $RepoRoot "clients\desktop"

Push-Location $RepoRoot
try {
    function Invoke-Step {
        param(
            [string]$Name,
            [scriptblock]$Command
        )

        Write-Host "==> $Name"
        & $Command
    }

    Invoke-Step "Verify release-safe repo state" {
        git -C $RepoRoot diff --check
    }

    if (-not $SkipTests) {
        Invoke-Step "Run Ruff" {
            ruff check $RepoRoot
        }
        Invoke-Step "Run targeted Python release tests" {
            pytest -q tests
        }
        Invoke-Step "Verify API import safety" {
            python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
        }
    }

    if ($InstallDependencies) {
        Invoke-Step "Install Web dependencies" {
            npm --prefix $WebDir ci
        }
        Invoke-Step "Install desktop dependencies" {
            npm --prefix $DesktopDir ci
        }
    }

    Invoke-Step "Build Web client" {
        npm --prefix $WebDir run build
    }

    Invoke-Step "Build desktop bundle ($Bundle)" {
        npm --prefix $DesktopDir run build -- --bundles $Bundle
    }

    $ReleaseContextPath = Join-Path $RepoRoot "dist\releases\release-context.json"

    Invoke-Step "Resolve release context" {
        python (Join-Path $PSScriptRoot "resolve_release_context.py") `
            --channel $ReleaseChannel `
            --allow-off-mainline `
            --output $ReleaseContextPath
    }

    Invoke-Step "Package deployment role bundle" {
        if ([string]::IsNullOrWhiteSpace($ApiImageDigest)) {
            Write-Host "Skipped: the Server operator bundle identity requires -ApiImageDigest sha256:<digest> of the published API image."
        }
        else {
            & (Join-Path $PSScriptRoot "package_deployment_bundle.ps1") `
                -ReleaseContext $ReleaseContextPath `
                -ImageDigest $ApiImageDigest
        }
    }


    Write-Host "==> Release artifacts"
    Get-ChildItem -Path (Join-Path $DesktopDir "src-tauri\target\release\bundle") -Recurse -File |
        Where-Object { $_.Extension -in ".exe", ".msi", ".deb", ".AppImage" } |
        Select-Object FullName, Length
}
finally {
    Pop-Location
}

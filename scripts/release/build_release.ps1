param(
    [switch]$SkipTests,
    [switch]$InstallDependencies,
    [ValidateSet("nsis", "deb", "appimage", "msi")]
    [string]$Bundle = "nsis"
)

$ErrorActionPreference = "Stop"

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
            pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/sdk tests/cli tests/release tests/security
        }
        Invoke-Step "Verify API import safety" {
            python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
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

    Invoke-Step "Package deployment role bundle" {
        & (Join-Path $PSScriptRoot "package_deployment_bundle.ps1")
    }

    Write-Host "==> Release artifacts"
    Get-ChildItem -Path (Join-Path $DesktopDir "src-tauri\target\release\bundle") -Recurse -File |
        Where-Object { $_.Extension -in ".exe", ".msi", ".deb", ".AppImage" } |
        Select-Object FullName, Length
}
finally {
    Pop-Location
}

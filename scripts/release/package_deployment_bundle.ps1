param(
    [string]$OutputDirectory = "dist/releases"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$OutputRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
$StagingRoot = Join-Path ([IO.Path]::GetTempPath()) ("eurogas-nexus-deployment-" + [Guid]::NewGuid().ToString("N"))
$ServerRoot = Join-Path $StagingRoot "Eurogas-Nexus-Server-Windows"
$ServerArchive = Join-Path $OutputRoot "Eurogas-Nexus-Server-Windows.zip"

function Copy-DeploymentPayload([string]$Destination) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($relativePath in @("deploy\runtime", "docs\deployment")) {
        $source = Join-Path $RepoRoot $relativePath
        $target = Join-Path $Destination $relativePath
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    }
    $windowsScripts = Join-Path $Destination "scripts\install\windows"
    New-Item -ItemType Directory -Path $windowsScripts -Force | Out-Null
    foreach ($scriptName in @("Deploy-EurogasNexus.ps1", "Install-EurogasNexusServerRuntime.ps1")) {
        Copy-Item -LiteralPath (Join-Path $RepoRoot "scripts\install\windows\$scriptName") `
            -Destination $windowsScripts -Force
    }
}

try {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    Copy-DeploymentPayload $ServerRoot

    @"
EUROGAS NEXUS SERVER FOR WINDOWS

Advanced operator package for a dedicated Server deployment. Run the documented
PowerShell preflight before installation. This package is not a desktop Client.
See docs\deployment\DEPLOYMENT_ROLES-EN.md or DEPLOYMENT_ROLES-CN.md.
"@ | Set-Content -LiteralPath (Join-Path $ServerRoot "START-HERE.txt") -Encoding UTF8

    foreach ($target in @($ServerArchive)) {
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
    }
    Compress-Archive -Path $ServerRoot -DestinationPath $ServerArchive -CompressionLevel Optimal
    Get-Item -LiteralPath $ServerArchive | Select-Object FullName, Length
}
finally {
    $resolvedStaging = [IO.Path]::GetFullPath($StagingRoot)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedStaging.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path $resolvedStaging -Leaf).StartsWith("eurogas-nexus-deployment-")) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force -ErrorAction SilentlyContinue
    }
}

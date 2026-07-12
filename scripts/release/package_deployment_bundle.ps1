param(
    [string]$OutputDirectory = "dist/releases"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$OutputRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
$StagingRoot = Join-Path ([IO.Path]::GetTempPath()) ("eurogas-nexus-deployment-" + [Guid]::NewGuid().ToString("N"))
$BundleRoot = Join-Path $StagingRoot "eurogas-nexus-deployment"
$Archive = Join-Path $OutputRoot "eurogas-nexus-deployment-windows.zip"

try {
    New-Item -ItemType Directory -Path $BundleRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    foreach ($relativePath in @("deploy\runtime", "scripts\install\windows", "docs\deployment")) {
        $source = Join-Path $RepoRoot $relativePath
        $destination = Join-Path $BundleRoot $relativePath
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
    }
    if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
    Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $Archive -CompressionLevel Optimal
    Get-Item -LiteralPath $Archive | Select-Object FullName, Length
}
finally {
    $resolvedStaging = [IO.Path]::GetFullPath($StagingRoot)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedStaging.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path $resolvedStaging -Leaf).StartsWith("eurogas-nexus-deployment-")) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force -ErrorAction SilentlyContinue
    }
}

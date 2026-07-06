param(
    [switch]$SkipTests,
    [switch]$InstallDependencies,
    [ValidateSet("nsis", "deb", "appimage", "msi")]
    [string]$Bundle = "nsis"
)

$ErrorActionPreference = "Stop"

Write-Warning "build_v1_release.ps1 is deprecated; use build_release.ps1 instead."

$ForwardArgs = @()
if ($SkipTests) {
    $ForwardArgs += "-SkipTests"
}
if ($InstallDependencies) {
    $ForwardArgs += "-InstallDependencies"
}
$ForwardArgs += "-Bundle"
$ForwardArgs += $Bundle

& (Join-Path $PSScriptRoot "build_release.ps1") @ForwardArgs
exit $LASTEXITCODE

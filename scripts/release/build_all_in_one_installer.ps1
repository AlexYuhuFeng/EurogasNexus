[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ClientInstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$ApiImageArchivePath,
    [string]$ApiImage = "eurogas-nexus-api:0.5.0",
    [string]$Version = "0.5.0",
    [string]$OutputDirectory = "dist/releases",
    [string]$MakeNsisPath
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ClientInstaller = (Resolve-Path -LiteralPath $ClientInstallerPath).Path
$ApiImageArchive = (Resolve-Path -LiteralPath $ApiImageArchivePath).Path
$OutputRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
$NsisSource = Join-Path $RepoRoot "installer\windows\all-in-one\EurogasNexusAllInOne.nsi"

if ([string]::IsNullOrWhiteSpace($MakeNsisPath)) {
    $command = Get-Command makensis -ErrorAction SilentlyContinue
    if ($command) { $MakeNsisPath = $command.Source }
}
if ([string]::IsNullOrWhiteSpace($MakeNsisPath)) {
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA "tauri\NSIS\makensis.exe"),
        (Join-Path $env:LOCALAPPDATA "tauri\NSIS\Bin\makensis.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe"),
        (Join-Path $env:ProgramFiles "NSIS\makensis.exe")
    )) {
        if (Test-Path -LiteralPath $candidate) { $MakeNsisPath = $candidate; break }
    }
}
if ([string]::IsNullOrWhiteSpace($MakeNsisPath) -or -not (Test-Path -LiteralPath $MakeNsisPath)) {
    throw "makensis.exe was not found. Install NSIS as a build-time dependency."
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$shortSha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA.Substring(0, 7) } else { "local" }
$OutputFile = Join-Path $OutputRoot "Eurogas-Nexus-AllInOne-$Version-$shortSha-x64-setup.exe"

$arguments = @(
    "/V3",
    "/DVERSION=$Version",
    "/DOUTPUT_FILE=$OutputFile",
    "/DSOURCE_ROOT=$($RepoRoot.Path)",
    "/DCLIENT_INSTALLER=$ClientInstaller",
    "/DAPI_IMAGE_ARCHIVE=$ApiImageArchive",
    "/DAPI_IMAGE=$ApiImage",
    $NsisSource
)
& $MakeNsisPath @arguments
if ($LASTEXITCODE -ne 0) { throw "NSIS compilation failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath $OutputFile)) { throw "NSIS did not produce $OutputFile." }

$hash = Get-FileHash -LiteralPath $OutputFile -Algorithm SHA256
$checksumPath = "$OutputFile.sha256"
"$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($OutputFile))" |
    Set-Content -LiteralPath $checksumPath -Encoding ASCII

Get-Item -LiteralPath $OutputFile, $checksumPath | Select-Object FullName, Length

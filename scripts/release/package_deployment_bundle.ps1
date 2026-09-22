# Thin wrapper: the customer file allowlist, the staging tree and the ZIP are
# owned by package_deployment_bundle.py and its policy manifest. This script
# must not select files itself, so the Windows operator path and the release
# workflow build the same member set.
param(
    [string]$OutputDirectory = "dist/releases"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PackageScript = Join-Path $PSScriptRoot "package_deployment_bundle.py"
$OutputRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
}
else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
}

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) { $PythonCommand = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $PythonCommand) { $PythonCommand = Get-Command py -ErrorAction SilentlyContinue }
if (-not $PythonCommand) {
    throw "Python 3 is required to package the deployment bundle."
}

$Archives = & $PythonCommand.Source $PackageScript $OutputRoot 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Deployment bundle packaging failed."
}

$ArchivePath = $Archives | Select-Object -Last 1
Get-Item -LiteralPath $ArchivePath | Select-Object FullName, Length

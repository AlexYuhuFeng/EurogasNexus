#!/usr/bin/env pwsh
#requires -Version 7.0

# Install the reviewed Windows Python archive without touching machine-global
# state. The URL, archive, checksum and interpreter version are fixed constants;
# the only environment inputs are the GitHub runner's RUNNER_TEMP and GITHUB_PATH.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedPythonVersion = '3.11.12'
$ExpectedSha256 = 'f794b1e74349a989d1b9a466d2207527d4e16a36c92a1277802458293bc4be31'
$ArchiveUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20250529/cpython-3.11.12%2B20250529-x86_64-pc-windows-msvc-install_only_stripped.tar.gz'

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$canonicalVersionPath = Join-Path $repositoryRoot '.python-version'
if (-not (Test-Path -LiteralPath $canonicalVersionPath -PathType Leaf)) {
    throw 'canonical Python version file is missing: .python-version'
}

$canonicalVersion = (Get-Content -LiteralPath $canonicalVersionPath -Raw).Trim()
if ($canonicalVersion -cne $ExpectedPythonVersion) {
    throw 'canonical Python version is not the reviewed 3.11.12 Windows asset'
}

$runnerTemp = [Environment]::GetEnvironmentVariable('RUNNER_TEMP')
$githubPath = [Environment]::GetEnvironmentVariable('GITHUB_PATH')
if ([string]::IsNullOrWhiteSpace($runnerTemp)) {
    throw 'RUNNER_TEMP is required'
}
if ([string]::IsNullOrWhiteSpace($githubPath)) {
    throw 'GITHUB_PATH is required'
}
if (-not (Test-Path -LiteralPath $runnerTemp -PathType Container)) {
    throw 'RUNNER_TEMP is not an existing directory'
}
if (-not (Test-Path -LiteralPath $githubPath -PathType Leaf)) {
    throw 'GITHUB_PATH is not an existing file'
}

$systemRoot = [Environment]::GetEnvironmentVariable('SystemRoot')
if ([string]::IsNullOrWhiteSpace($systemRoot)) {
    throw 'SystemRoot is required'
}
$tarPath = Join-Path $systemRoot 'System32\tar.exe'
if (-not (Test-Path -LiteralPath $tarPath -PathType Leaf)) {
    throw 'built-in tar.exe is missing'
}

$installRoot = Join-Path $runnerTemp "eurogas-nexus-python-$ExpectedPythonVersion"
if (Test-Path -LiteralPath $installRoot) {
    throw "refusing to overwrite an existing Windows Python install: $installRoot"
}
New-Item -ItemType Directory -Path $installRoot -ErrorAction Stop | Out-Null

$archivePath = Join-Path $installRoot 'cpython-windows-install_only_stripped.tar.gz'
try {
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $archivePath -MaximumRedirection 10 -ErrorAction Stop
}
catch {
    throw 'download of the reviewed Windows Python archive failed'
}
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    throw 'downloaded Windows Python archive is missing'
}

$actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -cne $ExpectedSha256) {
    throw 'downloaded Windows Python archive SHA-256 does not match the reviewed checksum'
}

$tarArguments = @('-xzf', $archivePath, '-C', $installRoot)
& $tarPath $tarArguments
if ($LASTEXITCODE -ne 0) {
    throw "tar.exe extraction failed with exit code $LASTEXITCODE"
}

$pythonHome = Join-Path $installRoot 'python'
# The reviewed archive installs the interpreter as python/python.exe.
$pythonExe = Join-Path $pythonHome 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw 'the reviewed Windows Python archive did not contain python\python.exe'
}

$versionOutput = (& $pythonExe --version 2>&1 | Out-String).Trim()
$versionExitCode = $LASTEXITCODE
if ($versionExitCode -ne 0) {
    throw "python --version failed with exit code $versionExitCode"
}
if ($versionOutput -cne "Python $ExpectedPythonVersion") {
    throw 'installed Python version is not exactly 3.11.12'
}

Add-Content -LiteralPath $githubPath -Value $pythonHome -Encoding utf8
Write-Host "Installed canonical Python $ExpectedPythonVersion from the reviewed Windows archive."

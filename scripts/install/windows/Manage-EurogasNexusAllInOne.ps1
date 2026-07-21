[CmdletBinding()]
param(
    [ValidateSet("Start", "Stop", "Restart", "Status", "Open", "Logs", "PurgeData")]
    [string]$Action = "Status",
    [string]$RuntimeRoot = (Join-Path $env:ProgramData "Eurogas Nexus\AllInOne Runtime"),
    [switch]$ConfirmPurge
)

$ErrorActionPreference = "Stop"
$ComposeFile = Join-Path $RuntimeRoot "compose.yaml"
$EnvironmentFile = Join-Path $RuntimeRoot ".env"
$DeploymentFile = Join-Path $RuntimeRoot "deployment.json"
$ApiHealthUrl = "http://127.0.0.1:8765/api/health"

function Invoke-Compose([string[]]$Arguments) {
    if (-not (Test-Path -LiteralPath $ComposeFile) -or -not (Test-Path -LiteralPath $EnvironmentFile)) {
        throw "Eurogas Nexus AllInOne is not configured on this device."
    }
    & docker compose --env-file $EnvironmentFile -f $ComposeFile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose operation failed." }
}

function Find-ClientExecutable {
    $roots = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($root in $roots) {
        $entry = Get-ItemProperty $root -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -eq "Eurogas Nexus" } |
            Select-Object -First 1
        if (-not $entry) { continue }
        $candidates = @($entry.DisplayIcon)
        if (-not [string]::IsNullOrWhiteSpace($entry.InstallLocation)) {
            $candidates += Join-Path $entry.InstallLocation "Eurogas Nexus.exe"
        }
        foreach ($candidate in $candidates) {
            if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
            $rawCandidate = ([string]$candidate).Trim()
            if ($rawCandidate -match '^"([^"]+)"') {
                $path = $Matches[1]
            } else {
                $path = $rawCandidate.Split(",")[0].Trim('"')
            }
            if (Test-Path -LiteralPath $path) { return $path }
        }
    }
    return $null
}

function Get-ConfiguredProfiles {
    $profiles = @()
    $configuration = $null
    if (Test-Path -LiteralPath $DeploymentFile) {
        $configuration = Get-Content -LiteralPath $DeploymentFile -Raw | ConvertFrom-Json
    }
    if (
        $null -eq $configuration -or
        $null -eq $configuration.simulated_prices_enabled -or
        [bool]$configuration.simulated_prices_enabled
    ) {
        $profiles += @("--profile", "simulated-prices")
    }
    if (
        $null -eq $configuration -or
        $null -eq $configuration.public_data_workers_enabled -or
        [bool]$configuration.public_data_workers_enabled
    ) {
        $profiles += @("--profile", "public-ingestion")
    }
    return $profiles
}

function Start-ConfiguredRuntime {
    $arguments = @(Get-ConfiguredProfiles) + @("up", "-d")
    Invoke-Compose $arguments
}

switch ($Action) {
    "Start" {
        Start-ConfiguredRuntime
    }
    "Stop" {
        Invoke-Compose @("down", "--remove-orphans")
    }
    "Restart" {
        Invoke-Compose @("down", "--remove-orphans")
        Start-ConfiguredRuntime
    }
    "Status" {
        Invoke-Compose @("ps")
        try {
            Invoke-RestMethod -Uri $ApiHealthUrl -TimeoutSec 5 | ConvertTo-Json
        }
        catch {
            Write-Warning "The local API is not reachable."
        }
    }
    "Open" {
        try { $null = Invoke-RestMethod -Uri $ApiHealthUrl -TimeoutSec 5 } catch { throw "Start Eurogas Nexus before opening the client." }
        $client = Find-ClientExecutable
        if (-not $client) { throw "The Eurogas Nexus desktop Client executable was not found." }
        Start-Process -FilePath $client
    }
    "Logs" {
        Invoke-Compose @("logs", "--tail", "300")
    }
    "PurgeData" {
        if (-not $ConfirmPurge) {
            $confirmation = Read-Host "Type PURGE to permanently delete the Eurogas Nexus PostgreSQL volume"
            if ($confirmation -cne "PURGE") { Write-Output "Purge cancelled."; exit 0 }
        }
        Invoke-Compose @("down", "--volumes", "--remove-orphans")
        $resolvedRuntime = [IO.Path]::GetFullPath($RuntimeRoot)
        $expectedRoot = [IO.Path]::GetFullPath((Join-Path $env:ProgramData "Eurogas Nexus"))
        if (-not $resolvedRuntime.StartsWith($expectedRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove a runtime path outside the Eurogas Nexus ProgramData root."
        }
        Remove-Item -LiteralPath $resolvedRuntime -Recurse -Force
        Write-Output "Eurogas Nexus runtime containers and PostgreSQL volume were deleted."
    }
}

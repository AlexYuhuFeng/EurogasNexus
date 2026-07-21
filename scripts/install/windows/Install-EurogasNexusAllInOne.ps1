[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Install", "Repair", "Validate", "Uninstall")]
    [string]$Action = "Install",
    [string]$ClientInstallerPath,
    [string]$ApiImageArchivePath,
    [string]$ApiImage = "eurogas-nexus-api:0.5.0",
    [string]$RuntimeRoot = (Join-Path $env:ProgramData "Eurogas Nexus\AllInOne Runtime"),
    [switch]$SkipPublicData,
    [switch]$DisableSimulatedPrices,
    [switch]$UninstallClient,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ServerRuntimeScript = Join-Path $PSScriptRoot "Install-EurogasNexusServerRuntime.ps1"
$ClientConfigRoot = Join-Path $env:ProgramData "Eurogas Nexus\Client"
$ClientConfigFile = Join-Path $ClientConfigRoot "deployment.json"
$LogRoot = Join-Path $env:ProgramData "Eurogas Nexus\Logs"
$LogFile = Join-Path $LogRoot "all-in-one-install.log"
$ApiBaseUrl = "http://127.0.0.1:8765/api"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-DockerCommand {
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidate = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $candidate) {
        $env:Path = "$(Split-Path $candidate -Parent);$env:Path"
        return $candidate
    }
    throw "Docker Desktop is required. Install Docker Desktop with Compose v2, then rerun this installer."
}

function Test-DockerEngine([string]$DockerCommand) {
    & $DockerCommand info *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-DockerReady {
    $docker = Resolve-DockerCommand
    & $docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose v2 is required." }
    if (Test-DockerEngine $docker) { return }

    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $desktop)) {
        throw "Docker is installed but its engine is not running. Start Docker and rerun the installer."
    }
    Start-Process -FilePath $desktop -WindowStyle Minimized
    for ($attempt = 1; $attempt -le 90; $attempt++) {
        Start-Sleep -Seconds 2
        if (Test-DockerEngine $docker) { return }
    }
    throw "Docker Desktop did not become ready within three minutes."
}

function Write-ClientDeployment {
    New-Item -ItemType Directory -Path $ClientConfigRoot -Force | Out-Null
    [ordered]@{
        schema_version = 1
        role = "AllInOne"
        api_base_url = $ApiBaseUrl
        configured_at_utc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $ClientConfigFile -Encoding UTF8
    & icacls $ClientConfigFile /inheritance:r /grant:r "Users:(R)" "SYSTEM:(F)" "Administrators:(F)" *> $null
    if ($LASTEXITCODE -ne 0) { throw "Failed to secure the managed desktop endpoint configuration." }
}

function Install-DesktopClient {
    if ([string]::IsNullOrWhiteSpace($ClientInstallerPath)) {
        throw "The embedded desktop Client installer path is required."
    }
    $installer = Resolve-Path -LiteralPath $ClientInstallerPath -ErrorAction Stop
    & $installer.Path /S
    if ($LASTEXITCODE -ne 0) {
        throw "The embedded desktop Client installer failed with exit code $LASTEXITCODE."
    }
    Write-ClientDeployment
}

function Find-ClientUninstallCommand {
    $roots = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($root in $roots) {
        $entry = Get-ItemProperty $root -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -eq "Eurogas Nexus" } |
            Select-Object -First 1
        if ($entry -and $entry.UninstallString) { return [string]$entry.UninstallString }
    }
    return $null
}

function Uninstall-DesktopClient {
    $command = Find-ClientUninstallCommand
    if (-not $command) { return }
    $executable = $null
    $arguments = "/S"
    if ($command -match '^\s*"([^"]+)"\s*(.*)$') {
        $executable = $Matches[1]
        if (-not [string]::IsNullOrWhiteSpace($Matches[2])) { $arguments = "$($Matches[2]) /S" }
    }
    elseif ($command -match '^\s*(\S+\.exe)\s*(.*)$') {
        $executable = $Matches[1]
        if (-not [string]::IsNullOrWhiteSpace($Matches[2])) { $arguments = "$($Matches[2]) /S" }
    }
    if ($executable -and (Test-Path -LiteralPath $executable)) {
        $process = Start-Process -FilePath $executable -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "The desktop Client uninstaller failed with exit code $($process.ExitCode)."
        }
    }
}

function Invoke-ServerRuntime([string]$RuntimeAction) {
    $parameters = @{
        Action = $RuntimeAction
        InstallRoot = $RuntimeRoot
        ApiPort = 8765
        PostgresPort = 55432
        DeploymentRole = "AllInOne"
        HttpsBindAddress = "127.0.0.1"
        ApiImage = $ApiImage
        ApiImageArchivePath = $ApiImageArchivePath
        LocalHttpOnly = $true
        EnableSimulatedPrices = -not [bool]$DisableSimulatedPrices
        SkipPublicData = [bool]$SkipPublicData
        Json = $true
    }
    $output = & $ServerRuntimeScript @parameters
    if ($LASTEXITCODE -ne 0) { throw "The local Docker runtime operation failed." }
    return $output | ConvertFrom-Json
}

function Test-ApiReady {
    $health = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -TimeoutSec 8
    if ($health.status -ne "ok") { throw "The local API health check did not return status=ok." }
    return $health
}

if (-not (Test-Administrator)) {
    throw "Eurogas Nexus AllInOne installation requires administrator privileges."
}

New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
Start-Transcript -LiteralPath $LogFile -Append | Out-Null
try {
    $result = $null
    if ($Action -in @("Install", "Repair")) {
        Wait-DockerReady
        if ($PSCmdlet.ShouldProcess("Eurogas Nexus AllInOne", $Action)) {
            $runtime = Invoke-ServerRuntime $Action
            Install-DesktopClient
            $health = Test-ApiReady
            $runtimeValidation = Invoke-ServerRuntime "Validate"
            $result = [ordered]@{
                ok = $true
                action = $Action
                role = "AllInOne"
                api_base_url = $ApiBaseUrl
                api_version = $health.version
                database_revision = $runtimeValidation.database_revision
                missing_tables = $runtimeValidation.missing_tables
                simulated_prices_enabled = -not [bool]$DisableSimulatedPrices
                log_file = $LogFile
            }
        }
    }
    elseif ($Action -eq "Validate") {
        Wait-DockerReady
        $runtime = Invoke-ServerRuntime "Validate"
        $health = Test-ApiReady
        $result = [ordered]@{
            ok = $true
            action = "Validate"
            api_base_url = $ApiBaseUrl
            api_version = $health.version
            database_revision = $runtime.database_revision
            missing_tables = $runtime.missing_tables
            client_configuration_present = Test-Path -LiteralPath $ClientConfigFile
            log_file = $LogFile
        }
    }
    elseif ($Action -eq "Uninstall") {
        $runtime = $null
        try {
            Wait-DockerReady
            $runtime = Invoke-ServerRuntime "Uninstall"
        }
        catch {
            Write-Warning "Docker runtime cleanup could not run: $($_.Exception.Message)"
        }
        if ($UninstallClient) { Uninstall-DesktopClient }
        if (Test-Path -LiteralPath $ClientConfigFile) {
            Remove-Item -LiteralPath $ClientConfigFile -Force
        }
        $result = [ordered]@{
            ok = $true
            action = "Uninstall"
            data_preserved = $true
            runtime = $runtime
            log_file = $LogFile
        }
    }
    if ($null -eq $result) { $result = [ordered]@{ ok = $true; action = $Action } }
    if ($Json) { $result | ConvertTo-Json -Depth 8 } else { $result | Format-List }
}
catch {
    Write-Error $_
    exit 20
}
finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}

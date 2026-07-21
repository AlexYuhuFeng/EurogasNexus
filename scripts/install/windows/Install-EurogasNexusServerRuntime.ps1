[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Preflight", "Install", "Repair", "Validate", "Uninstall")]
    [string]$Action = "Preflight",
    [string]$InstallRoot = (Join-Path $env:ProgramData "Eurogas Nexus\Server Runtime"),
    [ValidateRange(1024, 65535)]
    [int]$ApiPort = 8765,
    [ValidateRange(1024, 65535)]
    [int]$PostgresPort = 55432,
    [ValidateSet("Server", "AllInOne")]
    [string]$DeploymentRole = "AllInOne",
    [string]$ServerName,
    [ValidateRange(1024, 65535)]
    [int]$HttpsPort = 8443,
    [string]$HttpsBindAddress = "127.0.0.1",
    [switch]$PrivateNetworkOnly,
    [string]$TlsCertificatePath,
    [string]$TlsPrivateKeyPath,
    [string]$ApiImage = "ghcr.io/alexyuhufeng/eurogasnexus-api:0.5-preview",
    [string]$ApiImageArchivePath,
    [switch]$LocalHttpOnly,
    [switch]$EnableSimulatedPrices,
    [switch]$SkipPublicData,
    [switch]$PurgeData,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$SourceComposeFile = Join-Path $RepoRoot "deploy\runtime\compose.yaml"
$SourceCaddyFile = Join-Path $RepoRoot "deploy\runtime\Caddyfile"
$ComposeFile = Join-Path $InstallRoot "compose.yaml"
$EnvironmentFile = Join-Path $InstallRoot ".env"
$DeploymentFile = Join-Path $InstallRoot "deployment.json"
$LocalApiBaseUrl = "http://127.0.0.1:$ApiPort/api"
$UseLocalHttp = $DeploymentRole -eq "AllInOne" -and [bool]$LocalHttpOnly
$ApiBaseUrl = if ($UseLocalHttp) { $LocalApiBaseUrl } else { "https://${ServerName}:$HttpsPort/api" }

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-CommandAvailable([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-TcpPortAvailable([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -eq $listener
}

function Test-LocalBindAddress([string]$Address) {
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed)) { return $false }
    if ($Address -eq "0.0.0.0") { return $false }
    if ($Address -eq "127.0.0.1") { return $true }
    return $null -ne (Get-NetIPAddress -IPAddress $Address -ErrorAction SilentlyContinue)
}

function New-HexSecret([int]$ByteCount = 32) {
    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Get-PreflightReport {
    $dockerAvailable = Test-CommandAvailable "docker"
    $composeAvailable = $false
    $engineAvailable = $false
    if ($dockerAvailable) {
        & docker compose version *> $null
        $composeAvailable = $LASTEXITCODE -eq 0
        & docker info *> $null
        $engineAvailable = $LASTEXITCODE -eq 0
    }

    $systemDrive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($env:SystemDrive)'"
    $computer = Get-CimInstance Win32_ComputerSystem
    $checks = [ordered]@{
        windows = $env:OS -eq "Windows_NT"
        powershell_supported = $PSVersionTable.PSVersion.Major -ge 5
        administrator = Test-Administrator
        docker_cli = $dockerAvailable
        docker_compose_v2 = $composeAvailable
        docker_engine = $engineAvailable
        memory_gb = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
        memory_supported = $computer.TotalPhysicalMemory -ge 8GB
        free_disk_gb = [math]::Round($systemDrive.FreeSpace / 1GB, 1)
        disk_supported = $systemDrive.FreeSpace -ge 10GB
        api_port_available = Test-TcpPortAvailable $ApiPort
        postgres_port_available = Test-TcpPortAvailable $PostgresPort
        compose_source_present = Test-Path -LiteralPath $SourceComposeFile
        caddy_source_present = $UseLocalHttp -or (Test-Path -LiteralPath $SourceCaddyFile)
        api_image_archive_present = (
            [string]::IsNullOrWhiteSpace($ApiImageArchivePath) -or
            (Test-Path -LiteralPath $ApiImageArchivePath)
        )
    }
    $blocking = @(
        if (-not $checks.windows) { "Windows is required for this bootstrapper." }
        if (-not $checks.powershell_supported) { "PowerShell 5.1 or newer is required." }
        if (-not $checks.docker_cli) { "Docker is not installed. Install an approved Docker/Compose runtime, then rerun Preflight." }
        if ($checks.docker_cli -and -not $checks.docker_compose_v2) { "Docker Compose v2 is required." }
        if ($checks.docker_cli -and -not $checks.docker_engine) { "Docker is installed but its engine is not running." }
        if (-not $checks.memory_supported) { "At least 8 GB of system memory is required." }
        if (-not $checks.disk_supported) { "At least 10 GB of free system-drive space is required." }
        if (-not $checks.compose_source_present) { "The server-runtime Compose manifest is missing from the deployment bundle." }
        if (-not $checks.caddy_source_present) { "The HTTPS gateway configuration is missing from the deployment bundle." }
        if (-not $checks.api_image_archive_present) { "The bundled API image archive is missing." }
    )
    if ($UseLocalHttp) {
        if ($HttpsBindAddress -ne "127.0.0.1") {
            $blocking += "Local AllInOne mode is restricted to the 127.0.0.1 loopback interface."
        }
    }
    elseif ($DeploymentRole -in @("Server", "AllInOne")) {
        if (-not $PrivateNetworkOnly) {
            $blocking += "v0.5-preview Server and AllInOne roles require -PrivateNetworkOnly. Public exposure is not supported before authentication is implemented."
        }
        if (-not (Test-LocalBindAddress $HttpsBindAddress)) {
            $blocking += "HttpsBindAddress must be 127.0.0.1 or a specific IP assigned to this device; 0.0.0.0 is refused."
        }
        if ([string]::IsNullOrWhiteSpace($ServerName)) { $blocking += "ServerName is required for the $DeploymentRole role." }
        if ([string]::IsNullOrWhiteSpace($TlsCertificatePath) -or -not (Test-Path -LiteralPath $TlsCertificatePath)) {
            $blocking += "TlsCertificatePath must point to the PEM server certificate."
        }
        if ([string]::IsNullOrWhiteSpace($TlsPrivateKeyPath) -or -not (Test-Path -LiteralPath $TlsPrivateKeyPath)) {
            $blocking += "TlsPrivateKeyPath must point to the PEM private key."
        }
        if (-not (Test-TcpPortAvailable $HttpsPort) -and -not (Test-Path $DeploymentFile)) {
            $blocking += "HTTPS port $HttpsPort is already in use."
        }
    }
    if ($Action -in @("Install", "Repair")) {
        if (-not $checks.administrator) { $blocking += "Install and Repair require an elevated PowerShell session." }
        if (-not $checks.api_port_available -and -not (Test-Path $DeploymentFile)) { $blocking += "API port $ApiPort is already in use." }
        if (-not $checks.postgres_port_available -and -not (Test-Path $DeploymentFile)) { $blocking += "PostgreSQL port $PostgresPort is already in use." }
    }
    return [ordered]@{
        ok = $blocking.Count -eq 0
        action = $Action
        install_root = $InstallRoot
        api_base_url = $ApiBaseUrl
        checks = $checks
        blocking = $blocking
        docker_install_attempted = $false
        local_http_only = $UseLocalHttp
    }
}

function Protect-EnvironmentFile {
    & icacls $EnvironmentFile /inheritance:r /grant:r "$env:USERNAME`:(R,W)" "SYSTEM:(F)" "Administrators:(F)" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restrict the server runtime environment file ACL."
    }
}

function Initialize-RuntimeFiles {
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Copy-Item -LiteralPath $SourceComposeFile -Destination $ComposeFile -Force
    if (-not $UseLocalHttp) {
        Copy-Item -LiteralPath $SourceCaddyFile -Destination (Join-Path $InstallRoot "Caddyfile") -Force
    }
    if (-not $UseLocalHttp -and $DeploymentRole -in @("Server", "AllInOne")) {
        $tlsRoot = Join-Path $InstallRoot "tls"
        New-Item -ItemType Directory -Path $tlsRoot -Force | Out-Null
        Copy-Item -LiteralPath $TlsCertificatePath -Destination (Join-Path $tlsRoot "server.crt") -Force
        Copy-Item -LiteralPath $TlsPrivateKeyPath -Destination (Join-Path $tlsRoot "server.key") -Force
        & icacls $tlsRoot /inheritance:r /grant:r "SYSTEM:(F)" "Administrators:(F)" *> $null
        if ($LASTEXITCODE -ne 0) { throw "Failed to restrict the TLS material directory ACL." }
    }
    $existing = @{}
    if (Test-Path -LiteralPath $EnvironmentFile) {
        foreach ($line in Get-Content -LiteralPath $EnvironmentFile) {
            if (-not $line.Contains("=")) { continue }
            $parts = $line.Split("=", 2)
            $existing[$parts[0]] = $parts[1]
        }
    }
    $postgresPassword = if ($existing.POSTGRES_PASSWORD) { $existing.POSTGRES_PASSWORD } else { New-HexSecret 32 }
    $secretKey = if ($existing.EUROGAS_NEXUS_SECRET_KEY) { $existing.EUROGAS_NEXUS_SECRET_KEY } else { New-HexSecret 32 }
    $internalToken = if ($existing.EUROGAS_NEXUS_INTERNAL_API_TOKEN) { $existing.EUROGAS_NEXUS_INTERNAL_API_TOKEN } else { New-HexSecret 32 }
    $lines = @(
        "EUROGAS_NEXUS_API_IMAGE=$ApiImage"
        "EUROGAS_NEXUS_VERSION=0.5.0"
        "POSTGRES_DB=eurogas_nexus"
        "POSTGRES_USER=eurogas_runtime"
        "POSTGRES_PASSWORD=$postgresPassword"
        "POSTGRES_PORT=$PostgresPort"
        "API_PORT=$ApiPort"
        "HTTPS_PORT=$HttpsPort"
        "HTTPS_BIND_ADDRESS=$HttpsBindAddress"
        "SERVER_NAME=$ServerName"
        "EUROGAS_NEXUS_SECRET_KEY=$secretKey"
        "EUROGAS_NEXUS_INTERNAL_API_TOKEN=$internalToken"
    )
    [IO.File]::WriteAllLines($EnvironmentFile, $lines, [Text.UTF8Encoding]::new($false))
    Protect-EnvironmentFile
    [ordered]@{
        deployment_mode = if ($DeploymentRole -eq "Server") { "server" } else { "all_in_one" }
        api_base_url = $ApiBaseUrl
        compose_file = $ComposeFile
        simulated_prices_enabled = [bool]$EnableSimulatedPrices
        public_data_workers_enabled = -not [bool]$SkipPublicData
        server_name = $ServerName
        https_port = $HttpsPort
        https_bind_address = $HttpsBindAddress
        network_exposure = if ($UseLocalHttp) { "loopback_only" } else { "private_network_only" }
        local_http_only = $UseLocalHttp
        installed_at_utc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $DeploymentFile -Encoding UTF8
}

function Invoke-Compose([string[]]$Arguments) {
    & docker compose --env-file $EnvironmentFile -f $ComposeFile @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed while running: $($Arguments -join ' ')"
    }
}

function Import-ApiImageArchive {
    if ([string]::IsNullOrWhiteSpace($ApiImageArchivePath)) { return }
    $resolvedArchive = Resolve-Path -LiteralPath $ApiImageArchivePath -ErrorAction Stop
    & docker load --input $resolvedArchive.Path | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Docker could not load the bundled Eurogas Nexus API image."
    }
}

function Wait-ApiReady {
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "$LocalApiBaseUrl/health" -TimeoutSec 3
            if ($health.status -eq "ok") { return $health }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "The server runtime API did not become healthy at $LocalApiBaseUrl."
}

function Wait-PublicApiReady {
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -TimeoutSec 3
            if ($health.status -eq "ok") { return $health }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "The HTTPS API did not become healthy at $ApiBaseUrl. Check certificate trust and DNS."
}

function Install-OrRepairRuntime {
    Initialize-RuntimeFiles
    Import-ApiImageArchive
    if ([string]::IsNullOrWhiteSpace($ApiImageArchivePath)) {
        Invoke-Compose @("pull", "postgres", "migrate", "api")
    }
    else {
        Invoke-Compose @("pull", "postgres")
    }
    Invoke-Compose @("up", "-d", "postgres")
    Invoke-Compose @("run", "--rm", "--no-deps", "migrate")
    Invoke-Compose @("up", "-d", "--no-deps", "api")
    Invoke-Compose @(
        "--profile", "monitoring", "up", "-d",
        "--no-deps", "monitoring-worker"
    )
    if (-not $UseLocalHttp -and $DeploymentRole -in @("Server", "AllInOne")) {
        Invoke-Compose @("--profile", "server", "up", "-d", "--no-deps", "gateway")
    }
    if ($EnableSimulatedPrices) {
        Invoke-Compose @("--profile", "tools", "run", "--rm", "--no-deps", "preview-seed")
        Invoke-Compose @("--profile", "simulated-prices", "up", "-d", "--no-deps", "simulated-prices")
    }
    else {
        Invoke-Compose @("--profile", "simulated-prices", "stop", "simulated-prices")
    }
    $null = Wait-ApiReady
    $health = Wait-PublicApiReady
    $initialIngestionOk = $null
    if (-not $SkipPublicData) {
        try {
            Invoke-Compose @("--profile", "tools", "run", "--rm", "--no-deps", "public-ingestion")
            $initialIngestionOk = $true
        }
        catch {
            $initialIngestionOk = $false
            Write-Warning "Initial public ingestion failed. Runtime installation will continue and the recurring worker will retry."
        }
        Invoke-Compose @(
            "--profile", "public-ingestion", "up", "-d",
            "--no-deps",
            "public-ingestion-worker", "reference-ingestion-worker"
        )
    }
    else {
        Invoke-Compose @(
            "--profile", "public-ingestion", "stop",
            "public-ingestion-worker", "reference-ingestion-worker"
        )
    }
    return [ordered]@{
        ok = $true
        action = $Action
        deployment_mode = if ($DeploymentRole -eq "Server") { "server" } else { "all_in_one" }
        api_base_url = $ApiBaseUrl
        api_status = $health.status
        api_version = $health.version
        simulated_prices_enabled = [bool]$EnableSimulatedPrices
        public_data_ingestion_requested = -not [bool]$SkipPublicData
        public_data_workers_enabled = -not [bool]$SkipPublicData
        monitoring_worker_enabled = $true
        initial_public_ingestion_ok = $initialIngestionOk
        local_http_only = $UseLocalHttp
    }
}

function Validate-Runtime {
    if (-not (Test-Path $EnvironmentFile) -or -not (Test-Path $ComposeFile)) {
        throw "No server runtime deployment was found at $InstallRoot."
    }
    $health = Wait-ApiReady
    $runtime = Invoke-RestMethod -Uri "$LocalApiBaseUrl/runtime/db" -TimeoutSec 5
    return [ordered]@{
        ok = [bool]$runtime.data.connectivity.ok
        action = "Validate"
        api_base_url = $ApiBaseUrl
        api_status = $health.status
        api_version = $health.version
        database_revision = $runtime.data.alembic_revision
        missing_tables = $runtime.data.missing_tables
    }
}

function Uninstall-Runtime {
    if (-not (Test-Path $EnvironmentFile) -or -not (Test-Path $ComposeFile)) {
        return [ordered]@{ ok = $true; action = "Uninstall"; already_absent = $true }
    }
    $arguments = @("down", "--remove-orphans")
    if ($PurgeData) { $arguments += "--volumes" }
    Invoke-Compose $arguments
    if ($PurgeData) {
        $resolvedRoot = [IO.Path]::GetFullPath($InstallRoot)
        $programDataRoot = [IO.Path]::GetFullPath((Join-Path $env:ProgramData "Eurogas Nexus"))
        if (-not $resolvedRoot.StartsWith($programDataRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to purge a runtime path outside the Eurogas Nexus ProgramData root."
        }
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    }
    return [ordered]@{ ok = $true; action = "Uninstall"; data_purged = [bool]$PurgeData }
}

$preflight = Get-PreflightReport
if ($Action -eq "Preflight") {
    $result = $preflight
}
elseif (-not $preflight.ok) {
    $result = $preflight
}
elseif ($Action -in @("Install", "Repair")) {
    if ($PSCmdlet.ShouldProcess($InstallRoot, "$Action Eurogas Nexus server runtime")) {
        $result = Install-OrRepairRuntime
    }
    else {
        $result = [ordered]@{ ok = $true; action = $Action; changed = $false }
    }
}
elseif ($Action -eq "Validate") {
    $result = Validate-Runtime
}
elseif ($Action -eq "Uninstall") {
    if (-not (Test-Administrator)) {
        throw "Uninstall requires an elevated PowerShell session."
    }
    if ($PSCmdlet.ShouldProcess($InstallRoot, "Uninstall Eurogas Nexus server runtime")) {
        $result = Uninstall-Runtime
    }
    else {
        $result = [ordered]@{ ok = $true; action = "Uninstall"; changed = $false }
    }
}

if ($Json) {
    $result | ConvertTo-Json -Depth 6
}
else {
    $result | Format-List
    if (-not $result.ok) {
        $result.blocking | ForEach-Object { Write-Error $_ }
    }
}

if (-not $result.ok) { exit 20 }

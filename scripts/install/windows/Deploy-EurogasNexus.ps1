[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Preflight", "Install", "Repair", "Validate", "Uninstall")]
    [string]$Action = "Preflight",
    [ValidateSet("Server", "Client", "AllInOne")]
    [string]$Role,
    [string]$ServerApiUrl,
    [string]$ClientInstallerPath,
    [string]$ServerName,
    [ValidateRange(1024, 65535)]
    [int]$HttpsPort = 8443,
    [string]$HttpsBindAddress = "127.0.0.1",
    [switch]$PrivateNetworkOnly,
    [string]$TlsCertificatePath,
    [string]$TlsPrivateKeyPath,
    [switch]$AllowUnsignedPreview,
    [switch]$EnableSimulatedPrices,
    [switch]$SkipPublicData,
    [switch]$PurgeServerData,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ServerRuntimeScript = Join-Path $PSScriptRoot "Install-EurogasNexusServerRuntime.ps1"
$ClientConfigRoot = Join-Path $env:ProgramData "Eurogas Nexus\Client"
$ClientConfigFile = Join-Path $ClientConfigRoot "deployment.json"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-ApiUrl([string]$Value, [bool]$RemoteRequired) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "ServerApiUrl is required for the Client role."
    }
    $uri = $null
    if (-not [Uri]::TryCreate($Value.Trim(), [UriKind]::Absolute, [ref]$uri)) {
        throw "ServerApiUrl must be an absolute URL."
    }
    $path = $uri.AbsolutePath.TrimEnd("/")
    if ($path -ne "/api") {
        throw "ServerApiUrl must end with /api."
    }
    $loopback = $uri.Host -in @("127.0.0.1", "localhost")
    if ($RemoteRequired -and $uri.Scheme -ne "https") {
        throw "A remote client requires an HTTPS ServerApiUrl."
    }
    if (-not $RemoteRequired -and $uri.Scheme -ne "https" -and -not ($loopback -and $uri.Scheme -eq "http")) {
        throw "Only loopback API URLs may use HTTP."
    }
    return $uri.AbsoluteUri.TrimEnd("/")
}

function Test-Api([string]$ApiUrl) {
    $health = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 8
    if ($health.status -ne "ok") {
        throw "The backend health endpoint did not report status=ok."
    }
    return $health
}

function Write-ClientDeployment([string]$ApiUrl, [string]$DeploymentRole) {
    New-Item -ItemType Directory -Path $ClientConfigRoot -Force | Out-Null
    [ordered]@{
        schema_version = 1
        role = $DeploymentRole
        api_base_url = $ApiUrl
        configured_at_utc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $ClientConfigFile -Encoding UTF8
    & icacls $ClientConfigFile /inheritance:r /grant:r "Users:(R)" "SYSTEM:(F)" "Administrators:(F)" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restrict the desktop client deployment configuration."
    }
}

function Install-Client([string]$ApiUrl, [string]$DeploymentRole) {
    $resolvedInstaller = Resolve-Path -LiteralPath $ClientInstallerPath -ErrorAction Stop
    if ([IO.Path]::GetExtension($resolvedInstaller.Path) -ne ".exe") {
        throw "ClientInstallerPath must point to the signed Windows NSIS .exe."
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $resolvedInstaller.Path
    if ($signature.Status -ne "Valid" -and -not $AllowUnsignedPreview) {
        throw "The Windows client installer signature is not valid. Use only a signed release installer."
    }
    & $resolvedInstaller.Path /S
    if ($LASTEXITCODE -ne 0) {
        throw "The Windows client installer failed with exit code $LASTEXITCODE."
    }
    Write-ClientDeployment $ApiUrl $DeploymentRole
}

function Get-DeployedApiUrl {
    if ($Role -eq "Client") { return Resolve-ApiUrl $ServerApiUrl $true }
    return "https://${ServerName}:$HttpsPort/api"
}

function Invoke-ServerRuntime([string]$RuntimeAction) {
    $parameters = @{
        Action = $RuntimeAction
        ApiPort = 8765
        PostgresPort = 55432
        DeploymentRole = $Role
        ServerName = $ServerName
        HttpsPort = $HttpsPort
        HttpsBindAddress = $HttpsBindAddress
        PrivateNetworkOnly = [bool]$PrivateNetworkOnly
        TlsCertificatePath = $TlsCertificatePath
        TlsPrivateKeyPath = $TlsPrivateKeyPath
        EnableSimulatedPrices = [bool]$EnableSimulatedPrices
        SkipPublicData = [bool]$SkipPublicData
        PurgeData = [bool]$PurgeServerData
        Json = $true
    }
    $output = & $ServerRuntimeScript @parameters
    if ($LASTEXITCODE -ne 0) {
        throw "The local server runtime operation failed."
    }
    return $output | ConvertFrom-Json
}

function Get-Preflight {
    $blocking = @()
    if (-not $Role) { $blocking += "Role is required: Server, Client, or AllInOne." }
    if ($Action -in @("Install", "Repair", "Uninstall") -and -not (Test-Administrator)) {
        $blocking += "$Action requires an elevated PowerShell session."
    }
    if ($Role -in @("Client", "AllInOne") -and $Action -in @("Install", "Repair")) {
        if ([string]::IsNullOrWhiteSpace($ClientInstallerPath) -or -not (Test-Path -LiteralPath $ClientInstallerPath)) {
            $blocking += "ClientInstallerPath must point to the Windows NSIS installer."
        }
    }
    $apiUrl = $null
    try {
        if ($Role -eq "Client") { $apiUrl = Resolve-ApiUrl $ServerApiUrl $true }
        if ($Role -in @("Server", "AllInOne")) {
            if (-not $PrivateNetworkOnly) {
                throw "v0.5-preview Server and AllInOne deployments require -PrivateNetworkOnly."
            }
            if ([string]::IsNullOrWhiteSpace($ServerName)) { throw "ServerName is required for the $Role role." }
            if ([string]::IsNullOrWhiteSpace($TlsCertificatePath) -or -not (Test-Path -LiteralPath $TlsCertificatePath)) {
                throw "TlsCertificatePath must point to the PEM server certificate."
            }
            if ([string]::IsNullOrWhiteSpace($TlsPrivateKeyPath) -or -not (Test-Path -LiteralPath $TlsPrivateKeyPath)) {
                throw "TlsPrivateKeyPath must point to the PEM private key."
            }
            $apiUrl = "https://${ServerName}:$HttpsPort/api"
        }
    }
    catch {
        $blocking += $_.Exception.Message
    }
    $runtimePreflight = $null
    if ($Role -in @("Server", "AllInOne")) {
        try {
            $runtimePreflight = Invoke-ServerRuntime "Preflight"
            if (-not $runtimePreflight.ok) { $blocking += $runtimePreflight.blocking }
        }
        catch {
            $blocking += $_.Exception.Message
        }
    }
    return [ordered]@{
        ok = $blocking.Count -eq 0
        action = $Action
        role = $Role
        api_base_url = $apiUrl
        client_installer_present = -not [string]::IsNullOrWhiteSpace($ClientInstallerPath) -and (Test-Path -LiteralPath $ClientInstallerPath)
        server_runtime = $runtimePreflight
        blocking = $blocking
        automatic_docker_install = $false
        client_database_credentials = $false
        unsigned_preview_allowed = [bool]$AllowUnsignedPreview
        network_exposure = if ($Role -in @("Server", "AllInOne")) { "private_network_only" } else { "client_only" }
    }
}

$preflight = Get-Preflight
$result = $preflight
if ($Action -ne "Preflight" -and $preflight.ok) {
    if ($Action -in @("Install", "Repair")) {
        if ($PSCmdlet.ShouldProcess("Eurogas Nexus $Role", $Action)) {
            $runtime = $null
            if ($Role -in @("Server", "AllInOne")) {
                $runtime = Invoke-ServerRuntime $Action
            }
            $apiUrl = Get-DeployedApiUrl
            $health = $null
            if ($Role -in @("Client", "AllInOne")) {
                $health = Test-Api $apiUrl
                Install-Client $apiUrl $Role
            }
            $result = [ordered]@{
                ok = $true
                action = $Action
                role = $Role
                api_base_url = $apiUrl
                api_version = if ($health) { $health.version } else { $runtime.api_version }
                server_runtime_changed = $Role -in @("Server", "AllInOne")
                client_changed = $Role -in @("Client", "AllInOne")
            }
        }
        else {
            $result = [ordered]@{ ok = $true; action = $Action; role = $Role; changed = $false }
        }
    }
    elseif ($Action -eq "Validate") {
        $runtime = $null
        if ($Role -in @("Server", "AllInOne")) { $runtime = Invoke-ServerRuntime "Validate" }
        $apiUrl = Get-DeployedApiUrl
        $health = if ($Role -in @("Client", "AllInOne")) { Test-Api $apiUrl } else { $null }
        $result = [ordered]@{
            ok = $true
            action = "Validate"
            role = $Role
            api_base_url = $apiUrl
            api_version = if ($health) { $health.version } else { $runtime.api_version }
            database_revision = if ($runtime) { $runtime.database_revision } else { $null }
        }
    }
    elseif ($Action -eq "Uninstall" -and $PSCmdlet.ShouldProcess("Eurogas Nexus $Role", "Uninstall")) {
        if ($Role -in @("Server", "AllInOne")) { $null = Invoke-ServerRuntime "Uninstall" }
        if ($Role -in @("Client", "AllInOne") -and (Test-Path -LiteralPath $ClientConfigFile)) {
            Remove-Item -LiteralPath $ClientConfigFile -Force
        }
        $result = [ordered]@{ ok = $true; action = "Uninstall"; role = $Role }
    }
}

if ($Json) { $result | ConvertTo-Json -Depth 8 } else { $result | Format-List }
if (-not $result.ok) { exit 20 }

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Preflight", "Install", "Repair", "Validate", "Uninstall")]
    [string]$Action = "Preflight",
    [ValidateSet("Server", "Client")]
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

# Release identity (PILOT-A). A released operator ZIP carries
# release-identity.json at the bundle root: schema version, application and
# release version, channel, full commit SHA and the API image pinned by digest.
# That record is the only accepted identity source for packaged use. An explicit
# source checkout (three levels above this script) keeps working for development
# and is reported as release_identity_source=source-development. Anything else
# fails closed instead of guessing a version from a machine variable.
$BundleRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$ReleaseIdentityPath = Join-Path $BundleRoot "release-identity.json"
$SourceDevelopmentMarker = Join-Path $BundleRoot "pyproject.toml"
$SourceTauriConfigPath = Join-Path $BundleRoot "clients\desktop\src-tauri\tauri.conf.json"

function Assert-IdentityText([object]$Value, [string]$Name, [string]$Pattern) {
    if ($Value -isnot [string] -or $Value -notmatch $Pattern) {
        throw "The release identity is malformed: $Name does not match $Pattern."
    }
    return [string]$Value
}

function Assert-IdentityImageRepository([string]$Repository) {
    # A registry port belongs to the first component (registry.example.com:5000/team/api).
    # A colon on the final path component is a tag, which this identity never carries.
    $finalComponent = $Repository.Split("/")[-1]
    if ([string]::IsNullOrEmpty($finalComponent) -or $finalComponent.Contains(":")) {
        throw "The release identity is malformed: api_image_repository must end with a repository name and must not carry a tag on its final path component."
    }
    return $Repository
}

function Read-BundleReleaseIdentity([string]$Path) {
    $identity = $null
    try {
        $identity = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "The release identity is malformed: $Path is not valid JSON."
    }
    if ($identity.schema_version -ne 1) {
        throw "The release identity is malformed: unsupported schema_version in $Path."
    }
    if ($identity.product_name -ne "Eurogas Nexus") {
        throw "The release identity is malformed: product_name in $Path is not Eurogas Nexus."
    }
    $channel = Assert-IdentityText $identity.channel "channel" "^(preview|rc|stable)$"
    $appVersion = Assert-IdentityText $identity.app_version "app_version" "^\d+\.\d+\.\d+$"
    $releaseVersion = Assert-IdentityText $identity.release_version "release_version" `
        "^v\d+\.\d+\.\d+(-(preview|rc)\.\d+(\.([0-9a-f]{7,40}))?)?$"
    $expectedVersion = if ($channel -eq "stable") { "^v$([regex]::Escape($appVersion))$" }
        elseif ($channel -eq "rc") { "^v$([regex]::Escape($appVersion))-rc\.\d+$" }
        else { "^v$([regex]::Escape($appVersion))-preview\.\d+\.[0-9a-f]{12}$" }
    if ($releaseVersion -notmatch $expectedVersion) {
        throw "The release identity is malformed: release_version does not match channel $channel."
    }
    $commit = Assert-IdentityText $identity.commit_sha "commit_sha" "^[0-9a-f]{40}$"
    if ($channel -eq "preview" -and -not $commit.StartsWith($releaseVersion.Split(".")[-1])) {
        throw "The release identity is malformed: release_version preview suffix does not match commit_sha."
    }
    $repository = Assert-IdentityImageRepository (Assert-IdentityText $identity.api_image_repository "api_image_repository" "^[^@\s]+/[^@\s]+$")
    $digest = Assert-IdentityText $identity.api_image_digest "api_image_digest" "^sha256:[0-9a-f]{64}$"
    $reference = Assert-IdentityText $identity.api_image_reference "api_image_reference" "^[^@\s]+@sha256:[0-9a-f]{64}$"
    if ($reference -ne "$repository@$digest") {
        throw "The release identity is malformed: api_image_reference does not match repository and digest."
    }
    return [ordered]@{
        source = "bundle"
        app_version = $appVersion
        release_version = $releaseVersion
        channel = $channel
        commit_sha = $commit
        api_image = $reference
    }
}

function Resolve-ReleaseIdentity {
    if (Test-Path -LiteralPath $ReleaseIdentityPath) {
        $identity = Read-BundleReleaseIdentity $ReleaseIdentityPath
        if ($env:EUROGAS_NEXUS_VERSION -and $env:EUROGAS_NEXUS_VERSION -ne $identity.app_version) {
            throw "Release identity conflict: EUROGAS_NEXUS_VERSION does not match the bundle release-identity.json."
        }
        if ($env:EUROGAS_NEXUS_RELEASE_CHANNEL -and $env:EUROGAS_NEXUS_RELEASE_CHANNEL -ne $identity.channel) {
            throw "Release identity conflict: EUROGAS_NEXUS_RELEASE_CHANNEL does not match the bundle release-identity.json."
        }
        return $identity
    }
    if ((Test-Path -LiteralPath $SourceDevelopmentMarker) -and (Test-Path -LiteralPath $SourceTauriConfigPath)) {
        $config = Get-Content -LiteralPath $SourceTauriConfigPath -Raw | ConvertFrom-Json
        $version = if ($env:EUROGAS_NEXUS_VERSION) { $env:EUROGAS_NEXUS_VERSION } else { [string]$config.version }
        if ($version -notmatch "^\d+\.\d+\.\d+$") {
            throw "Release identity conflict: source-development version '$version' is not X.Y.Z."
        }
        $channel = if ($env:EUROGAS_NEXUS_RELEASE_CHANNEL) { $env:EUROGAS_NEXUS_RELEASE_CHANNEL } else { "preview" }
        if ($channel -notin @("preview", "rc", "stable")) {
            throw "Release identity conflict: source-development channel '$channel' is not preview, rc or stable."
        }
        return [ordered]@{
            source = "source-development"
            app_version = $version
            release_version = "v${version}-${channel}"
            channel = $channel
            commit_sha = $null
            api_image = $null
        }
    }
    throw "Cannot resolve the release identity: release-identity.json is missing from this deployment bundle and no source checkout was found next to this script. Use the released operator ZIP."
}

$ReleaseIdentity = Resolve-ReleaseIdentity
$PackageVersion = $ReleaseIdentity.app_version
$ReleaseChannel = $ReleaseIdentity.channel
$ReleaseLine = "v${PackageVersion}-${ReleaseChannel}"
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
    if (-not $Role) { $blocking += "Role is required: Server or Client." }
    if ($Action -in @("Install", "Repair", "Uninstall") -and -not (Test-Administrator)) {
        $blocking += "$Action requires an elevated PowerShell session."
    }
    if ($Role -eq "Client" -and $Action -in @("Install", "Repair")) {
        if ([string]::IsNullOrWhiteSpace($ClientInstallerPath) -or -not (Test-Path -LiteralPath $ClientInstallerPath)) {
            $blocking += "ClientInstallerPath must point to the Windows NSIS installer."
        }
    }
    $apiUrl = $null
    try {
        if ($Role -eq "Client") { $apiUrl = Resolve-ApiUrl $ServerApiUrl $true }
        if ($Role -eq "Server") {
            if (-not $PrivateNetworkOnly) {
                throw "${ReleaseLine} Server deployments require -PrivateNetworkOnly."
            }
            if ([string]::IsNullOrWhiteSpace($ServerName)) { throw "ServerName is required for the Server role." }
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
    if ($Role -eq "Server") {
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
        release_version = $ReleaseIdentity.release_version
        release_channel = $ReleaseChannel
        release_identity_source = $ReleaseIdentity.source
        api_image = $ReleaseIdentity.api_image
        client_installer_present = -not [string]::IsNullOrWhiteSpace($ClientInstallerPath) -and (Test-Path -LiteralPath $ClientInstallerPath)
        server_runtime = $runtimePreflight
        blocking = $blocking
        automatic_docker_install = $false
        client_database_credentials = $false
        unsigned_preview_allowed = [bool]$AllowUnsignedPreview
        network_exposure = if ($Role -eq "Server") { "private_network_only" } else { "client_only" }
    }
}

$preflight = Get-Preflight
$result = $preflight
if ($Action -ne "Preflight" -and $preflight.ok) {
    if ($Action -in @("Install", "Repair")) {
        if ($PSCmdlet.ShouldProcess("Eurogas Nexus $Role", $Action)) {
            $runtime = $null
            if ($Role -eq "Server") {
                $runtime = Invoke-ServerRuntime $Action
            }
            $apiUrl = Get-DeployedApiUrl
            $health = $null
            if ($Role -eq "Client") {
                $health = Test-Api $apiUrl
                Install-Client $apiUrl $Role
            }
            $result = [ordered]@{
                ok = $true
                action = $Action
                role = $Role
                api_base_url = $apiUrl
                api_version = if ($health) { $health.version } else { $runtime.api_version }
                server_runtime_changed = $Role -eq "Server"
                client_changed = $Role -eq "Client"
            }
        }
        else {
            $result = [ordered]@{ ok = $true; action = $Action; role = $Role; changed = $false }
        }
    }
    elseif ($Action -eq "Validate") {
        $runtime = $null
        if ($Role -eq "Server") { $runtime = Invoke-ServerRuntime "Validate" }
        $apiUrl = Get-DeployedApiUrl
        $health = if ($Role -eq "Client") { Test-Api $apiUrl } else { $null }
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
        if ($Role -eq "Server") { $null = Invoke-ServerRuntime "Uninstall" }
        if ($Role -eq "Client" -and (Test-Path -LiteralPath $ClientConfigFile)) {
            Remove-Item -LiteralPath $ClientConfigFile -Force
        }
        $result = [ordered]@{ ok = $true; action = "Uninstall"; role = $Role }
    }
}

if ($Json) { $result | ConvertTo-Json -Depth 8 } else { $result | Format-List }
if (-not $result.ok) { exit 20 }

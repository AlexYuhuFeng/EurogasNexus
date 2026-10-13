# Eurogas Nexus - single local acceptance startup (Docker PostgreSQL + API + Web).
#
# One normal local entry point:
#
#   powershell -File scripts/ops/Start-LocalAcceptance.ps1
#
# It performs exactly this sequence, and nothing else:
#   1. fail-closed preflight (Docker reachable, compose file, ignored env file, ignored secret,
#      and the EXTERNAL verified volume already present);
#   2. `docker compose -f <root docker-compose.yml> up -d` for the canonical container
#      eurogas-nexus-postgres on loopback 127.0.0.1:51356, then wait for its HEALTHCHECK;
#   3. verify the running container still mounts the expected volume and secret and publishes
#      exactly the loopback port from the compose contract;
#   4. start the API and the Vite Web dev server only when their ports are free, reusing an
#      existing listener only after proving it belongs to this repository's project;
#   5. wait for `/api/health/ready` and the Web HTTP response.
#
# It deliberately does NOT: pull or install anything, run initdb, seed, migrate, reset, delete a
# volume, or fall back to the retired embedded PostgreSQL. A missing volume, unhealthy container,
# occupied port owned by something else, or missing interpreter is a hard failure to investigate.
#
# Secrets: the ignored `.dnx-out/user-uat.env` is read into this process only and is never printed
# or passed on a command line; the ignored superuser secret is used by Docker Compose, not here.

[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$ComposeFile = '',
    [string]$EnvFile = '',
    [string]$PythonExe = '',
    [string]$NodeExe = '',
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [string]$DbHost = '127.0.0.1',
    [int]$DbPort = 51356,
    [string]$ContainerName = 'eurogas-nexus-postgres',
    [string]$VolumeName = 'eurogas-nexus-postgres-data',
    [string]$SecretFile = '',
    [string]$EvidenceDir = '',
    [switch]$CheckOnly,
    [switch]$Fingerprint
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path }
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
if (-not $ComposeFile) { $ComposeFile = Join-Path $RepoRoot 'docker-compose.yml' }
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot '.dnx-out/user-uat.env' }
if (-not $SecretFile) { $SecretFile = Join-Path $RepoRoot '.dnx-out/docker-postgres-20261008/secrets/postgres_superuser_password.txt' }
if (-not $EvidenceDir) { $EvidenceDir = Join-Path $RepoRoot '.dnx-out/local-acceptance' }

function Write-Step([string]$Message) { Write-Output ('[start-local] ' + $Message) }
function Fail([string]$Message) { throw ('Start-LocalAcceptance: ' + $Message) }

function Require-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { Fail "$Label is missing: $Path" }
}

function Resolve-Executable([string]$Explicit, [string[]]$Candidates, [string]$CommandName, [string]$Label) {
    if ($Explicit) {
        if (-not (Test-Path -LiteralPath $Explicit -PathType Leaf)) { Fail "$Label was given explicitly but does not exist: $Explicit" }
        return (Resolve-Path -LiteralPath $Explicit).Path
    }
    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    $found = Get-Command $CommandName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found -and $found.Source) { return $found.Source }
    Fail "No installed $Label found. This script never installs one; pass -$($Label -replace ' ', '')Exe or install it first."
    return ''
}

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $output = & docker @DockerArgs 2>&1
    $code = $LASTEXITCODE
    return [pscustomobject]@{ ExitCode = $code; Output = @($output | ForEach-Object { $_.ToString() }) }
}

function Get-ListeningProcessId([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) { return [int]$connection.OwningProcess }
    return 0
}

function Get-ProcessCommandLine([int]$ProcessId) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        return [string]$process.CommandLine
    }
    catch {
        return ''
    }
}

function Wait-Healthy([int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $result = Invoke-Docker -DockerArgs @('inspect', '--format', '{{.State.Health.Status}}', $ContainerName)
        $status = ($result.Output -join '').Trim()
        if ($status -eq 'healthy') { return 'healthy' }
        Start-Sleep -Seconds 3
    }
    return 'timeout'
}

function Wait-Port([int]$Port, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ListeningProcessId $Port) -ne 0) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# ---------------------------------------------------------------------------
# 1. Fail-closed preflight
# ---------------------------------------------------------------------------
Write-Step 'preflight'
Require-File $ComposeFile 'root docker-compose.yml'
Require-File $EnvFile 'ignored local env file'
Require-File $SecretFile 'ignored PostgreSQL superuser secret'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'the docker CLI is not on PATH; no fallback database is started.' }
$version = Invoke-Docker -DockerArgs @('version', '--format', '{{.Server.Version}}')
if ($version.ExitCode -ne 0) {
    Fail ("the Docker engine is unreachable from this session. Refusing any fallback. Details: " + (($version.Output -join ' ') -replace '\s+', ' '))
}

$volume = Invoke-Docker -DockerArgs @('volume', 'inspect', $VolumeName)
if ($volume.ExitCode -ne 0) {
    Fail "the verified external volume '$VolumeName' does not exist. Routine startup must not create an empty database; restore/inspect the verified volume first."
}

# ---------------------------------------------------------------------------
# 2. Compose up (canonical container, loopback 51356) + health
# ---------------------------------------------------------------------------
$dshPython = ''
$dshNode = ''
if ($env:DSH_HOME) {
    $dshPython = Join-Path $env:DSH_HOME 'dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe'
    $dshNode = Join-Path $env:DSH_HOME 'dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node.exe'
}
$pythonCandidates = @(
    (Join-Path $RepoRoot '.venv/Scripts/python.exe'),
    $dshPython,
    'C:/Users/qqshu/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe'
)
$nodeCandidates = @(
    $dshNode,
    'C:/Users/qqshu/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node.exe'
)
$python = Resolve-Executable -Explicit $PythonExe -Candidates $pythonCandidates -CommandName 'python' -Label 'Python'
$node = Resolve-Executable -Explicit $NodeExe -Candidates $nodeCandidates -CommandName 'node' -Label 'Node'
$vite = Join-Path $RepoRoot 'clients/web/node_modules/vite/bin/vite.js'
Require-File $vite 'the existing Vite installation (clients/web/node_modules)'

if (-not $CheckOnly) {
    Write-Step "docker compose up -d ($ComposeFile)"
    $up = Invoke-Docker -DockerArgs @('compose', '-f', $ComposeFile, 'up', '-d', '--pull', 'never')
    if ($up.ExitCode -ne 0) { Fail ('docker compose up failed: ' + (($up.Output -join ' ') -replace '\s+', ' ')) }
}

Write-Step 'waiting for container health'
$health = Wait-Healthy -TimeoutSeconds 180
if ($health -ne 'healthy') { Fail "container '$ContainerName' did not become healthy (health=$health)." }

$inspect = Invoke-Docker -DockerArgs @('inspect', '--format', '{{json .}}', $ContainerName)
if ($inspect.ExitCode -ne 0) { Fail "could not inspect container '$ContainerName'." }
$container = ($inspect.Output -join '') | ConvertFrom-Json

if ($container.State.Health.Status -ne 'healthy') { Fail 'container health is not healthy.' }

$portOk = $false
foreach ($key in $container.NetworkSettings.Ports.PSObject.Properties.Name) {
    foreach ($binding in @($container.NetworkSettings.Ports.$key)) {
        if ($binding.HostIp -eq $DbHost -and [string]$binding.HostPort -eq [string]$DbPort) { $portOk = $true }
    }
}
if (-not $portOk) { Fail "container is not published on $DbHost`:$DbPort (expected loopback-only)." }

$mountOk = $false
$secretOk = $false
$resolvedSecret = (Resolve-Path -LiteralPath $SecretFile).Path
foreach ($mount in @($container.Mounts)) {
    if ($mount.Type -eq 'volume' -and $mount.Name -eq $VolumeName -and $mount.Destination -eq '/var/lib/postgresql/data') { $mountOk = $true }
    if ($mount.Type -eq 'bind' -and $mount.Destination -eq '/run/secrets/pg_superuser_password' -and $mount.Source -eq $resolvedSecret -and -not $mount.RW) { $secretOk = $true }
}
if (-not $mountOk) { Fail "container does not mount the external volume '$VolumeName' at /var/lib/postgresql/data." }
if (-not $secretOk) { Fail 'container does not bind the expected read-only superuser secret at /run/secrets/pg_superuser_password.' }
if ($container.Config.Image -notin @('docker.io/library/postgres:16-alpine', 'postgres:16-alpine')) { Fail 'container image does not match the official local PostgreSQL contract.' }

# ---------------------------------------------------------------------------
# 3. API + Web
# ---------------------------------------------------------------------------
$envMap = @{}
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $key, $value = $line -split '=', 2
    $key = $key.Trim()
    if ($key) { $envMap[$key] = $value.Trim().Trim('"') }
}
if (-not $envMap.ContainsKey('RUNTIME_STORE_DATABASE_URL')) { Fail 'the ignored env file carries no RUNTIME_STORE_DATABASE_URL.' }
$configuredDb = [System.Uri]$envMap['RUNTIME_STORE_DATABASE_URL']
if ($configuredDb.Host -ne $DbHost -or $configuredDb.Port -ne $DbPort -or $configuredDb.AbsolutePath -ne '/nexus_browser') { Fail 'the configured API database does not match the canonical Docker endpoint and nexus_browser database.' }
foreach ($key in $envMap.Keys) { Set-Item -Path ('Env:' + $key) -Value $envMap[$key] }
$env:PYTHONPATH = (@('.dnx-deps', 'src', 'packages/python-sdk/src', '.') |
    ForEach-Object { Join-Path $RepoRoot $_ } | Where-Object { Test-Path -LiteralPath $_ }) -join ';'

New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
$apiOut = Join-Path $EvidenceDir 'api.stdout.log'
$apiErr = Join-Path $EvidenceDir 'api.stderr.log'
$webOut = Join-Path $EvidenceDir 'web.stdout.log'
$webErr = Join-Path $EvidenceDir 'web.stderr.log'

$reusedApi = $false
$apiPid = Get-ListeningProcessId $ApiPort
if ($apiPid -ne 0) {
    $commandLine = Get-ProcessCommandLine $apiPid
    if ($commandLine -notmatch 'uvicorn' -or $commandLine -notmatch 'apps\.api\.main:app' -or $commandLine -notmatch [regex]::Escape($RepoRoot)) {
        Fail "port $ApiPort is held by a process that is not this repository's API (pid $apiPid). Not reusing and not killing it."
    }
    $reusedApi = $true
    Write-Step "reusing existing project API listener on port $ApiPort (pid $apiPid)"
}
elseif ($CheckOnly) {
    Fail "no API listener on port $ApiPort and -CheckOnly was requested."
}
else {
    Write-Step "starting API on 127.0.0.1:$ApiPort"
    Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'apps.api.main:app', '--app-dir', ('"' + $RepoRoot + '"'), '--host', '127.0.0.1', '--port', "$ApiPort", '--log-level', 'info') `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr | Out-Null
}

$reusedWeb = $false
$webPid = Get-ListeningProcessId $WebPort
if ($webPid -ne 0) {
    $commandLine = Get-ProcessCommandLine $webPid
    if ($commandLine -notmatch 'vite' -or $commandLine -notmatch [regex]::Escape($RepoRoot)) {
        Fail "port $WebPort is held by a process that is not this repository's Vite server (pid $webPid). Not reusing and not killing it."
    }
    $reusedWeb = $true
    Write-Step "reusing existing project Web listener on port $WebPort (pid $webPid)"
}
elseif ($CheckOnly) {
    Fail "no Web listener on port $WebPort and -CheckOnly was requested."
}
else {
    Write-Step "starting Web (Vite) on 127.0.0.1:$WebPort"
    Start-Process -FilePath $node -ArgumentList @(('"' + $vite + '"'), '--host', '127.0.0.1', '--port', "$WebPort", '--strictPort') `
        -WorkingDirectory (Join-Path $RepoRoot 'clients/web') -WindowStyle Hidden -RedirectStandardOutput $webOut -RedirectStandardError $webErr | Out-Null
}

if (-not (Wait-Port $ApiPort 60)) { Fail "no API listener on port $ApiPort after startup; inspect $apiErr." }
if (-not (Wait-Port $WebPort 60)) { Fail "no Web listener on port $WebPort after startup; inspect $webErr." }

$ready = $null
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    try {
        $ready = Invoke-RestMethod ("http://127.0.0.1:$ApiPort/api/health/ready") -TimeoutSec 10
        if ($ready.status -eq 'ready') { break }
    }
    catch { $ready = $null }
    Start-Sleep -Seconds 2
}
if (-not $ready -or $ready.status -ne 'ready') { Fail 'API readiness did not report ready against the Docker database.' }
$runtimeHeaders = @{ 'X-Eurogas-Api-Key' = $envMap['EUROGAS_NEXUS_PUBLIC_API_TOKEN'] }
$runtimeDb = Invoke-RestMethod ("http://127.0.0.1:$ApiPort/api/runtime/db") -Headers $runtimeHeaders -TimeoutSec 15
if (-not $runtimeDb.data.connectivity.ok -or $runtimeDb.data.missing_tables.Count -ne 0 -or $runtimeDb.data.redacted_database_url -notmatch '127\.0\.0\.1:51356/nexus_browser$') { Fail 'the running API has not confirmed the canonical Docker database identity and required tables.' }

$web = Invoke-WebRequest ("http://127.0.0.1:$WebPort") -UseBasicParsing -TimeoutSec 15
if ($web.StatusCode -ne 200) { Fail "Web returned HTTP $($web.StatusCode)." }

# ---------------------------------------------------------------------------
# 4. Machine-readable evidence (for the idempotent-second-start comparison)
# ---------------------------------------------------------------------------
$dbFingerprint = $null
if ($Fingerprint) {
    $psql = Join-Path $RepoRoot '.dnx-pg/pgserver/pginstall/bin/psql.exe'
    if (Test-Path -LiteralPath $psql) {
        $dsn = $envMap['RUNTIME_STORE_DATABASE_URL']
        $uri = [System.Uri]$dsn
        if ($uri.UserInfo) {
            $parts = $uri.UserInfo -split ':', 2
            $env:PGPASSWORD = if ($parts.Count -gt 1) { [System.Uri]::UnescapeDataString($parts[1]) } else { '' }
            $pgPort = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
            $env:PGHOST = $uri.Host
            $env:PGPORT = [string]$pgPort
            $env:PGUSER = [System.Uri]::UnescapeDataString($parts[0])
            $env:PGDATABASE = [System.Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
            $env:PGCLIENTENCODING = 'UTF8'
            try {
                $dbFingerprint = (& $psql -X -q -A -t -v ON_ERROR_STOP=1 -c "select 'rev=' || coalesce((select version_num from public.alembic_version), '-') || ' tables=' || (select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p'))" 2>&1 | Out-String).Trim()
            }
            finally {
                foreach ($name in @('PGPASSWORD', 'PGHOST', 'PGPORT', 'PGUSER', 'PGDATABASE')) { Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue }
            }
        }
    }
}

$record = [ordered]@{
    started_utc      = (Get-Date).ToUniversalTime().ToString('o')
    check_only       = [bool]$CheckOnly
    container        = $ContainerName
    container_id     = $container.Id
    container_image  = $container.Config.Image
    container_started = $container.State.StartedAt
    restart_count    = $container.RestartCount
    health           = $container.State.Health.Status
    volume           = $VolumeName
    db_endpoint      = "${DbHost}:${DbPort}"
    api_port         = $ApiPort
    web_port         = $WebPort
    reused_api       = $reusedApi
    reused_web       = $reusedWeb
    api_ready        = $ready.status
    web_http         = $web.StatusCode
    db_fingerprint   = $dbFingerprint
}
$evidenceFile = Join-Path $EvidenceDir 'startup-evidence.jsonl'
$previous = $null
if (Test-Path -LiteralPath $evidenceFile) {
    $last = Get-Content -LiteralPath $evidenceFile -Tail 1
    if ($last) { try { $previous = $last | ConvertFrom-Json } catch { $previous = $null } }
}
$previousId = $null
$previousFingerprint = $null
if ($previous) {
    $previousId = $previous.container_id
    $previousFingerprint = $previous.db_fingerprint
}
$record['previous_container_id'] = $previousId
$record['container_id_unchanged'] = [bool]($previousId -and $previousId -eq $container.Id)
$record['previous_db_fingerprint'] = $previousFingerprint
$jsonLine = ($record | ConvertTo-Json -Compress)
Add-Content -LiteralPath $evidenceFile -Value $jsonLine -Encoding utf8NoBOM

Write-Step ("Docker PostgreSQL healthy on $DbHost`:$DbPort (container $($container.Id.Substring(0, 12))); API ready; web HTTP $($web.StatusCode)")
Write-Output "Open http://127.0.0.1:$WebPort. Local acceptance only (Docker-backed, loopback); not production and not a customer-delivery certification."
if ($dbFingerprint) { Write-Output ("db_fingerprint=" + $dbFingerprint) }
if ($record['container_id_unchanged']) { Write-Output "container_id_unchanged=true (idempotent restart over the same container)" }

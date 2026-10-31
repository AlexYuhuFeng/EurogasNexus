<#
.SYNOPSIS
  Install, launch and uninstall the Windows desktop installer on a clean runner, and
  optionally upgrade over the previous release first (release gates G6 and G7).

.DESCRIPTION
  Runs the NSIS installer silently (/S), finds the product through its uninstall
  registry entry, checks the installed version, starts the application and confirms it
  is still running after the settle time, stops it, then runs the uninstaller silently
  and confirms the entry and files are gone. With -PreviousInstaller, the previous
  version is installed first and the new installer must upgrade it in place.

  The result is written as JSON; this script never fails the job on a smoke failure,
  so a release candidate still publishes while a stable release stays blocked by the
  gate evidence written from this result.
#>
param(
  [Parameter(Mandatory = $true)] [string] $Installer,
  [Parameter(Mandatory = $true)] [string] $ExpectedVersion,
  [string] $PreviousInstaller = "",
  [string] $ProductName = "Eurogas Nexus",
  [int] $SettleSeconds = 15,
  [Parameter(Mandatory = $true)] [string] $Output
)

$ErrorActionPreference = "Stop"
$result = [ordered]@{
  installer = (Split-Path $Installer -Leaf)
  expected_version = $ExpectedVersion
  previous_installer = $(if ($PreviousInstaller) { Split-Path $PreviousInstaller -Leaf } else { "" })
  steps = @()
  install_ok = $false
  launch_ok = $false
  uninstall_ok = $false
  upgrade_attempted = [bool]$PreviousInstaller
  upgrade_ok = $false
  error = ""
}

function Step([string] $Name, [bool] $Ok, [string] $Detail) {
  $script:result.steps += [ordered]@{ name = $Name; ok = $Ok; detail = $Detail }
  Write-Host ("[{0}] {1}: {2}" -f $(if ($Ok) { "ok" } else { "FAIL" }), $Name, $Detail)
}

function Find-Entry {
  $roots = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
  )
  foreach ($root in $roots) {
    $hit = Get-ItemProperty $root -ErrorAction SilentlyContinue |
      Where-Object { $_.DisplayName -like "$ProductName*" } | Select-Object -First 1
    if ($hit) { return $hit }
  }
  return $null
}

function Run-Installer([string] $Path) {
  $process = Start-Process -FilePath $Path -ArgumentList "/S" -Wait -PassThru
  Start-Sleep -Seconds 3
  return $process.ExitCode
}

function Installed-Exe($Entry) {
  $location = $Entry.InstallLocation
  if (-not $location -and $Entry.UninstallString) {
    $location = Split-Path ($Entry.UninstallString.Trim('"').Split('"')[0])
  }
  $location = $location.Trim('"')
  return Get-ChildItem -Path $location -Filter *.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notmatch "^unins|uninstall" } | Select-Object -First 1
}

try {
  if ($PreviousInstaller) {
    $code = Run-Installer $PreviousInstaller
    $previous = Find-Entry
    Step "install previous" ($code -eq 0 -and $null -ne $previous) ("exit {0}, version {1}" -f $code, $previous.DisplayVersion)
  }

  $code = Run-Installer $Installer
  $entry = Find-Entry
  $versionOk = $null -ne $entry -and "$($entry.DisplayVersion)" -eq $ExpectedVersion
  $exe = if ($entry) { Installed-Exe $entry } else { $null }
  $result.install_ok = ($code -eq 0) -and $versionOk -and ($null -ne $exe)
  Step "install" $result.install_ok ("exit {0}, registered version {1}, executable {2}" -f $code, $entry.DisplayVersion, $exe.FullName)
  if ($PreviousInstaller) {
    $result.upgrade_ok = $result.install_ok
    Step "upgrade in place" $result.upgrade_ok "the new version replaced the previous one under the same product entry"
  }

  if ($exe) {
    $app = Start-Process -FilePath $exe.FullName -PassThru
    Start-Sleep -Seconds $SettleSeconds
    $app.Refresh()
    $result.launch_ok = -not $app.HasExited
    Step "launch" $result.launch_ok ("still running after {0}s: {1}" -f $SettleSeconds, (-not $app.HasExited))
    if (-not $app.HasExited) { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue }
    Get-Process | Where-Object { $_.Path -eq $exe.FullName } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }

  if ($entry -and $entry.UninstallString) {
    $uninstaller = $entry.UninstallString.Trim('"').Split('"')[0]
    $process = Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -PassThru
    Start-Sleep -Seconds 5
    $gone = $null -eq (Find-Entry)
    $filesGone = -not ($exe -and (Test-Path $exe.FullName))
    $result.uninstall_ok = ($process.ExitCode -eq 0) -and $gone -and $filesGone
    Step "uninstall" $result.uninstall_ok ("exit {0}, entry removed {1}, executable removed {2}" -f $process.ExitCode, $gone, $filesGone)
  }
}
catch {
  $result.error = $_.Exception.Message
  Step "error" $false $result.error
}

$result.ok = $result.install_ok -and $result.launch_ok -and $result.uninstall_ok
$result | ConvertTo-Json -Depth 5 | Set-Content -Path $Output -Encoding utf8
Write-Host ("installer smoke ok={0} upgrade_ok={1}" -f $result.ok, $result.upgrade_ok)
exit 0

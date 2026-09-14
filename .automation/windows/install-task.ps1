param([string]$TaskName='EurogasNexus-Codex-Autonomous')
$ErrorActionPreference='Stop';$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path;$Runner=Join-Path $Repo '.automation\windows\run-supervisor.ps1'
$Action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" -WorkingDirectory $Repo
$Trigger=New-ScheduledTaskTrigger -AtLogOn
$Settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$Principal=New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force|Out-Null
Write-Host "Installed $TaskName"

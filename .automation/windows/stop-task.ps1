param([string]$TaskName='EurogasNexus-Codex-Autonomous')
$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path;New-Item -ItemType File -Path (Join-Path $Repo '.automation\STOP') -Force|Out-Null;Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

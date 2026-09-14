param([string]$TaskName='EurogasNexus-Codex-Autonomous')
$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path;$Stop=Join-Path $Repo '.automation\STOP';if(Test-Path $Stop){Remove-Item $Stop -Force};python (Join-Path $Repo '.automation\scripts\set_control.py') RUNNING;Start-ScheduledTask -TaskName $TaskName

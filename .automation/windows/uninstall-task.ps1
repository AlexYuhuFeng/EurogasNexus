param([string]$TaskName='EurogasNexus-Codex-Autonomous')
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

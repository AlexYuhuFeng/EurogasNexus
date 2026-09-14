$ErrorActionPreference='Stop'
$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Repo
if (-not $env:EUROGAS_ORCHESTRATOR_NODE_ID) { $env:EUROGAS_ORCHESTRATOR_NODE_ID='windows-primary' }
python .automation\scripts\supervisor.py
exit $LASTEXITCODE

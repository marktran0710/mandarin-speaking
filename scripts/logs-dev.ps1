<#
.SYNOPSIS
  Follow only the development frontend and backend Docker logs.

.EXAMPLE
  .\scripts\logs-dev.ps1
#>

[CmdletBinding()]
param(
  [int]$Tail = 100
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'docker-compose.dev.yml'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'Docker CLI was not found. Start Docker Desktop first.'
}

Write-Host 'Following frontend and backend logs. Press Ctrl+C to stop viewing logs; containers keep running.' -ForegroundColor Cyan
& docker compose -f $composeFile logs --follow --tail=$Tail backend frontend
exit $LASTEXITCODE

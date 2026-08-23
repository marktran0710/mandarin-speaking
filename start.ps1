<#
Starts the same independent Docker development stack on every device.

Usage:
  .\start.ps1              Run in the foreground, reusing existing images.
  .\start.ps1 -Detached    Run in the background, reusing existing images.
  .\start.ps1 -Build       Rebuild backend/frontend images before starting.
  .\start.ps1 -NoBuild     Compatibility switch; start without rebuilding (the default).
  .\start.ps1 -PruneDangling  Remove only this project's dangling images before starting.
  .\start.ps1 -ResetData   Delete this device's Docker volumes, then start fresh.

There is deliberately no Lab/Laptop/Standalone mode. Each device owns its
own PostgreSQL database, uploads, model cache, and frontend dependencies.
#>

[CmdletBinding()]
param(
  [switch]$Detached,
  [switch]$Build,
  [switch]$NoBuild,
  [switch]$PruneDangling,
  [switch]$ResetData
)

$ErrorActionPreference = 'Stop'
$composeFile = Join-Path $PSScriptRoot 'docker-compose.dev.yml'
$envFile = Join-Path $PSScriptRoot 'backend/.env'

if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf)) {
  throw "Compose file not found: $composeFile"
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
  throw "Missing backend/.env. Create it first with: Copy-Item backend/.env.example backend/.env"
}
if ($Build -and $NoBuild) {
  throw 'Build and NoBuild cannot be used together. Omit NoBuild or use it alone for compatibility.'
}

$composeArgs = @('-f', $composeFile)

Write-Host 'Validating Docker Compose configuration...' -ForegroundColor Cyan
& docker compose @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

if ($ResetData) {
  Write-Warning 'ResetData will delete this device''s PostgreSQL database, uploads, model cache, and Node dependencies.'
  & docker compose @composeArgs down -v
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

if ($PruneDangling) {
  Write-Host 'Removing dangling images for mandarin-speaking-dev only...' -ForegroundColor Yellow
  & docker image prune --force --filter 'label=com.docker.compose.project=mandarin-speaking-dev'
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

$upArgs = @('up')
if ($Build) {
  $upArgs += '--build'
}
if ($Detached) {
  $upArgs += '-d'
}

Write-Host 'Starting the independent Docker development stack...' -ForegroundColor Cyan
& docker compose @composeArgs @upArgs
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

if ($Detached) {
  Write-Host ''
  Write-Host 'App:     http://127.0.0.1:5177' -ForegroundColor Green
  Write-Host 'Backend: http://127.0.0.1:8001/health/ready' -ForegroundColor Green
  Write-Host 'Logs:    docker compose -f docker-compose.dev.yml logs -f backend frontend' -ForegroundColor Green
}

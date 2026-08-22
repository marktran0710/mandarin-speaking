<#
.SYNOPSIS
  Expose the local Docker demo through Tailscale Funnel.

.DESCRIPTION
  The current Docker development stack already serves the Vite frontend on
  127.0.0.1:5177 and proxies /api to the backend. Tailscale Funnel exposes
  that single origin over HTTPS, so a separate Nginx container is not needed
  for this demo workflow.

.EXAMPLE
  .\scripts\start-demo-funnel.ps1
  .\scripts\start-demo-funnel.ps1 -Stop
#>

[CmdletBinding()]
param(
  [switch]$Stop,
  [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'docker-compose.dev.yml'
$localUrl = 'http://127.0.0.1:5177'

if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
  throw 'Tailscale CLI was not found. Install Tailscale and sign in first.'
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'Docker CLI was not found. Start Docker Desktop first.'
}

$tailscaleSelf = tailscale status --self --json | ConvertFrom-Json
$publicHost = ([string]$tailscaleSelf.Self.DNSName).TrimEnd('.')
if ([string]::IsNullOrWhiteSpace($publicHost)) {
  throw 'Could not determine this device''s Tailscale DNS name.'
}

if ($Stop) {
  Write-Host 'Stopping the public demo Funnel...' -ForegroundColor Yellow
  & tailscale funnel 5177 off
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & tailscale funnel status
  exit 0
}

if (-not $NoStart) {
  $frontend = docker compose -f $composeFile ps --status running --services frontend 2>$null
  if ($frontend -notcontains 'frontend') {
    Write-Host 'Starting the local Docker stack...' -ForegroundColor Cyan
    & (Join-Path $root 'start.ps1') -Detached
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
}

# Vite rejects unknown Host headers by default. Allow only this device's
# current Tailscale hostname, then recreate the frontend with the new env.
$env:VITE_ALLOWED_HOSTS = $publicHost
Write-Host "Allowing Vite host: $publicHost" -ForegroundColor Cyan
& docker compose -f $composeFile up -d --no-build --force-recreate frontend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ready = $false
for ($attempt = 1; $attempt -le 12; $attempt++) {
  try {
    $response = Invoke-WebRequest -Uri $localUrl -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
      $ready = $true
      break
    }
  } catch {
    Start-Sleep -Seconds 2
  }
}

if (-not $ready) {
  throw "The local frontend is not ready at $localUrl. Check: docker compose -f docker-compose.dev.yml logs frontend backend"
}

Write-Host 'Starting Tailscale Funnel on the local frontend...' -ForegroundColor Cyan
& tailscale funnel --bg 5177
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Public demo status:' -ForegroundColor Green
& tailscale funnel status
Write-Host ''
Write-Host 'Stop the demo with: .\scripts\start-demo-funnel.ps1 -Stop' -ForegroundColor Yellow

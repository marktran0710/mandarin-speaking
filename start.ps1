<#
Modes:
  .\start.ps1 -Mode Lab
      Shared Lab PC: PostgreSQL + backend + frontend.

  .\start.ps1 -Mode Laptop
      Laptop client: frontend only, using the Lab backend over Tailscale.

  .\start.ps1 -Mode Standalone
      Full local stack with an independent PostgreSQL volume and uploads.

  .\start.ps1 -Mode Lab -AllowedClientIps 100.104.12.33
      Add a Tailscale client IP when the frontend is opened by its Tailscale IP.

  .\start.ps1 -Mode Lab -Reload
      Auto-restart the backend on code changes while you edit it. Leave
      this off for a live classroom session - see the -Reload param note.
#>

param(
  [ValidateSet('Lab', 'Laptop', 'Standalone')]
  [string]$Mode = 'Lab',

  # Used by Laptop mode. Override when the Lab backend address changes.
  [string]$LabBackendUrl = 'http://100.67.229.122:8000',

  # Origins used when a browser opens the frontend through Tailscale instead
  # of localhost. The default matches the current Laptop Tailscale IP.
  [string[]]$AllowedClientIps = @('100.104.12.33'),

  # Off by default: --reload is for active development (editing code while
  # the server runs), not a live classroom session - it adds file-watching
  # overhead and a hot-reload mid-request can drop a student's in-flight
  # recording. Pass -Reload when you're actually iterating on backend code.
  [switch]$Reload
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Start-PowerShellWindow {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Command
  )

  Start-Process powershell -ArgumentList @('-NoExit', '-Command', $Command)
}

function Get-UsableHostIps {
  @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.InterfaceAlias -notlike '*WSL*' -and
        $_.InterfaceAlias -notlike '*Docker*' -and
        $_.InterfaceAlias -notlike '*Default Switch*'
      } |
      Select-Object -ExpandProperty IPAddress -Unique)
}

function Get-CorsOrigins {
  $origins = @(
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5174',
    'http://127.0.0.1:5174',
    'http://localhost:5175',
    'http://127.0.0.1:5175',
    'http://localhost:5176',
    'http://127.0.0.1:5176'
  )

  $ips = @((Get-UsableHostIps) + $AllowedClientIps) |
    Where-Object { $_ } |
    Select-Object -Unique

  foreach ($ip in $ips) {
    foreach ($port in 5173, 5174, 5175, 5176) {
      $origins += "http://${ip}:$port"
    }
  }

  $origins | Select-Object -Unique
}

Write-Host "Mandarin Speaking - mode: $Mode" -ForegroundColor Cyan

if ($Mode -eq 'Laptop') {
  Write-Host "Checking Lab backend: $LabBackendUrl/health" -ForegroundColor Cyan
  try {
    $health = Invoke-WebRequest -Uri "$LabBackendUrl/health" -UseBasicParsing -TimeoutSec 5
    if ($health.StatusCode -eq 200) {
      Write-Host 'Lab backend is reachable.' -ForegroundColor Green
    }
  }
  catch {
    Write-Warning "Lab backend is not reachable yet. The frontend will still start, but API calls will fail until $LabBackendUrl is accessible."
  }

  Write-Host 'Starting frontend only; local PostgreSQL and backend are intentionally not started.' -ForegroundColor Yellow
  # BACKEND_PROXY_TARGET (not VITE_BACKEND_URL) - the browser must only ever
  # talk to this laptop's own Vite server (see vite.config.ts's proxy). If
  # the browser called the Lab backend directly cross-origin, Chrome silently
  # drops the httpOnly session cookie (backend/auth.py) even with correct
  # CORS/SameSite=Lax headers - confirmed by hand, not a hypothetical.
  $frontendCommand = "`$env:BACKEND_PROXY_TARGET='$LabBackendUrl'; Set-Location '$root'; npm run dev -- --host 0.0.0.0"
  Start-PowerShellWindow -Command $frontendCommand

  Write-Host ''
  Write-Host 'Frontend local: http://localhost:5173 (Vite may choose the next free port)' -ForegroundColor Green
  foreach ($ip in Get-UsableHostIps) {
    Write-Host "Frontend via network: http://${ip}:5173" -ForegroundColor Green
  }
  Write-Host "Backend:  $LabBackendUrl" -ForegroundColor Green
  return
}

# Lab and Standalone modes both run a local database and backend. The only
# difference is intent: Lab is the shared central server; Standalone is an
# isolated development copy with its own Docker volume and uploads.
Write-Host 'Starting PostgreSQL (docker compose)...' -ForegroundColor Cyan
docker compose up -d db

$corsOriginsValue = (Get-CorsOrigins) -join ','
$reloadFlag = if ($Reload) { '--reload ' } else { '' }
$backendCommand = "`$env:CORS_ORIGINS='$corsOriginsValue'; Set-Location '$root\backend'; python -m uvicorn main:app --host 0.0.0.0 ${reloadFlag}--port 8000"

Write-Host 'Starting backend (port 8000)...' -ForegroundColor Cyan
Start-PowerShellWindow -Command $backendCommand

Write-Host 'Starting frontend (port 5173)...' -ForegroundColor Cyan
# No VITE_BACKEND_URL here on purpose - the frontend defaults to its own
# origin and vite.config.ts's dev proxy (default target 127.0.0.1:8000,
# matching the backend started above) forwards /api and /uploads to it.
# Keeping the browser same-origin is what makes the httpOnly session cookie
# (backend/auth.py) actually get attached - see the Laptop-mode note above.
$frontendCommand = "Set-Location '$root'; npm run dev -- --host 0.0.0.0"
Start-PowerShellWindow -Command $frontendCommand

Write-Host ''
Write-Host 'App:     http://localhost:5173' -ForegroundColor Green
Write-Host 'Backend: http://localhost:8000/health' -ForegroundColor Green

if ($Mode -eq 'Lab') {
  Write-Host 'Role:    central Lab server' -ForegroundColor Green
  Write-Host 'Laptop frontend backend URL: http://100.67.229.122:8000' -ForegroundColor Green
}
else {
  Write-Host 'Role:    isolated standalone copy' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Login: use an account from the active database roster; newly created accounts default to password 123456.' -ForegroundColor Yellow

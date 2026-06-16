# Start Mandarin Stories — backend + frontend
# Usage: .\start.ps1

$root = $PSScriptRoot

Write-Host "Starting backend (port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; python -m uvicorn main:app --reload --port 8000"

Write-Host "Starting frontend (port 5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; npm run dev"

Write-Host ""
Write-Host "App:     http://localhost:5173" -ForegroundColor Green
Write-Host "Backend: http://localhost:8000/health" -ForegroundColor Green
Write-Host ""
Write-Host "Logins:  teacher / teacher123    student / student123" -ForegroundColor Yellow

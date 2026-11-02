# ParakhMaan Industrial AI Inspection Platform PowerShell Launcher
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Starting ParakhMaan Industrial AI Visual Inspection Platform (v2.0)" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$backendDir = Join-Path $scriptDir "backend"
$frontendDir = Join-Path $scriptDir "frontend"

Write-Host "[1/2] Starting Backend (FastAPI on http://127.0.0.1:8080)..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$backendDir`" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8080"

Write-Host "[2/2] Starting Frontend (Next.js on http://localhost:3000)..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$frontendDir`" && npx next start -p 3000"

Write-Host "`nBoth services launched!" -ForegroundColor Green
Write-Host " - Frontend Web UI : http://localhost:3000" -ForegroundColor White
Write-Host " - Backend API Docs: http://localhost:8080/docs" -ForegroundColor White
Write-Host " - API Health Check: http://localhost:8080/api/health" -ForegroundColor White
Write-Host "`nDemo Credentials: supervisor@gov.in | Password: parakhmaan123" -ForegroundColor Cyan

Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"

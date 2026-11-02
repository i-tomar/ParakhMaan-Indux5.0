@echo off
title ParakhMaan Industrial AI Inspection Platform Runner
echo =====================================================================
echo Starting ParakhMaan Industrial AI Visual Inspection Platform (v2.0)
echo =====================================================================
echo.

set SCRIPT_DIR=%~dp0

echo [1/2] Launching FastAPI Backend on http://localhost:8080 ...
start "ParakhMaan Backend" cmd /k "cd /d "%SCRIPT_DIR%backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8080"

echo [2/2] Launching Next.js Frontend on http://localhost:3000 ...
start "ParakhMaan Frontend" cmd /k "cd /d "%SCRIPT_DIR%frontend" && npx next start -p 3000"

echo.
echo =====================================================================
echo System is starting up:
echo  - Frontend Web UI : http://localhost:3000
echo  - Backend API Docs: http://localhost:8080/docs
echo  - API Health Check: http://localhost:8080/api/health
echo.
echo Demo Login Credentials:
echo  - Supervisor : supervisor@gov.in  ^| Password: parakhmaan123
echo  - Admin      : admin@gov.in       ^| Password: parakhmaan123
echo  - Inspector  : inspector@gov.in   ^| Password: parakhmaan123
echo =====================================================================
timeout /t 5 >nul
start http://localhost:3000

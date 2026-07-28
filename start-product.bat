@echo off
setlocal

if "%CONTROL_CENTER_PORT%"=="" set CONTROL_CENTER_PORT=8080
set PRODUCT_URL=http://localhost:%CONTROL_CENTER_PORT%

where docker >nul 2>nul
if errorlevel 1 (
  echo ERROR: Docker Desktop is not installed.
  echo Install Docker Desktop and run this file again.
  pause
  exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Docker Compose is unavailable. Update Docker Desktop.
  pause
  exit /b 1
)

echo Starting Channel Analyzer Bot...
docker compose up -d --build
if errorlevel 1 (
  echo ERROR: Docker failed to start the product.
  docker compose logs app
  pause
  exit /b 1
)

echo Waiting for Control Center...
for /L %%I in (1,1,60) do (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%PRODUCT_URL%/health' -TimeoutSec 2 ^| Out-Null; exit 0 } catch { exit 1 }"
  if not errorlevel 1 (
    echo Channel Analyzer Bot is ready: %PRODUCT_URL%
    start "" "%PRODUCT_URL%"
    exit /b 0
  )
  timeout /t 2 /nobreak >nul
)

echo ERROR: The product did not become ready in time.
docker compose ps
docker compose logs app
pause
exit /b 1

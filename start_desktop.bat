@echo off
REM Enterprise Regulation RAG Desktop - DEV Launcher (Windows)
REM Starts the FastAPI side-car and the Vite dev server in separate windows,
REM then opens the OAuth2 API docs and the web UI in the browser.
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"

echo ========================================================
echo    Enterprise Regulation RAG Desktop - DEV Launcher
echo ========================================================

REM [1/6] Python virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Create it first:
    echo   python -m venv venv ^&^& venv\Scripts\activate ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

REM [2/6] Node.js / npm toolchain
where node >nul 2>nul || (echo [ERROR] Node.js not found on PATH. Install it from https://nodejs.org && pause && exit /b 1)
where npm  >nul 2>nul || (echo [ERROR] npm not found on PATH. Reinstall Node.js. && pause && exit /b 1)

REM [3/6] RAG core config (.env)
if not exist ".env" (
    echo [WARNING] .env not found. Creating from .env.example...
    copy .env.example .env >nul
    echo [IMPORTANT] Edit .env: MODE / OPENAI_API_KEY or Ollama settings.
)

REM [4/6] Side-car config (.env.server) with auto-generated secrets
if not exist ".env.server" (
    echo [WARNING] .env.server not found. Generating random JWT_SECRET and admin password...
    for /f "delims=" %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$rng=[System.Security.Cryptography.RandomNumberGenerator]::Create(); $jb=New-Object byte[] 48; $rng.GetBytes($jb); $jwt=[Convert]::ToBase64String($jb); $pb=New-Object byte[] 6; $rng.GetBytes($pb); $pw='Admin-'+([BitConverter]::ToString($pb)).Replace('-','').ToLower(); $c=Get-Content '.env.server.example'; $c=$c -replace '^JWT_SECRET=.*',('JWT_SECRET='+$jwt); $c=$c -replace '^BOOTSTRAP_ADMIN_PASSWORD=.*',('BOOTSTRAP_ADMIN_PASSWORD='+$pw); Set-Content -Path '.env.server' -Value $c -Encoding UTF8; Write-Output $pw"') do set "ADMIN_PW=%%P"
    echo   ============================================================
    echo     Initial admin login - username: admin  password: !ADMIN_PW!
    echo   ============================================================
)

REM Free any stale listeners on our ports so re-runs don't silently fail to bind
REM (e.g. a previous side-car still holding 8756 makes the new one exit immediately).
echo Freeing stale ports 8756 / 5173 (if any)...
powershell -NoProfile -Command "foreach($p in 8756,5173){ Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }" >nul 2>nul

REM [5/6] Install Python deps and start the side-car
echo [5/6] Installing Python dependencies and starting side-car...
call venv\Scripts\activate.bat
pip install -q -r requirements.txt || (echo [ERROR] pip install failed. && pause && exit /b 1)
start "Enterprise Regulation RAG - Sidecar (127.0.0.1:8756)" cmd /k "call venv\Scripts\activate.bat && set PYTHONUTF8=1 && python -m src.server.main"

REM [6/6] Install front-end deps and start the Vite dev server
echo [6/6] Starting front-end...
pushd desktop
if not exist "node_modules" (
    echo Installing front-end dependencies via npm install...
    call npm install || (popd && echo [ERROR] npm install failed. && pause && exit /b 1)
)
start "Enterprise Regulation RAG - Frontend (http://localhost:5173)" cmd /k "npm run dev"
popd

echo.
echo   Side-car  : http://127.0.0.1:8756
echo   OAuth2 API: http://127.0.0.1:8756/docs
echo   Web UI    : http://localhost:5173

REM Wait for the side-car (RAG init) and Vite to come up, then open both pages.
timeout /t 12 /nobreak >nul
start "" "http://127.0.0.1:8756/docs"
start "" "http://localhost:5173"

endlocal

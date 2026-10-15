# One-step local start for Windows. Double-click run-local.bat (or run: powershell -ExecutionPolicy Bypass -File run-local.ps1)
# Needs only Python 3.12+ and Node.js. Uses a local SQLite file unless backend\.env sets DATABASE_URL to PostgreSQL.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

# ---- pick a Python (prefer 3.12/3.13; very new versions may lack package wheels)
Step "Finding Python"
$pyExe = $null; $pyArgs = @()
foreach ($v in @("-3.12", "-3.13", "-3")) {
    try { & py $v --version *> $null; if ($LASTEXITCODE -eq 0) { $pyExe = "py"; $pyArgs = @($v); break } } catch {}
}
if (-not $pyExe) {
    try { & python --version *> $null; if ($LASTEXITCODE -eq 0) { $pyExe = "python" } } catch {}
}
if (-not $pyExe) { Write-Host "Python not found. Install Python 3.12 from https://www.python.org/downloads/ (tick 'Add to PATH')." -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
& $pyExe @pyArgs --version

# ---- backend: venv, packages, settings, database, demo data
Set-Location $backend
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Step "Creating virtual environment"
    & $pyExe @pyArgs -m venv .venv
}
Step "Installing backend packages (first run takes a minute)"
& $venvPython -m pip install --disable-pip-version-check -q -r requirements.txt

if (-not (Test-Path (Join-Path $backend ".env"))) {
    Step "Creating backend\.env (local SQLite database)"
    @(
        "DJANGO_DEBUG=1",
        "DATABASE_URL=sqlite",
        "# To use PostgreSQL instead: DATABASE_URL=postgres://postgres:YOUR_PASSWORD@localhost:5432/cmrs"
    ) | Set-Content -Encoding ASCII (Join-Path $backend ".env")
}

Step "Preparing the database"
& $venvPython manage.py migrate --no-input -v 0
Step "Loading demo data (skipped if already loaded)"
& $venvPython manage.py seed_demo

# ---- free port 8000 if something else is holding it
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "Port 8000 is used by another program (PID $($busy[0].OwningProcess)). Stopping it so CMRS can start." -ForegroundColor Yellow
    Stop-Process -Id $busy[0].OwningProcess -Force -ErrorAction SilentlyContinue
}

Step "Starting backend in a new window (http://localhost:8000)"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$venvPython' manage.py runserver 8000"

# ---- frontend
Set-Location $frontend
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Host "Node.js not found. Install it from https://nodejs.org (LTS)." -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Step "Installing frontend packages (first run takes a minute)"
    npm install --no-audit --no-fund
}
Step "Starting frontend in a new window (http://localhost:5173)"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm run dev"

Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
Write-Host "`nCMRS is starting. Sign in as manager.mum / agent.ravi / finance / admin with password Cmrs@2026" -ForegroundColor Green
Write-Host "Keep the two new windows open; close them to stop the app."
Read-Host "Press Enter to close this window"

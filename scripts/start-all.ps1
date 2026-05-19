# Citizen Health AI — start backend, LiveKit worker, and frontend (Windows)
# Usage:
#   .\scripts\start-all.ps1
#   .\scripts\start-all.ps1 -NoNewWindows    # run all in this console (sequential blocks — not recommended)
#   .\scripts\start-all.ps1 -SkipWorker      # backend + frontend only

param(
    [switch]$NoNewWindows,
    [switch]$SkipWorker,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$WorkerDir = Join-Path $Root "livekit_worker"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$VenvPip = Join-Path $BackendDir ".venv\Scripts\pip.exe"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    WARNING: $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Citizen Health AI — full stack startup" -ForegroundColor White
Write-Host "  Root: $Root" -ForegroundColor DarkGray

# ── Backend venv ─────────────────────────────────────────────────────────────
Write-Step "Checking Python virtualenv (backend/.venv)"
if (-not (Test-Path $VenvPython)) {
    Write-Warn "Creating venv and installing backend requirements..."
    python -m venv (Join-Path $BackendDir ".venv")
    & $VenvPip install -r (Join-Path $BackendDir "requirements.txt")
}
Write-Ok "Python: $VenvPython"

$envFile = Join-Path $BackendDir ".env"
if (-not (Test-Path $envFile)) {
    Write-Warn "backend/.env not found. Copy from README (LIVEKIT_*, SARVAM_API_KEY, DATABASE_URL)."
} else {
    Write-Ok "Found backend/.env"
}

# ── LiveKit worker dependencies (installed into backend venv) ───────────────
if (-not $SkipWorker) {
    Write-Step "Checking LiveKit worker dependencies"
    & $VenvPip install -q -r (Join-Path $WorkerDir "requirements.txt") 2>$null
    Write-Ok "livekit-agents ready in backend venv"
}

# ── Frontend node_modules ───────────────────────────────────────────────────
Write-Step "Checking frontend dependencies"
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Warn "Running npm install in frontend/..."
    Push-Location $FrontendDir
    npm install
    Pop-Location
}
Write-Ok "frontend/node_modules present"

# ── Launch commands ─────────────────────────────────────────────────────────
$backendCmd = @"
Set-Location '$BackendDir'
`$env:PYTHONUNBUFFERED = '1'
Write-Host 'Backend API — http://127.0.0.1:$BackendPort' -ForegroundColor Green
Write-Host 'Health: http://127.0.0.1:$BackendPort/health' -ForegroundColor DarkGray
& '$VenvPython' -m uvicorn app.main:app --reload --host 127.0.0.1 --port $BackendPort
"@

$workerCmd = @"
Set-Location '$WorkerDir'
`$env:PYTHONUNBUFFERED = '1'
Write-Host 'LiveKit worker — agent: citizen-health-ai' -ForegroundColor Magenta
Write-Host 'Requires LIVEKIT_* in backend/.env' -ForegroundColor DarkGray
& '$VenvPython' agent.py dev
"@

$frontendCmd = @"
Set-Location '$FrontendDir'
`$env:PORT = '$FrontendPort'
Write-Host 'Frontend — http://localhost:$FrontendPort' -ForegroundColor Blue
npm run dev -- -p $FrontendPort
"@

function Start-ServiceWindow([string]$title, [string]$command) {
    $args = @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "`$host.ui.RawUI.WindowTitle = '$title'; $command"
    )
    Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Normal | Out-Null
}

Write-Step "Starting services"
if ($NoNewWindows) {
    Write-Warn "-NoNewWindows is not supported for three parallel servers. Opening separate windows instead."
}

Start-ServiceWindow "Citizen Health AI — Backend :$BackendPort" $backendCmd
Start-Sleep -Seconds 2

if (-not $SkipWorker) {
    Start-ServiceWindow "Citizen Health AI — LiveKit Worker" $workerCmd
    Start-Sleep -Seconds 2
}

Start-ServiceWindow "Citizen Health AI — Frontend :$FrontendPort" $frontendCmd

# ── Wait for backend health ─────────────────────────────────────────────────
Write-Step "Waiting for backend health check"
$healthUrl = "http://127.0.0.1:$BackendPort/health"
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $r = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($r.ok) {
            $ready = $true
            Write-Ok "Backend is up (v$($r.version))"
            Write-Host "       db_configured=$($r.db_configured)  sarvam_configured=$($r.sarvam_configured)  livekit_configured=$($r.livekit_configured)" -ForegroundColor DarkGray
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Write-Warn "Backend not ready yet — check the Backend window for errors."
}

Write-Host ""
Write-Host "  All services launched in separate windows." -ForegroundColor Green
Write-Host ""
Write-Host "  Open:  http://localhost:$FrontendPort" -ForegroundColor White
Write-Host "  API:   http://127.0.0.1:$BackendPort/docs" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Stop:  .\scripts\stop-all.ps1" -ForegroundColor DarkGray
Write-Host ""

# Optional: open browser
try {
    Start-Process "http://localhost:$FrontendPort"
} catch {}

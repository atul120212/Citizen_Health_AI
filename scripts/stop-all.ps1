# Stop Citizen Health AI local dev processes (Windows)
# Frees ports 8000 (backend) and 3000 (frontend) and stops related Python/Node children.

param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "SilentlyContinue"

function Stop-PortListeners([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Stopping $($proc.ProcessName) (PID $($proc.Id)) on port $Port"
            Stop-Process -Id $proc.Id -Force
        }
    }
}

Write-Host "`nStopping Citizen Health AI dev servers...`n" -ForegroundColor Cyan
Stop-PortListeners -Port $BackendPort
Stop-PortListeners -Port $FrontendPort

# LiveKit worker has no fixed port; stop uvicorn/python agent.py dev if still running
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match "agent\.py dev|uvicorn app\.main" } |
    ForEach-Object {
        Write-Host "Stopping python PID $($_.ProcessId): $($_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length)))..."
        Stop-Process -Id $_.ProcessId -Force
    }

Write-Host "`nDone.`n" -ForegroundColor Green

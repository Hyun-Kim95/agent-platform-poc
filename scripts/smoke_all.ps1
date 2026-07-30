#Requires -Version 5.1
# Run from repo root with .venv available.
# Unit smokes first (no server), then HTTP smokes (server must be up).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "scripts"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python"
}

function Invoke-Smoke([string]$Rel) {
    Write-Host "=== $Rel ===" -ForegroundColor Cyan
    & $Py (Join-Path $Root $Rel)
    if ($LASTEXITCODE -ne 0) {
        throw "FAIL $Rel exit=$LASTEXITCODE"
    }
}

$unit = @(
    "scripts\smoke_guardrail.py",
    "scripts\smoke_small_fixes.py",
    "scripts\smoke_vector_rag.py",
    "scripts\smoke_sales_pg.py",
    "scripts\smoke_run_store.py",
    "scripts\smoke_tool_router.py"
)
$http = @(
    "scripts\smoke_chat.py",
    "scripts\smoke_s1.py",
    "scripts\smoke_timeout.py",
    "scripts\smoke_loop.py",
    "scripts\smoke_hybrid.py",
    "scripts\smoke_feedback.py",
    "scripts\smoke_obs.py",
    "scripts\smoke_usage.py",
    "scripts\smoke_t2sql_llm.py",
    "scripts\smoke_router_llm.py"
)

foreach ($s in $unit) { Invoke-Smoke $s }

try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3
} catch {
    Write-Host "ERROR: start API first: .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000" -ForegroundColor Red
    exit 1
}

foreach ($s in $http) { Invoke-Smoke $s }

Write-Host "smoke_all: all passed (demo_hitl not included)" -ForegroundColor Green

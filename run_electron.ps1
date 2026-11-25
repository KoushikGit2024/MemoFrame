param(
  [switch]$Build,
  [switch]$Test
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontDir = Join-Path $Root "frontElectron"

$env:MEMOFRAME_BACKEND_DIR = Join-Path $Root "backend"
foreach ($cand in @(
  (Join-Path $Root ".venv\Scripts\python.exe"),
  (Join-Path $Root "venv\Scripts\python.exe"),
  (Join-Path $Root "backend\.venv\Scripts\python.exe")
)) {
  if (Test-Path $cand) {
    $env:MEMOFRAME_PYTHON = $cand
    break
  }
}

Push-Location $FrontDir
try {
  if (-not (Test-Path (Join-Path $FrontDir "node_modules"))) {
    Write-Host "[MemoFrame] Installing Electron frontend dependencies..."
    npm install
  }
  if ($Test) {
    npm run typecheck
  } elseif ($Build) {
    npm start
  } else {
    npm run dev
  }
} finally {
  Pop-Location
}

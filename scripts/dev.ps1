param(
  [switch]$Build,
  [switch]$Test
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DesktopDir = Join-Path $Root "apps\desktop"

$env:MEMOFRAME_ENGINE_DIR = Join-Path $Root "services\engine"
foreach ($cand in @(
  (Join-Path $Root ".venv\Scripts\python.exe"),
  (Join-Path $Root "venv\Scripts\python.exe"),
  (Join-Path $Root "services\engine\.venv\Scripts\python.exe")
)) {
  if (Test-Path $cand) {
    $env:MEMOFRAME_PYTHON = $cand
    break
  }
}

Push-Location $DesktopDir
try {
  if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) {
    Write-Host "[MemoFrame] Installing desktop dependencies..."
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

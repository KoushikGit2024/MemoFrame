$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DesktopDir = Join-Path $Root "apps\desktop"

Write-Host "[1/3] Installing / verifying desktop dependencies..."
Push-Location $DesktopDir
try {
  if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) {
    npm ci
  }
  Write-Host "[2/3] Building TypeScript, Vite bundle, PyInstaller server.exe, and NSIS installer..."
  npm run package
  Write-Host "[3/3] Done! Installer is in apps\desktop\release\"
} finally {
  Pop-Location
}

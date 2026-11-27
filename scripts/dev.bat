@echo off
setlocal
set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

if not exist "%ROOT_DIR%\apps\desktop\node_modules" (
  echo [MemoFrame] Installing desktop frontend dependencies...
  pushd "%ROOT_DIR%\apps\desktop"
  call npm install
  if errorlevel 1 (popd & exit /b 1)
  popd
)

set "MEMOFRAME_ENGINE_DIR=%ROOT_DIR%\services\engine"
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  set "MEMOFRAME_PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"
) else if exist "%ROOT_DIR%\venv\Scripts\python.exe" (
  set "MEMOFRAME_PYTHON=%ROOT_DIR%\venv\Scripts\python.exe"
)

pushd "%ROOT_DIR%\apps\desktop"
if /I "%~1"=="--build" (
  call npm start
) else (
  call npm run dev
)
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

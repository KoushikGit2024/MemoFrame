@echo off
setlocal
cd /d "%~dp0"

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if not exist "%ROOT_DIR%\frontElectron\node_modules" (
  echo [MemoFrame] Installing Electron frontend dependencies...
  pushd "%ROOT_DIR%\frontElectron"
  call npm install
  if errorlevel 1 (
    popd
    exit /b 1
  )
  popd
)

set "MEMOFRAME_BACKEND_DIR=%ROOT_DIR%\backend"
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  set "MEMOFRAME_PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"
) else if exist "%ROOT_DIR%\venv\Scripts\python.exe" (
  set "MEMOFRAME_PYTHON=%ROOT_DIR%\venv\Scripts\python.exe"
)

pushd "%ROOT_DIR%\frontElectron"
if /I "%~1"=="--build" (
  call npm start
) else (
  call npm run dev
)
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

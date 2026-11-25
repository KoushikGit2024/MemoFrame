@echo off
setlocal
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "PY_EXE=python"
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PY_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
if exist "%ROOT_DIR%\venv\Scripts\python.exe" set "PY_EXE=%ROOT_DIR%\venv\Scripts\python.exe"

echo [1/3] Running backend pytest suite...
pushd "%ROOT_DIR%\backend"
"%PY_EXE%" -m pytest
if errorlevel 1 (popd & exit /b 1)
popd

echo [2/3] Running bridge pytest suite...
set "PYTHONPATH=%ROOT_DIR%;%ROOT_DIR%\backend;%PYTHONPATH%"
"%PY_EXE%" -m pytest "%ROOT_DIR%\bridge\tests"
if errorlevel 1 exit /b 1

echo [3/3] Running Electron TSX typecheck...
pushd "%ROOT_DIR%\frontElectron"
if exist node_modules call npm run typecheck
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

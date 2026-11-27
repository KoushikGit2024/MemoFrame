@echo off
setlocal
set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

set "PY_EXE=python"
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PY_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
if exist "%ROOT_DIR%\venv\Scripts\python.exe" set "PY_EXE=%ROOT_DIR%\venv\Scripts\python.exe"

echo [1/2] Running Python engine and RPC pytest suite...
pushd "%ROOT_DIR%\services\engine"
"%PY_EXE%" -m pytest tests
if errorlevel 1 (popd & exit /b 1)
popd

echo [2/2] Running Desktop TypeScript typecheck...
pushd "%ROOT_DIR%\apps\desktop"
if exist node_modules call npm run typecheck
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

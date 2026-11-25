@echo off
setlocal
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "PY_EXE=python"
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PY_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
if exist "%ROOT_DIR%\venv\Scripts\python.exe" set "PY_EXE=%ROOT_DIR%\venv\Scripts\python.exe"

pushd "%ROOT_DIR%\backend"
"%PY_EXE%" cli.py %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

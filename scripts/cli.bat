@echo off
setlocal
set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"
set "PYTHONPATH=%ROOT_DIR%\services\engine;%PYTHONPATH%"
python -m memoframe_engine.cli.cli %*

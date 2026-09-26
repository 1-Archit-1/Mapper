@echo off
REM ========================================
REM Location Shape Mapper - Setup Script
REM ========================================

echo.
echo ========================================
echo   Location Mapper - First Time Setup
echo ========================================
echo.

REM Check if uv is installed
echo [1/2] Checking for uv installation...
uv --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: uv is not installed or not in PATH!
    echo.
    echo Please install uv from: https://docs.astral.sh/uv/getting-started/installation/
    echo.
    echo Quick install command:
    echo   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    pause
    exit /b 1
)

uv --version
echo    uv found!
echo.

REM Install dependencies using uv sync
echo [2/2] Syncing dependencies with uv...
echo    This will create the virtual environment and install packages...
echo    Using lock file for reproducible builds...
echo.

uv sync

if errorlevel 1 (
    echo.
    echo ERROR: uv sync failed
    echo Please check the error messages above
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo You can now run the Location Mapper by double-clicking:
echo   run_location_mapper.bat
echo.
echo To configure settings, copy .env.example to .env and edit it.
echo.
pause

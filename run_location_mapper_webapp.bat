@echo off
REM ========================================
REM Location Mapper - Streamlit Web App
REM ========================================

echo.
echo ========================================
echo   Starting Location Mapper Web App
echo ========================================
echo.

REM Check if uv is available
uv --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found!
    echo Please run setup.bat first to install uv
    echo.
    pause
    exit /b 1
)

REM Start Streamlit app
echo Starting Streamlit web app...
echo.
echo ========================================
echo   App will open in your browser
echo   Press Ctrl+C to stop the server
echo ========================================
echo.

uv run streamlit run location_mapper_webapp.py

pause

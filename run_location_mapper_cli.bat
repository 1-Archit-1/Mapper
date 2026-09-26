@echo off
REM ========================================
REM Location Shape Mapper - Easy Launcher
REM ========================================

echo.
echo ========================================
echo   Location Shape Mapper
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

echo Do you want to run location mapper for Rasters or Shapefiles?
echo 1. Rasters
echo 2. Shapefiles
set /p choice=Enter your choice (1 or 2):
if "%choice%"=="1" (
    set "mapper_script=location_raster_mapping.py"
) else if "%choice%"=="2" (
    set "mapper_script=location_shape_mapping.py"
) else (
    echo Invalid choice. Exiting.
    pause
    exit /b 1
)
REM Run the location mapper
echo.
echo Starting Location Mapper...
echo ----------------------------------------
echo.

uv run python %mapper_script%

REM Capture exit code
set EXIT_CODE=%errorlevel%

echo.
echo ----------------------------------------

if %EXIT_CODE% equ 0 (
    echo.
    echo Program completed successfully!
) else (
    echo.
    echo Program exited with errors. Check the logs folder for details.
)

echo.
echo Press any key to exit...
pause >nul

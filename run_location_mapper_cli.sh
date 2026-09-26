#!/bin/bash
# ========================================
# Location Shape Mapper - Easy Launcher
# ========================================

echo ""
echo "========================================"
echo "  Location Shape Mapper"
echo "========================================"
echo ""

# Check if uv is available
if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv not found!"
    echo "Please run ./setup.sh first to install uv"
    echo ""
    read -n 1 -s -r -p "Press any key to exit..."
    echo ""
    exit 1
fi

echo "Do you want to run location mapper for Rasters or Shapefiles?"
echo "1. Rasters"
echo "2. Shapefiles"
read -p "Enter your choice (1 or 2): " choice

if [ "$choice" == "1" ]; then
    mapper_script="location_raster_mapping_cli.py"
elif [ "$choice" == "2" ]; then
    mapper_script="location_shape_mapping_cli.py"
else
    echo "Invalid choice. Exiting."
    read -n 1 -s -r -p "Press any key to exit..."
    echo ""
    exit 1
fi

# Run the location mapper
echo ""
echo "Starting Location Mapper..."
echo "----------------------------------------"
echo ""

uv run python "$mapper_script"

# Capture exit code
EXIT_CODE=$?

echo ""
echo "----------------------------------------"

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "Program completed successfully!"
else
    echo ""
    echo "Program exited with errors. Check the logs folder for details."
fi

echo ""
read -n 1 -s -r -p "Press any key to exit..."
echo ""

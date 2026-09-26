#!/bin/bash
# ========================================
# Location Shape Mapper - Setup Script
# ========================================

echo ""
echo "========================================"
echo "  Location Mapper - First Time Setup"
echo "========================================"
echo ""

# Check if uv is installed
echo "[1/2] Checking for uv installation..."
if ! command -v uv >/dev/null 2>&1; then
    echo ""
    echo "ERROR: uv is not installed or not in PATH!"
    echo ""
    echo "Please install uv from: https://docs.astral.sh/uv/getting-started/installation/"
    echo ""
    echo "Quick install command:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    read -n 1 -s -r -p "Press any key to exit..."
    echo ""
    exit 1
fi

uv --version
echo "   uv found!"
echo ""

# Install dependencies using uv sync
echo "[2/2] Syncing dependencies with uv..."
echo "   This will create the virtual environment and install packages..."
echo "   Using lock file for reproducible builds..."
echo ""

uv sync

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: uv sync failed"
    echo "Please check the error messages above"
    echo ""
    read -n 1 -s -r -p "Press any key to exit..."
    echo ""
    exit 1
fi

echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "You can now run the Location Mapper by running:"
echo "  ./run_location_mapper_cli.sh"
echo "or"
echo "  ./run_location_mapper_webapp.sh"
echo ""
echo "To configure settings, copy .env.example to .env and edit it."
echo ""
read -n 1 -s -r -p "Press any key to exit..."
echo ""

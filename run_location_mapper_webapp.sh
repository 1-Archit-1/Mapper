#!/bin/bash
# ========================================
# Location Mapper - Streamlit Web App
# ========================================

echo ""
echo "========================================"
echo "  Starting Location Mapper Web App"
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

# Start Streamlit app
echo "Starting Streamlit web app..."
echo ""
echo "========================================"
echo "  App will open in your browser"
echo "  Press Ctrl+C to stop the server"
echo "========================================"
echo ""

uv run streamlit run location_mapper_webapp.py

read -n 1 -s -r -p "Press any key to exit..."
echo ""

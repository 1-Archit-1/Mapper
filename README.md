# Location Mapper Quick Start Guide

## Overview
Location Mapper is a geospatial analysis toolkit that provides **two powerful workflows**:

1. **Raster Value Extraction** - Extract values from raster/GeoTIFF files (flood depths, elevation, etc.) at specific location coordinates
2. **Shapefile Intersection** - Map locations to GIS shapefiles and perform spatial intersections

Both workflows support:
- Reading locations from SQL Server databases or CSV files
- Interactive map visualization
- Multiple output formats (CSV, SQL tables, shapefiles, GeoJSON)

---

## First Time Setup

### 1. Install uv Package Manager
uv is a fast Python package manager
**Install command:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Or visit: https://docs.astral.sh/uv/getting-started/installation/

### 2. Download repo
[GitHub](https://github.com) (click the green "Code" button, then "Download ZIP")
- Unzip the downloaded file
- Open the unzipped folder in File Explorer
- All commands below should be run from inside this directory

### 3. Run Setup (One-Time)
- Double-click `setup.bat`
- Wait for it to complete

---
## Two Ways to Run

### **Option 1: Web App (Recommended)**
Interactive Streamlit web interface with live maps, data previews, and visual configuration.

**To launch:**
- Double-click `run_webapp.bat`
- Your browser will open automatically
- Use the tabs to select your workflow (Raster or Shapefile)

### **Option 2: Command Line Tool**
Fast batch processing for automated workflows and scripting.
- Copy `.env.example` to `.env`
- Edit `.env` with your settings
- Tool will use these settings automatically for repeated runs

**To launch:**
- Double-click `run_location_mapper.bat`
- Choose between Raster (1) or Shapefile (2) mode
- Follow the prompts


---

## Workflow 1: Raster Value Extraction

Extract values from raster files (GeoTIFF, .tif) at specific coordinates.

**Inputs:**
- **Locations:** SQL Server table or CSV with coordinates (latitude/longitude)
- **Raster File:** GeoTIFF file with values to extract

**Outputs:**
- CSV file with extracted raster values
- Optional: Save results to new SQL table
- Interactive map visualization

**How to Use:**
1. Launch the tool (web app or CLI)
2. Select "Raster" workflow
3. Configure your database/CSV source
4. Upload or specify raster file path
5. Map coordinate columns (latitude/longitude)
6. Extract values and visualize results

---

## Workflow 2: Shapefile Intersection

Perform spatial intersection between locations and shapefile boundaries.

**Inputs:**
- **Locations:** SQL Server table or CSV with coordinates
- **Shapefile:** GeoJSON, GeoPackage (.gpkg)

**Outputs:**
- CSV with joined spatial attributes
- Optional: New SQL table with results
- Optional: New shapefile/GeoJSON with combined data
- Interactive map visualization

**How to Use:**
1. Launch the tool (web app or CLI)
2. Select "Shapefile" workflow
3. Configure your database/CSV source
4. Upload shapefile or specify path
5. Map coordinate columns
6. Perform intersection and download results

---

## Common Issues

**"uv not found"**
- Install uv: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Restart your terminal after installation

**"Virtual environment not found" or "uv sync failed"**
- Run `setup.bat` to create the environment
- Make sure you have internet connection for package downloads

**"Failed to connect to database"**
- Verify server name and database name are correct
- Ensure you have Windows Authentication access to SQL Server
- Check VPN connection if accessing remote servers

**"Error loading shapefile"**
- Use .geojson or .gpkg formats
- Check file paths use forward slashes (/) or double backslashes (\\\\)

**"Error loading raster"**
- Ensure raster file is a valid GeoTIFF (.tif)
- Check coordinate reference system (CRS) matches your location data
- Verify file is not corrupted

**Web app won't start**
- Check if port 8501 is already in use
- Try closing other Streamlit apps
- Restart your computer if needed

---

## Output Files

- Results are saved in the `outputs` for cli runs
---

## Advanced Usage

### Manual Commands
If you prefer running commands directly:

```powershell
# Run web app
uv run streamlit run app.py

# Run CLI tool (raster mode)
uv run python location_raster_mapping.py

# Run CLI tool (shapefile mode)
uv run python location_shape_mapping.py
```

### Update Dependencies
```powershell
uv sync  # Update from lock file
uv lock  # Regenerate lock file after adding packages
```

---

## Getting Help

- Check the `logs` folder for detailed error information
- Each run creates a timestamped log file
- Share log files when requesting support
- Review map visualizations to verify coordinate correctness

---

## Requirements

- Windows OS (batch files are Windows-specific)
- uv package manager
- Python 3.11 (installed automatically by uv)
- Internet connection for first-time setup

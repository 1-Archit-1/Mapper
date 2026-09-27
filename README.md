# Mapper Quick Start Guide

## Overview
Mapper is a super-lightweight geospatial analysis toolkit that provides **two powerful workflows**:

1. **Raster Value Extraction** - Extract values from raster/GeoTIFF files (flood depths, elevation, etc.) at specific location coordinates
2. **Shapefile Intersection** - Map locations to GIS shapefiles and perform spatial intersections

Locations are mapped using coordinates, Latitude or Longitude columns are mandatory. 

Both workflows support:
- Reading locations from SQL databases or CSV files
- Currently supports MS SQL server (Windows Authentication and SQL Server Authentication). Support for other DBs coming soon
- Interactive map visualization
- Multiple output formats (CSV, SQL tables, GeoJSON)

---

## Setup Instructions

### Option A: Run with Docker (Recommended)
Docker provides the easiest way to run the application with all dependencies (including MS SQL Server ODBC drivers) pre-configured.
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd Mapper
   ```

### Option B: Local Setup
If you prefer to run the application locally without Docker, you will need the `uv` package manager.

1. **Install uv:**
   - Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Linux/macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   *(Or visit the [official documentation](https://docs.astral.sh/uv/getting-started/installation/))*

2. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd Mapper
   ```

3. **Initialize the environment:**
   - **Windows:** Double-click `setup.bat`
   - **Linux/macOS:** Run `./setup.sh`

---

## Running the Application

### Option 1: Web App (Recommended)
Interactive Streamlit web interface with live maps, data previews, and visual configuration.

**Via Docker:**
```bash
docker-compose up
```
*(The app will be available in your browser at `http://localhost:8501`)*

**Via Local Environment:**
- **Windows:** Double-click `run_location_mapper_webapp.bat`
- **Linux/macOS:** Run `./run_location_mapper_webapp.sh` in the terminal
- Your browser will open automatically.

### Option 2: Command Line Tools
Fast batch processing for automated workflows and scripting.
*Note: Copy `.env.example` to `.env` and configure your settings before running.*

**Via Docker:**
```bash
# Run Raster workflow
docker-compose run --rm cli-raster

# Run Shapefile workflow
docker-compose run --rm cli-shapefile
```

**Via Local Environment:**
- **Windows:** Double-click `run_location_mapper_cli.bat`
- **Linux/macOS:** Run `./run_location_mapper_cli.sh` in the terminal
- Choose between Raster (1) or Shapefile (2) mode and follow the prompts.


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
- Windows: Install uv: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Linux/macOS: Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Restart your terminal after installation

**"Virtual environment not found" or "uv sync failed"**
- Run `setup.bat` (Windows) or `./setup.sh` (Linux/macOS) to create the environment
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
uv run streamlit run location_mapper_webapp.py

# Run CLI tool (raster mode)
uv run python location_raster_mapping_cli.py

# Run CLI tool (shapefile mode)
uv run python location_shape_mapping_cli.py
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

- Windows, Linux, or macOS
- uv package manager
- Python 3.11 (installed automatically by uv)
- Internet connection for first-time setup

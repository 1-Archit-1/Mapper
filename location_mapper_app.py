"""
Location Mapper - Streamlit Web Application

Main entry point for the web UI. Handles page configuration and tab rendering.
All tab-specific logic is in separate modules for better maintainability.
"""
import streamlit as st
from src.location_mapper.shapefile_tab import render_shapefile_tab
from src.location_mapper.raster_tab import render_raster_tab
from src.location_mapper.event_shapefile_tab import render_event_shapefile_tab
from src.db_config import get_saved_servers, remove_server
from src.utils import setup_logging

# Initialize this once per Streamlit session (do not reset on reruns).
if "logging_setup_done" not in st.session_state:
    st.session_state.logging_setup_done = False

if not st.session_state.logging_setup_done:
    log_file = setup_logging()
    st.session_state.logging_setup_done = True

# Page config
st.set_page_config(
    page_title="Location Mapper",
    page_icon="🗺️",
    layout="wide"
)

# Title
st.title("🗺️ Location Mapper")
st.markdown("Map coordinates to shapefiles or extract raster values")

# Tabs for different modes
tab1, tab2= st.tabs(["📍 Shapefile Mapping", "🌐 Raster Value Extraction"])

# Render tabs using modular components
with tab1:
    render_shapefile_tab()

with tab2:
    render_raster_tab()

# Sidebar info
with st.sidebar:
    st.markdown("""
    **Location Mapper** helps you:
    - 📍 Map coordinates to shapefiles (spatial joins)
    - 🌐 Extract raster values at coordinates

    **Shapefile Mode:**
    1. Select your data source
    2. Upload shapefile (.geojson, .gpkg, .zip)
    3. Select coordinate columns
    4. Click Process

    **Raster Mode:**
    1. Select your data source
    2. Upload raster (.tif, .tiff)
    3. Select coordinate columns
    4. Click Extract

    ### Supported formats:
    - CSV/SQLTable for coordinates
    - Shapefiles: .geojson, .gpkg
    - Rasters: .tif, .tiff
    """)

    st.markdown("---")
    st.caption("DB defaults in db_connections.json; user state in db_connections.user.json")

    # Manage saved servers
    with st.expander("⚙️ Manage Saved Servers"):
        saved_servers = get_saved_servers()
        if saved_servers:
            st.write("**Saved Servers:**")
            for server in saved_servers:
                col1, col2 = st.columns([4, 1], vertical_alignment="center")
                with col1:
                    st.text(server)
                with col2:
                    if st.button("🗑️", key=f"delete_{server}", help=f"Delete {server}", type="primary"):
                        remove_server(server)
                        st.success(f"Removed {server}")
                        st.rerun()
        else:
            st.info("No saved servers yet. Use the 💾 button in the tabs to save servers.")

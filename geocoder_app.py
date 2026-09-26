
import streamlit as st
from streamlit_tree_select import tree_select
from pathlib import Path
import shutil
import traceback
from src.db_config import get_saved_servers, remove_server
from src.utils import setup_logging
from src.geocoder.ui.geocoder_shapes_ui_parallel import render_geocoder_shapes_ui
from src.utils.helpers import verify_available_shapes
from src.geocoder.config.shape_config import *

def build_compact_display_dict(nested_data: dict) -> dict:
    """Transforms the nested folder dict into a clean display dictionary."""
    display_dict = {}

    for folder_name, children in nested_data.items():
        if children:
            # Recurse for group folders
            display_dict[f"📁 {folder_name}"] = build_compact_display_dict(children)
        else:
            # Fetch data for leaf folders
            code = get_country_code_for_folder(folder_name)
            mapping = get_admin_mapping_for_code(code)

            key_name = f"{folder_name})"
            if mapping:
                display_dict[key_name] = mapping
            else:
                display_dict[key_name] = "No mapping defined"

    return display_dict



def download_shapefiles_from_network(
    selected_codes: list[str],
    network_root= NETWORK_SHAPES_ROOT,
    local_root= SHAPEFILE_ROOT_DIR
) -> None:
    """
    Downloads the selected country folders from the network drive to the local drive,
    maintaining the exact hierarchy and displaying a progress bar.
    """
    files_to_copy = []

    # 1. Map out every file we need to copy
    for code in selected_codes:

        rel_path = get_path_for_country_code(code)
        if not rel_path:
            continue
        src_dir = network_root / rel_path

        if src_dir.exists():
            # Recursively find all files (ignoring directories themselves)
            for src_file in src_dir.rglob('*'):
                if src_file.is_file():
                    # Map the exact destination path
                    file_rel_path = src_file.relative_to(network_root)
                    dest_file = local_root / file_rel_path
                    files_to_copy.append((src_file, dest_file, code))

    if not files_to_copy:
        st.error("Could not find any files on the network drive for the selected countries.")
        return

    # Progress UI
    total_files = len(files_to_copy)
    progress_bar = st.progress(0, text="Starting download...")

    # 3. Execute the copy operations
    for i, (src_file, dest_file, code) in enumerate(files_to_copy):
        # Update UI text to show what is currently downloading
        percent_complete = (i + 1) / total_files
        folder_name = get_folder_for_country_code(code) or code
        progress_bar.progress(
            percent_complete,
            text=f"Downloading {folder_name}... ({i+1}/{total_files} files)"
        )

        dest_file.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src_file, dest_file)

    # 4. Clean up UI on completion
    progress_bar.empty()
    st.success(f"✅ Successfully downloaded {total_files} files!")

# Initialize this once per Streamlit session (do not reset on reruns).
if "logging_setup_done" not in st.session_state:
    st.session_state.logging_setup_done = False

if not st.session_state.logging_setup_done:
    log_file = setup_logging()
    st.session_state.logging_setup_done = True

# Page config
st.set_page_config(
    page_title="Administrative Boundary Geocoder",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ Administrative Boundary Geocoder")
st.markdown("Map exposure sets to admninistrative boundaries using spatial joins")

# Add sidebar
with st.sidebar:
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

    with st.expander("Browse Available Shapefiles", expanded=False):
        # Pass in the nested dictionary we generated earlier!
        user_available_countries_nested = get_user_available_countries_nested(SHAPEFILE_ROOT_DIR)

        if user_available_countries_nested:
            display_data = build_compact_display_dict(user_available_countries_nested)
            st.json(display_data, expanded=False)
        else:
            st.info("No shapefiles found on disk.")
    list_of_country_folders = build_list_of_countries_from_nested_dict(user_available_countries_nested)
    user_codes = set(resolve_selection_to_codes(list_of_country_folders))
    all_codes = set(get_all_available_country_codes())
    missing_codes = all_codes - user_codes
    if missing_codes:
        st.warning("Shapefiles are available for the following countries but not found locally:")

        # 2. Prune the master config down to just the missing items
        missing_nested_dict = get_missing_countries_tree(SHAPE_MAPPING_ROOT, missing_codes)


        download_tree_nodes = build_streamlit_tree_from_nested_dict(missing_nested_dict)

        # 4. Render the tree
        selected_for_download = tree_select(
            nodes=download_tree_nodes,
            key="download_missing_shapes"
        )
        selected_codes = resolve_selection_to_codes(selected_for_download['checked'])
        if selected_codes:
            if st.button("Download Missing Shapefiles", type="primary", key="download_missing_shapes_button"):
                with st.spinner("Copying shapefiles from network share..."):
                    try:
                        download_shapefiles_from_network(
                            selected_codes=selected_codes
                        )
                    except Exception as e:
                        st.error(f"An error occurred during download: {str(e)}")
                        st.error(traceback.format_exc())




render_geocoder_shapes_ui()


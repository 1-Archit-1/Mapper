"""
Streamlit UI for Shapefile Mapping tab.
"""

import logging
import traceback

import streamlit as st
import pandas as pd
import geopandas as gpd
import tempfile
import os
from pathlib import Path
from src.utils import create_geodataframe, load_shapefile, check_shape_zip_validity, UIError
from .map_generation import display_map
from src.Config import Config
from src.components import (
	data_source_selector,
	csv_uploader,
	database_connection_ui,
	column_selector,
	data_preview,
	database_test_fetch_ui,
	results_display,
	save_outputs_ui
)


def reset_shapefile_state():
	st.session_state.shape_processed = False
	st.session_state.shape_result_df = None
	st.session_state.show_map_shape = False
	st.session_state.shape_original_row_count = None
	st.session_state.pop("shape_map_html", None)
	if "loaded_shapefile" in st.session_state:
		del st.session_state.loaded_shapefile


def render_shapefile_tab():
	"""Render the shapefile mapping tab."""
	# Initialize tab-specific state
	if "shape_processed" not in st.session_state:
		st.session_state.shape_processed = False
	if "shape_result_df" not in st.session_state:
		st.session_state.shape_result_df = None
	if "shape_original_row_count" not in st.session_state:
		st.session_state.shape_original_row_count = None

	st.subheader("Map Coordinates to Shapefile")

	# Data source selection
	data_source = data_source_selector("shape")

	shapefile = None
	upload_container = st.container()
	preview_container = st.container()
	results_container = st.container()
	output_container = st.container()
	map_container = st.container()
	# ==================== UPLOAD/FETCH ====================
	with upload_container:
		col1, col2 = st.columns([3,2])
		with col2:
			st.markdown("#### 2. Upload Shapefile")
			shapefile = st.file_uploader(
				"Upload Shapefile", type=["geojson", "gpkg", "zip"], key="shapefile_db", on_change=reset_shapefile_state
			)
			is_zip = shapefile is not None and shapefile.name.lower().endswith('.zip')
			if is_zip:
				valid, msg = check_shape_zip_validity(shapefile)
				if not valid:
					st.error(f"❌ {msg}")
					shapefile = None

		with col1:
			if data_source == "Upload CSV File":
				st.markdown("#### 1. Upload Files")
				csv_uploader("shape", reset_func=reset_shapefile_state)
			else:
				server, database, username, password, table = database_connection_ui(key_prefix="shape")
				database_test_fetch_ui(server=server, database=database, table=table, key_prefix="shape", username=username, password=password, reset_func = reset_shapefile_state)

	# ==================== COMMON PROCESSING ====================
	df = st.session_state.get("shape_active_input_df")
	if df is not None:
		with preview_container:
			# Check if shapefile is uploaded
			if not shapefile:
				# Show data preview even without shapefile
				data_preview(df)
				return

			# Column selection
			st.markdown("#### 3. Select Columns")
			col_config = column_selector(df, "shape", include_pkey=True)
			dedup_matches = st.checkbox(
				"Deduplicate matched rows",
				value=True,
				key="shape_dedup_matches",
				help="If a point falls inside multiple overlapping polygons, keep only the first match. Disable this to retain all polygon matches per point."
			)
			# Preview data
			data_preview(df)


			# Process button
			if st.button(
					"Process Shapefile Mapping", type="primary", key="shape_process"
			):
				with st.spinner("Processing... This may take a moment"):
					st.session_state.show_map_shape = False
					try:
						# Save shapefile temporarily
						with tempfile.NamedTemporaryFile(
								delete=False, suffix=Path(shapefile.name).suffix
						) as tmp:
							tmp.write(shapefile.getvalue())
							tmp_path = tmp.name

						# Create Config with UI values
						config = Config(values={"shapefile_path": tmp_path})
						shape = load_shapefile(config)
						st.session_state.loaded_shapefile = shape
						# Create geodataframe
						df_geo = create_geodataframe(
							df,
							col_config["lat_col"],
							col_config["lon_col"],
							col_config["use_pkey"],
							col_config["pkey_cols"],
						)
						st.info(f"Created GeoDataFrame with {len(df_geo)} points")

						# Spatial join
						joined = gpd.sjoin(
							df_geo, shape, how="inner", predicate="within")
						del df_geo, shape
						if dedup_matches:
							joined = joined[~joined.index.duplicated(keep='first')]

						st.session_state.shape_result_df = joined.drop(
							columns=["geometry", "index_right"], errors="ignore"
						)
						st.session_state.shape_original_row_count = len(df)
						st.session_state.shape_processed = True
						os.unlink(tmp_path)
						st.success(
							f"Processing complete! Found {len(joined)} matching locations"
						)

					except Exception as e:
						if getattr(e, "already_logged", False):
							pass
						else:
							logging.error(f"Error processing shapefile mapping: {str(e)}")
							logging.error(traceback.format_exc())
						st.error(f"❌ Error: {str(e)}")

					finally:
						if "tmp_path" in locals() and os.path.exists(tmp_path):
							os.unlink(tmp_path)

	# Show results (outside of 'if df is not None' so it persists across reruns)
	if (
		st.session_state.shape_processed
		and st.session_state.shape_result_df is not None
	):
		with results_container:
			st.markdown("#### Results")

			result_df = st.session_state.shape_result_df
			original_rows = st.session_state.get(	"shape_original_row_count", len(result_df))

			# Statistics
			col1, col2, col3 = st.columns(3)
			with col1:
				st.metric("Original Rows", original_rows)
			with col2:
				matched = len(result_df)
				st.metric("Matched Locations", matched)
			with col3:
				match_rate = (matched / original_rows *
							  100) if original_rows > 0 else 0
				st.metric("Match Rate", f"{match_rate:.1f}%")
			output_df = result_df
			# Get input server/database if data was fetched from DB
			input_server = st.session_state.get("shape_db_server")
			input_database = st.session_state.get("shape_db_database")

			results_display(
				display_df=output_df,
			)

		with output_container:
			save_outputs_ui(
				output_df=output_df,
				output_filename="shapefile_mapping_results.csv",
				key_prefix="shape_results",
				input_server=input_server,
				input_database=input_database,
				lat_col=col_config['lat_col'],
				lon_col=col_config['lon_col']
			)

		with map_container:
			map_df = st.session_state.shape_result_df

			if len(map_df) != 0:
				@st.fragment
				def map_controls():
					no_cluster = False
					if len(map_df) > 1000:
						st.caption("More than 1000 matched locations, map will be clustered by default")
						no_cluster = st.checkbox(
							"Show all points without clustering (not recommended)",
							key="shape_show_all_points"
						)
					render_high_res = st.checkbox(
						"Render high-resolution map (may be slow for complex shapes)",
						value = True,
						key="shape_high_res_map"
					)
					if st.button("Generate Map", type="primary", key="shape_map_button"):
						with st.spinner("Generating map..."):
							map_obj, map_html = display_map(
								map_df,
								lat_col=col_config["lat_col"],
								lon_col=col_config["lon_col"],
								_shapefile_gdf=st.session_state.get("loaded_shapefile"),
								popup_cols=map_df.columns.tolist(),
								high_res_shape_map=render_high_res,
								use_clustering='never' if no_cluster else 'auto'
							)
							st.session_state.shape_map_html = map_html
						st.session_state.show_map_shape = True

					if st.session_state.get('show_map_shape') and st.session_state.get('shape_map_html'):
						map_html = st.session_state.shape_map_html
						st.components.v1.html(map_html, height=600)
						col1, col2 = st.columns([4, 1])
						with col2:
							st.download_button(
								label="Download Map as HTML",
								data=map_html,
								file_name=f"map_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.html",
								mime="text/html"
							)

				map_controls()
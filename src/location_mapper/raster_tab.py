"""
Streamlit UI for Raster Value Extraction tab.
"""
import logging
import traceback

import streamlit as st
import tempfile
import os
import numpy as np
import pandas as pd
import plotly.express as px
from src.utils import join_with_raster, load_rasterfile
from src.Config import Config
from src.components import (
	data_source_selector,
	csv_uploader,
	database_connection_ui,
	column_selector,
	data_preview,
	results_display,
	database_test_fetch_ui,
	save_outputs_ui
)
from .map_generation import display_map, capture_raster_overlay
import matplotlib.pyplot as plt
import inspect
def reset_raster_state():
	print('Resetting raster tab state')
	st.session_state.raster_processed = False
	st.session_state.raster_result_df = None
	st.session_state.show_map_raster = False
	st.session_state.raster_overlays = {}

	if 'raster_value_columns' in st.session_state:
		del st.session_state.raster_value_columns

def render_raster_tab():
	"""Render the raster value extraction tab."""
	# Initialize tab-specific state
	if 'raster_processed' not in st.session_state:
		st.session_state.raster_processed = False
	if 'raster_result_df' not in st.session_state:
		st.session_state.raster_result_df = None
	if 'raster_original_row_count' not in st.session_state:
		st.session_state.raster_original_row_count = None
	if 'raster_active_input_df' not in st.session_state:
		st.session_state.raster_active_input_df = None



	st.subheader("Extract Raster Values at Coordinates")

	# Data source selection
	data_source = data_source_selector('raster')
	raster_file = None
	upload_container = st.container()
	preview_container = st.container()
	results_container = st.container()
	output_container = st.container()
	map_container = st.container()
	# ==================== UPLOAD/FETCH ====================

	with upload_container:
		col1, col2 = st.columns([3,2])

		with col1:
			if data_source == "Upload CSV File":
				st.markdown("#### 1. Upload Files")
				csv_uploader(key_prefix = 'raster', reset_func = reset_raster_state)
			else:
				server, database, table = database_connection_ui(key_prefix="raster")
				database_test_fetch_ui(server = server, database = database, table = table, key_prefix = "raster", reset_func = reset_raster_state)
		with col2:
			st.markdown("#### 2. Upload Raster File")
			raster_file = st.file_uploader("Upload Raster File", type=['tif', 'tiff', 'img'], key='raster_file_db', on_change=reset_raster_state)

	# ==================== COMMON PROCESSING ====================

	df = st.session_state.get('raster_active_input_df')
	if  df is not None:
		with preview_container:
			if not raster_file:
				data_preview(df)
				return

			# Column selection
			st.markdown("#### 3. Select Columns")
			col_config = column_selector(df, 'raster', include_pkey=False)

			# Preview data
			data_preview(df)

			retain_valid_only = st.checkbox(
				"Retain only locations with extracted values",
				value=True,
				key="raster_retain_valid",
				help="When enabled, rows where all raster bands returned NoData or fell outside the raster extent are excluded from results."
			)

			# Process button
			if st.button("Extract Raster Values", type="primary", key='raster_process'):
				with st.spinner("Extracting values... This may take a moment"):
					st.session_state.show_map_raster = False
					try:
						# Save raster temporarily
						with tempfile.NamedTemporaryFile(delete=False, suffix='.tif') as tmp:
							tmp.write(raster_file.getvalue())
							tmp_path = tmp.name

						# Create Config with UI values
						config = Config(values={
							'rasterfile_path': tmp_path,
							'latitude_col': col_config['lat_col'],
							'longitude_col': col_config['lon_col']
						})

						raster = load_rasterfile(config)

						num_bands = raster.count
						nodata_value = raster.nodata
						st.info(f"Raster info: {num_bands} band(s), NoData value: {nodata_value}")

						# Extract values using helper function
						result_raster = join_with_raster(df, raster, config)

						st.session_state.raster_result_df = result_raster
						st.session_state.raster_retain_valid_only = retain_valid_only
						st.session_state.raster_original_row_count = len(df)
						st.session_state.raster_processed = True

						# Capture raster image overlays for all bands before closing the file
						raster_overlays = {}
						for band_idx in range(1, raster.count + 1):
							band_name = f'Band_{band_idx}'
							raster_overlays[band_name] = capture_raster_overlay(raster, band=band_idx)
						st.session_state.raster_overlays = raster_overlays

						raster.close()
						os.unlink(tmp_path)

						raster_cols = [col for col in result_raster.columns if col.startswith('Band_')]
						st.session_state.raster_value_columns = raster_cols
						valid_count = result_raster[raster_cols[0]].notna().sum()

						st.success(f"Extraction complete! Got values for {valid_count:,} / {len(df):,} coordinates")

					except Exception as e:
						if getattr(e, 'already_logged', False):
							pass
						else:
							logging.error(f"Error processing raster values: {str(e)}")
							logging.error(traceback.format_exc())
						st.error(f"❌ Error: {str(e)}")
					finally:
						if 'tmp_path' in locals() and os.path.exists(tmp_path):
								os.unlink(tmp_path)

	# Show results
	if st.session_state.raster_processed and st.session_state.raster_result_df is not None:
		with results_container:
			st.markdown("#### Results")

			result_df = st.session_state.raster_result_df
			original_rows = st.session_state.get('raster_original_row_count', len(result_df))

			# Find raster value columns
			raster_cols = [col for col in result_df.columns if col.startswith('Band_') or col == 'Raster_Value']

			# Apply valid-only filter if requested
			if st.session_state.get('raster_retain_valid_only', True) and raster_cols:
				result_df = result_df.dropna(subset=raster_cols, how='all')

			# Statistics
			col1, col2, col3 = st.columns(3)
			with col1:
				st.metric("Total Coordinates", original_rows)
			with col2:
				valid = result_df[raster_cols[0]].notna().sum() if raster_cols else 0
				st.metric("Valid Values", valid)
			with col3:
				st.metric("NoData/Out of Bounds", original_rows - valid)

			# Value distribution
			if len(raster_cols) > 0:
				st.markdown("#### Value Distribution")
				for col in raster_cols:
					# Check if col is continous or categorical based on unique values
					unique_values = result_df[col].nunique()
					is_categorical = unique_values < 20  # Adjust threshold as needed

					with st.expander(f"Distribution for {col}"):
						if is_categorical:
							st.write(f"Column '{col}' appears to be categorical with {unique_values} unique values.")
							value_counts = result_df[col].value_counts().sort_index()
							st.bar_chart(value_counts)
						else:
							st.write(f"Column '{col}' appears to be continuous with {unique_values} unique values")

							# Create histogram data
							data = np.array(result_df[col].dropna())
							fig = px.histogram(data, nbins=20, title=f"Histogram of {col}", opacity=0.8)
							fig.update_traces(marker_line_color='white', marker_line_width=1)
							st.plotly_chart(fig, width='stretch')
							st.write(result_df[col].describe().to_frame().T.style.format("{:.2f}"))

			# Get input server/database if data was fetched from DB
			input_server = st.session_state.get('raster_db_server')
			input_database = st.session_state.get('raster_db_database')

			results_display(
				display_df=result_df
			)


		with output_container:
			save_outputs_ui(
				output_df=result_df,
				output_filename="raster_values_results.csv",
				key_prefix='raster_results',
				input_server=input_server,
				input_database=input_database
			)

		with map_container:
			# drop values with no data for mapping
			map_df = result_df.dropna(subset=st.session_state.get('raster_value_columns', []))

			if len(map_df) != 0:
				@st.fragment
				def map_controls():
					no_cluster = False
					if len(map_df) > 1000:
						st.caption("More than 1000 matched locations, map will be clustered by default")
						no_cluster = st.checkbox(
							"Show all points without clustering (not recommended)",
							key="raster_show_all_points"
						)

					col1, col2 = st.columns(2)
					with col1:
						selected_band = st.selectbox(
							"Select Raster Data to View:",
							st.session_state.get('raster_value_columns', []),
							key="raster_band_select"
						)

					if st.button("Generate Map", type="primary", key="raster_map_button"):
						st.session_state.show_map_raster = True
						st.session_state.frozen_band = selected_band
						st.session_state.raster_frozen_no_cluster = no_cluster

					if st.session_state.get('show_map_raster'):
						active_band = st.session_state.get('frozen_band')
						active_cluster = st.session_state.get('raster_frozen_no_cluster')

						with st.spinner("Generating map..."):
							raster_overlays = st.session_state.get('raster_overlays', {})
							map_obj, map_html = display_map(
								map_df,
								lat_col=col_config["lat_col"],
								lon_col=col_config["lon_col"],
								popup_cols=map_df.columns.tolist(),
								selected_band=active_band,
								_raster_overlay=raster_overlays.get(active_band),
								use_clustering='never' if active_cluster else 'auto'
							)
							st.components.v1.html(map_html, height=500)

							col1, col2 = st.columns([4, 1])
							with col2:
								st.download_button(
									label="Download Map as HTML",
									data=map_html,
									file_name=f"map_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.html",
									mime="text/html"
								)

				map_controls()

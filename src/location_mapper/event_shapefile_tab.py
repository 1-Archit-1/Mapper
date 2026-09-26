"""
Currently unused: Streamlit UI for Event Shapefile Mapping tab.
"""

import logging
import traceback

import streamlit as st
import pandas as pd
import geopandas as gpd
import tempfile
import os
from pathlib import Path
from src.utils import (
	create_geodataframe,
	load_shapefile,
	check_shape_zip_validity,
	detect_base_location_details_table,
	parse_db_object,
	UIError
)
from src.utils.helpers import create_engine_connection
from .map_generation import display_map
from src.Config import Config
from src.components import (
	event_database_connection_ui,
	column_selector,
	data_preview,
	event_database_test_fetch_ui,
	results_display,
	event_dashboard_save_outputs_ui
)
from sqlalchemy import text
from ..db_config import get_event_dashboard_default_config



def reset_event_shapefile_state():
	st.session_state.event_shape_processed = False
	st.session_state.event_shape_result_df = None
	st.session_state.event_shape_show_map = False
	st.session_state.event_shape_original_row_count = None
	st.session_state.pop("event_shape_map_html", None)
	st.session_state.pop("event_shape_detected_details_table", None)
	if "loaded_shapefile" in st.session_state:
		del st.session_state.loaded_shapefile


def render_event_shapefile_tab():
	"""Render the shapefile mapping tab."""
	# Initialize tab-specific state
	if "event_shape_processed" not in st.session_state:
		st.session_state.event_shape_processed = False
	if "event_shape_result_df" not in st.session_state:
		st.session_state.event_shape_result_df = None
	if "event_shape_original_row_count" not in st.session_state:
		st.session_state.event_shape_original_row_count = None

	error_key = "event_shape_table_error"
	if error_key not in st.session_state:
		st.session_state[error_key] = None

	st.subheader("Map Coordinates to Shapefile")

	shapefile = None
	upload_container = st.container()
	preview_container = st.container()
	results_container = st.container()
	output_container = st.container()
	map_container = st.container()
	# ==================== UPLOAD/FETCH ====================
	with upload_container:
		col1, col2 = st.columns(2)
		with col2:
			st.markdown("#### 2. Upload Shapefile")
			shapefile = st.file_uploader(
				"Upload Shapefile", type=["geojson", "gpkg", "zip"], key="event_shapefile_db", on_change=reset_event_shapefile_state
			)
			is_zip = shapefile is not None and shapefile.name.lower().endswith('.zip')
			if is_zip:
				valid, msg = check_shape_zip_validity(shapefile)
				if not valid:
					st.error(f"❌ {msg}")
					shapefile = None

		with col1:
			try:
				default_config = get_event_dashboard_default_config()
			except Exception as e:
				st.session_state[error_key] = str(e)
				st.error(str(e))
				return

			server, database, table = event_database_connection_ui(
				key_prefix="event_shape",
				default_config=default_config,
			)
			if table:
				last_table_key = "event_shape_last_table"
				if st.session_state.get(last_table_key) != table:
					st.session_state[last_table_key] = table
					st.session_state[error_key] = None
					# Invalidate cached details table when base table changes
					st.session_state.pop("event_shape_detected_details_table", None)

				st.session_state[error_key] = None
				#Find table columns
				engine = None
				try:
					engine = create_engine_connection(server, database)
				except Exception as e:
					st.session_state[error_key] = f"Error connecting to {server}.{database}: {str(e)}"
					st.error(f"❌ {st.session_state[error_key]}")
					return

				table_obj = parse_db_object(table, default_schema=None)

				def fetch_columns():
					if table_obj.schema:
						query = text(
							"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :table AND TABLE_SCHEMA = :schema"
						)
						params = {"table": table_obj.table, "schema": table_obj.schema}
					else:
						query = text(
							"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :table"
						)
						params = {"table": table_obj.table}

					with engine.connect() as conn:
						result = conn.execute(query, params)
						return [row.COLUMN_NAME.lower() for row in result]

				try:
					columns = fetch_columns()
				except Exception as e:
					logging.error(f"Error fetching columns for table {table}: {str(e)}")
					logging.error(traceback.format_exc())
					st.session_state[error_key] = f"Error fetching columns for table {table}: {str(e)}"
					columns = []
				will_continue = False
				# Check if required columns are present
				required_columns = default_config.get('required_columns')
				generated_columns = default_config.get('generated_columns')
				missing_columns = [col for col in required_columns if col.lower() not in columns]
				if missing_columns:
					st.session_state[error_key] = (
						f"The selected table is missing required columns: {', '.join(missing_columns)}"
					)
				else:
					# Check if at least one generated column is present
					generated_columns_present = [col for col in generated_columns if col.lower() in columns]
					if not generated_columns_present:
						st.info('Generated cols (e.g. accZnet_SC) not found in table. Run the generate step')
						if st.button("Generate Missing Columns", key="generate_columns_button"):
							with st.spinner("Generating missing columns..."):
								try:
									with engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
										conn.execute(text('EXEC [dbo].[usp_Add_accZnet] @table_name = :tbl'),
												{'tbl': table_obj.bare_table})
									columns = fetch_columns()
									generated_columns_present = [col for col in generated_columns if col.lower() in columns]
									if generated_columns_present:
										st.success("Missing columns generated successfully!")
									else:
										st.warning("Columns were generated but are still not detected.")
								except Exception as e:
									logging.error(f"Error generating columns for table {table}: {str(e)}")
									logging.error(traceback.format_exc())
									st.session_state[error_key] = f"Error generating columns for table {table}: {str(e)}"

					if generated_columns_present:
						st.success(f"All required columns found. Generated columns present: {', '.join(generated_columns_present)}")
						will_continue = True
				if will_continue:
					# Detect location details table once and cache in session state
					if st.session_state.get("event_shape_detected_details_table") is None:
						try:
							detected = detect_base_location_details_table(table, default_config)
							st.session_state["event_shape_detected_details_table"] = detected
						except Exception as e:
							logging.error(f"Error detecting location details table: {str(e)}")
							st.session_state["event_shape_detected_details_table"] = default_config.get("base_location_details_table")

					event_database_test_fetch_ui(
						server,
						database,
						table,
						required_columns+generated_columns,
						reset_func = reset_event_shapefile_state
					)

				if st.session_state.get(error_key):
					st.error(f"❌ {st.session_state[error_key]}")

				if engine is not None:
					engine.dispose()

	# ==================== COMMON PROCESSING ====================
	df = st.session_state.get("event_shape_active_input_df")
	if df is not None:
		with preview_container:
			# Check if shapefile is uploaded
			if not shapefile:
				# Show data preview even without shapefile
				data_preview(df)
				return

			# Column selection
			st.markdown("#### 3. Select Columns")
			col_config = column_selector(df, "event_shape", include_pkey=True)
			# Cache col_config for use in map fragment across reruns
			st.session_state["event_shape_col_config"] = col_config
			dedup_matches = st.checkbox(
				"Deduplicate matched rows",
				value=True,
				key="event_shape_dedup_matches",
				help="If a point falls inside multiple overlapping polygons, keep only the first match. Disable this to retain all polygon matches per point."
			)
			# Preview data
			data_preview(df)


			# Process button
			if st.button(
				"Process Shapefile Mapping", type="primary", key="event_shape_process"
			):
				with st.spinner("Processing... This may take a moment"):
					st.session_state.event_shape_show_map = False
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
						if dedup_matches:
							joined = joined[~joined.index.duplicated(keep='first')]
						st.session_state.event_shape_result_df = joined
						st.session_state.event_shape_original_row_count = len(df)
						st.session_state.event_shape_processed = True
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
		st.session_state.event_shape_processed
		and st.session_state.event_shape_result_df is not None
	):
		with results_container:
			st.markdown("#### Results")

			result_df = st.session_state.event_shape_result_df
			original_rows = st.session_state.get(	"event_shape_original_row_count", len(result_df))

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
			output_df = result_df.drop(
				columns=["geometry", "index_right"], errors="ignore"
			)

			input_table = st.session_state.get("event_shape_db_table")



			results_display(
				display_df=output_df,
			)

		with output_container:
			base_location_details_table = st.session_state.get(
				"event_shape_detected_details_table",
				default_config.get("base_location_details_table")
			)
			event_dashboard_save_outputs_ui(
				output_df=output_df,
				default_config=default_config,
				key_prefix="event_shape_results",
				detected_location_details_table=base_location_details_table
			)

		with map_container:
			map_df = pd.DataFrame(st.session_state.event_shape_result_df)

			if len(map_df) != 0:
				@st.fragment
				def map_controls():
					saved_col_config = st.session_state.get("event_shape_col_config", {})
					lat_col = saved_col_config.get("lat_col", "Latitude")
					lon_col = saved_col_config.get("lon_col", "Longitude")

					no_cluster = False
					if len(map_df) > 1000:
						st.caption("More than 1000 matched locations, map will be clustered by default")
						no_cluster = st.checkbox(
							"Show all points without clustering (not recommended)",
							key="event_shape_show_all_points"
						)
					render_high_res = st.checkbox(
						"Render high-resolution map (may be slow for complex shapes)",
						value = True,
						key="event_shape_high_res_map"
					)
					if st.button("Generate Map", type="primary", key="event_shape_map_button"):
						with st.spinner("Generating map..."):
							map_obj, map_html = display_map(
								map_df,
								lat_col=lat_col,
								lon_col=lon_col,
								_shapefile_gdf=st.session_state.get("loaded_shapefile"),
								popup_cols=map_df.columns.tolist(),
								high_res_shape_map=render_high_res,
								use_clustering='never' if no_cluster else 'auto'
							)
							st.session_state.event_shape_map_html = map_html
						st.session_state.event_shape_show_map = True

					if st.session_state.get('event_shape_show_map') and st.session_state.get('event_shape_map_html'):
						map_html = st.session_state.event_shape_map_html
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
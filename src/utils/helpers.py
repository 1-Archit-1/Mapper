import tempfile
import zipfile

import rasterio
from sqlalchemy import create_engine, text
import pandas as pd
import geopandas as gpd
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass
import os
from ..Config import Config
import pyodbc
import urllib.parse
import logging
import traceback
from datetime import datetime


class AppError(Exception):
	"""Application-level error with optional marker for prior logging."""

	def __init__(self, message: str, already_logged: bool = False):
		super().__init__(message)
		self.already_logged = already_logged

class UIError(AppError):
	"""Error intended to be shown to the user, with prior logging."""
	""" Currently unused """
	def __init__(self, message: str):
		super().__init__(message, already_logged=True)


@dataclass(frozen=True)
class DbObject:
	"""Parsed database object parts (database, schema, table)."""
	raw: str
	database: Optional[str]
	schema: Optional[str]
	table: str

	@property
	def schema_table(self) -> str:
		if self.schema:
			return f"{self.schema}.{self.table}"
		return self.table

	@property
	def bare_table(self) -> str:
		return self.table


def _split_qualified_name(value: str) -> List[str]:
	"""Split a qualified name into parts, honoring brackets."""
	parts: List[str] = []
	current: List[str] = []
	in_brackets = False
	for ch in value:
		if ch == '[':
			in_brackets = True
			continue
		if ch == ']':
			in_brackets = False
			continue
		if ch == '.' and not in_brackets:
			part = "".join(current).strip()
			if part:
				parts.append(part)
			current = []
			continue
		current.append(ch)
	part = "".join(current).strip()
	if part:
		parts.append(part)
	return parts


def parse_db_object(
	name: str,
	default_schema: Optional[str] = "dbo",
	default_database: Optional[str] = None
) -> DbObject:
	"""Parse a database object name into database/schema/table parts."""
	if name is None or str(name).strip() == "":
		raise ValueError("Database object name is required")

	parts = _split_qualified_name(str(name).strip())
	if len(parts) == 1:
		table = parts[0]
		schema = default_schema
		database = default_database
	elif len(parts) == 2:
		schema, table = parts
		database = default_database
	else:
		database = ".".join(parts[:-2]) or default_database
		schema = parts[-2]
		table = parts[-1]

	return DbObject(raw=str(name), database=database, schema=schema, table=table)


def format_db_object_sql(obj: DbObject, include_database: bool = False) -> str:
	"""Format a DbObject as bracketed SQL identifier parts."""
	parts: List[str] = []
	if include_database and obj.database:
		parts.append(obj.database)
	if obj.schema:
		parts.append(obj.schema)
	parts.append(obj.table)
	return ".".join(f"[{part}]" for part in parts)

# Setup logging
def setup_logging():
	"""Setup logging configuration to write errors to logfile only."""
	log_dir = 'logs'
	if not os.path.exists(log_dir):
		os.makedirs(log_dir)

	# Rotate by date only: one log file per day.
	today_stamp = datetime.now().strftime('%Y%m%d')
	log_file = os.path.join(log_dir, f'error_log_{today_stamp}.log')
	abs_log_file = os.path.abspath(log_file)

	root_logger = logging.getLogger()
	for handler in root_logger.handlers:
		if isinstance(handler, logging.FileHandler) and os.path.abspath(getattr(handler, 'baseFilename', '')) == abs_log_file:
			return log_file

	# Keep logging output file-only by replacing any existing handlers.
	for handler in list(root_logger.handlers):
		root_logger.removeHandler(handler)
		handler.close()

	# Suppress third-party library noise (rasterio, GDAL, tornado, etc.)
	root_logger.setLevel(logging.WARNING)

	file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
	file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
	root_logger.addHandler(file_handler)

	# Allow app-level loggers to log DEBUG and above regardless of root level
	for app_logger_name in ('src', '__main__', 'location_mapper', 'geocoder'):
		logging.getLogger(app_logger_name).setLevel(logging.DEBUG)

	print(f"Logging initialized. Errors will be written to: {log_file}")
	return log_file

## Create a database connection using SQLAlchemy with ODBC drivers,
# prioritizing modern drivers and falling back to legacy if necessary.
def create_engine_connection(server, database, fast_executemany=True):
	# Strip square brackets from database name - they're not valid in connection strings
	database = database.strip('[]')
	installed_drivers = pyodbc.drivers()
	selected_driver = None
	trust_cert = 'Trusted_Connection=yes;'
	is_legacy = False

	# --- Modern ODBC Drivers ---
	# We iterate through known versions.
	priority_versions = [18, 17, 13]

	for version in priority_versions:
		driver_name = f"ODBC Driver {version} for SQL Server"
		if driver_name in installed_drivers:
			selected_driver = f"{{{driver_name}}}"
			print(f"Found modern driver: {driver_name}")

			if version == 18:
				trust_cert += 'TrustServerCertificate=yes;'
			break

	# --- Native Client (Good alternative) ---
	if not selected_driver:
		if "SQL Server Native Client 11.0" in installed_drivers:
			selected_driver = "{SQL Server Native Client 11.0}"
			print("Modern ODBC not found. Using 'SQL Server Native Client 11.0'.")

	# --- Legacy Default (Bad) ---
	if not selected_driver:
		selected_driver = "{SQL Server}"
		is_legacy = True
		print("\n" + "!"*60)
		print("CRITICAL WARNING: No modern SQL drivers found.")
		print("   Falling back to legacy '{SQL Server}' driver.")
		print("   Database insertions will likely FAIL ")
		print("!"*60 + "\n")

	params = urllib.parse.quote_plus(
		f"DRIVER={selected_driver};"
		f"SERVER={server};"
		f"DATABASE={database};"
		f"{trust_cert}"
	)
	use_fast = (not is_legacy) and ("ODBC Driver" in selected_driver) and fast_executemany

	engine = create_engine(
		f"mssql+pyodbc:///?odbc_connect={params}",
		fast_executemany=use_fast
	)
	return engine

# Fetch data from specified CSV file
def fetch_data_from_csv(config):
	csv_path = config.get_env(
		'csv_input_path',
		prompt="Enter the full path of the input CSV file (including .csv extension):\n",
		case_sensitive=True
	)
	try:
		df = pd.read_csv(csv_path)
		print(f"CSV loaded successfully from: {csv_path}")
		return df
	except Exception as e:
		logging.error(f"Failed to load CSV file from '{csv_path}'")
		logging.error(traceback.format_exc())
		print(f"\n❌ Error: Failed to load CSV file from '{csv_path}'")
		print(f"   Reason: {str(e)}")
		raise AppError(f"Failed to load CSV file from '{csv_path}' \n Reason: {str(e)}", already_logged=True) from e

# Fetch data from specified DB table
def fetch_table_columns(engine, table: str) -> List[str]:
	"""Return column names for a table without fetching any rows."""
	table_obj = parse_db_object(table, default_schema=None)
	table_ref = format_db_object_sql(table_obj)
	with engine.connect() as conn:
		empty = pd.read_sql(text(f"SELECT TOP 0 * FROM {table_ref}"), conn)
	return empty.columns.tolist()


def fetch_data_from_db(engine, table: str, required_columns: Optional[List[str]] = None, chunksize: int = 100_000, progress_callback=None):
	try:
		table_obj = parse_db_object(table, default_schema=None)
		table_ref = format_db_object_sql(table_obj)
		with engine.execution_options(stream_results=True).connect() as conn:
			if required_columns:
				cols_str = ", ".join(required_columns)
				query = text(f"SELECT {cols_str} FROM {table_ref}")
			else:
				query = text(f"SELECT * FROM {table_ref}")
			def _chunks(chunk_iter):
				rows_so_far = 0
				for chunk in chunk_iter:
					rows_so_far += len(chunk)
					if progress_callback:
						progress_callback(rows_so_far)
					yield chunk
			chunks = pd.read_sql(query, conn, chunksize=chunksize)
			df = pd.concat(_chunks(chunks), ignore_index=True)
		return df
	except Exception as e:
		logging.error(f"Failed to fetch data from table '{table}'")
		logging.error(traceback.format_exc())
		print(f"\n❌ Error: Failed to fetch data from table '{table}'")
		print(f"   Reason: {str(e)}")
		raise AppError(f"Failed to fetch data from table '{table}' \n Reason: {str(e)}", already_logged=True) from e


def insert_data_to_db(engine, df: pd.DataFrame, table_name: str, chunksize: int = 100_000):
	table_obj = parse_db_object(table_name, default_schema=None)
	with engine.connect() as conn:
		df.to_sql(table_obj.table, conn, if_exists='replace', index=False, schema=table_obj.schema, chunksize=chunksize)
	print(f"Data inserted successfully into {table_obj.schema_table}")


def insert_event_metadata(
	engine,
	event_table: str,
	event_name: str,
	event_date,
	affected_location: str,
	event_type: str,
	event_type_label: str,
	peril_metric_set: str,
	raw_table_name: str
) -> int:
	try:
		table_obj = parse_db_object(event_table, default_schema=None)
		table_ref = format_db_object_sql(table_obj)
		insert_sql = text(
			f"""
			INSERT INTO {table_ref} (
				event_name,
				event_date,
				affected_location,
				event_type,
				event_type_label,
				peril_metric_set,
				raw_table_name
			)
			OUTPUT INSERTED.event_id
			VALUES (
				:event_name,
				:event_date,
				:affected_location,
				:event_type,
				:event_type_label,
				:peril_metric_set,
				:raw_table_name
			)
			"""
		)
		with engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
			result = conn.execute(
				insert_sql,
				{
					"event_name": event_name,
					"event_date": event_date,
					"affected_location": affected_location,
					"event_type": event_type,
					"event_type_label": event_type_label,
					"peril_metric_set": peril_metric_set,
					"raw_table_name": raw_table_name
				}
			)
			event_id = result.scalar()
		return event_id
	except Exception as e:
		logging.error(f"Error inserting event metadata: {str(e)}")
		logging.error(traceback.format_exc())
		raise AppError(f"Error inserting event metadata: {str(e)}", already_logged=True) from e


def seed_event_exposures(engine, event_id: int, location_details_table: str):
	try:
		location_table_obj = parse_db_object(location_details_table, default_schema=None)
		location_table_name = location_table_obj.bare_table
		with engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
			conn.execute(
				text(
					'EXEC [dbo].[usp_Seed_Event_Exposures] @event_id = :event_id, @location_details_table = :location_details_table'
				),
				{
					"event_id": event_id,
					"location_details_table": location_table_name
				}
			)
	except Exception as e:
		logging.error(f"Error seeding event exposures: {str(e)}")
		logging.error(traceback.format_exc())
		raise AppError("Error seeding event exposures", already_logged=True) from e


def recalculate_znet(engine, event_id: int):
	try:
		with engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
			conn.execute(
				text('EXEC [dbo].[usp_Recalculate_ZNet] @event_id = :event_id'),
				{
					"event_id": event_id
				}
			)
	except Exception as e:
		logging.error(f"Error recalculating ZNet: {str(e)}")
		logging.error(traceback.format_exc())
		raise AppError("Error recalculating ZNet", already_logged=True) from e


def detect_column_candidates(columns: List[str], patterns: List[str]):
	return [col for col in columns if col in patterns]


def get_latitude_longitude_columns(
	df: pd.DataFrame,
	config: Config
):
	"""Get or prompt for latitude and longitude column names."""
	latitude_assumptions = []
	longitude_assumptions = []
	columns = df.columns.tolist()
	if not config.use_env:
		lat_patterns = ['latitude', 'Latitude', 'LATITUDE', 'lat', 'Lat', 'LAT']
		latitude_assumptions = detect_column_candidates(columns, lat_patterns)

		lon_patterns = ['longitude', 'Longitude', 'LONGITUDE', 'long', 'Long', 'LONG', 'lon', 'Lon', 'LON']
		longitude_assumptions = detect_column_candidates(columns, lon_patterns)

	latitude = config.get_env(
		'latitude_col',
		prompt = f"Enter Latitude column name:\nDetected options: {latitude_assumptions}\n",
		valid_options=columns,
		case_sensitive=True
	)
	longitude = config.get_env(
		'longitude_col',
		prompt = f"Enter Longitude column name:\nDetected options: {longitude_assumptions}\n",
		valid_options=columns,
		case_sensitive=True
	)
	return latitude, longitude


def get_primary_key_columns(
	df: pd.DataFrame,
	config: Config
):
	"""Get or prompt for primary key column names."""
	use_pkey = config.get_bool('use_primary_key', prompt = "Do you want to use a Primary Key column? (y/n): ")

	if not use_pkey:
		return False, []

	columns = df.columns.tolist()
	pkey_assumptions = []
	if not config.use_env:
		pkey_patterns = ['LOCID', 'LocID', 'locid', 'LOCNUM', 'LocNum', 'locnum', 'ID', 'id']
		pkey_assumptions = detect_column_candidates(columns, pkey_patterns)

	pkey = config.get_pkeys(
		valid_options=columns + ['stop'],
		pkey_assumptions=pkey_assumptions
	)
	return True, pkey



def load_shapefile(config: Config):
	shapefile_path = config.get_env(
		'shapefile_path',
		prompt="Enter the full path of the shapefile \n .geojson, .gpkg, .zip(containing .shp, .shx, .dbf, .prj):\n",
		case_sensitive=True
	)
	try:
		if shapefile_path.lower().endswith('.zip'):
			return load_shapefile_zip(shapefile_path)
		else:
			shape = gpd.read_file(shapefile_path)
			if shape.crs and shape.crs.to_epsg() != 4326:
				shape = shape.to_crs(epsg=4326)
			print("Shapefile loaded successfully.")
			return shape
	except Exception as e:
		logging.error(f"Failed to load shapefile from '{shapefile_path}'")
		logging.error(traceback.format_exc())
		print(f"\n❌ Error: Failed to load shapefile from '{shapefile_path}'")
		print(f"   Reason: {str(e)}")
		raise AppError(f"Failed to load shapefile from '{shapefile_path}' \n Reason: {str(e)}", already_logged=True) from e

def load_shapefile_zip(zip_path: str):
	with tempfile.TemporaryDirectory() as tmpdir:
		with zipfile.ZipFile(zip_path, 'r') as z:
			z.extractall(tmpdir)
			files = os.listdir(tmpdir)

			extensions = [os.path.splitext(f)[1].lower() for f in files]
			missing = [ext for ext in ['.shp', '.shx', '.dbf', '.prj'] if ext not in extensions]
			if missing:
				raise AppError(f"Uploaded ZIP is missing required shapefile components: {', '.join(missing)}")
			shp_file = [os.path.join(dp, f) for dp, dn, filenames in os.walk(tmpdir)
									for f in filenames if f.endswith('.shp')][0]
			gdf = gpd.read_file(shp_file)
			if gdf.crs and gdf.crs.to_epsg() != 4326:
				gdf = gdf.to_crs(epsg=4326)
			return gdf

def check_shape_zip_validity(zip_path: str) -> Tuple[bool, Optional[str]]:
	try:
		with zipfile.ZipFile(zip_path, 'r') as z:
			files = z.namelist()
			extensions = [os.path.splitext(f)[1].lower() for f in files]
			missing = [ext for ext in ['.shp', '.shx', '.dbf', '.prj'] if ext not in extensions]
			if missing:
				return False, f"Uploaded ZIP is missing required shapefile components: {', '.join(missing)}"
		return True, None
	except zipfile.BadZipFile:
		logging.error("Invalid ZIP uploaded for shapefile validation")
		logging.error(traceback.format_exc())
		return False, "Uploaded file is not a valid ZIP archive."
	except Exception:
		logging.error("Unexpected error while validating shapefile ZIP")
		logging.error(traceback.format_exc())
		return False, "Could not validate ZIP file. Please try another file."

def load_rasterfile(config: Config):
	raster_path = config.get_env(
		'rasterfile_path',
		prompt="Enter the full path of the raster file (.tif, .img, etc):\n",
		case_sensitive=True
	)
	try:
		raster = rasterio.open(raster_path)
		print("Raster file loaded successfully.")
		return raster
	except Exception as e:
		logging.error(f"Failed to load raster file from '{raster_path}'")
		logging.error(traceback.format_exc())
		print(f"\n❌ Error: Failed to load raster file from '{raster_path}'")
		print(f"   Reason: {str(e)}")
		raise AppError(f"Failed to load raster file from '{raster_path}' \n Reason: {str(e)}", already_logged=True, ) from e

def create_geodataframe(
	df: pd.DataFrame,
	latitude: str,
	longitude: str,
	use_pkey: bool,
	pkey: Optional[List[str]] = None
):
	"""Create a GeoDataFrame from DataFrame with lat/lon coordinates."""
	try:
		if use_pkey and pkey:
			df = df[pkey + [latitude, longitude]]
			df = df.drop_duplicates(subset=pkey)

		df_geo = gpd.GeoDataFrame(
			df,
			geometry=gpd.points_from_xy(df[longitude], df[latitude]),
			crs="EPSG:4326"
		)
		return df_geo
	except Exception as e:
		logging.error("Failed to create GeoDataFrame from input data")
		logging.error(traceback.format_exc())
		print(f"\n❌ Error: Failed to create GeoDataFrame from input data")
		print(f"   Reason: {str(e)}")
		raise AppError(f"Failed to create GeoDataFrame from input data\n Reason: {str(e)}", already_logged=True) from e

def join_with_raster(
	df: pd.DataFrame,
	raster: rasterio.io.DatasetReader,
	config: Config
):
	"""Join location data with raster values based on lat/lon coordinates.
	Returns a DataFrame with an additional column for raster values.
	"""
	num_bands = raster.count
	nodata_value = raster.nodata

	# Get lat/lon column names from config
	lat_col = config.get_env('latitude_col')
	lon_col = config.get_env('longitude_col')

	lons = df[lon_col].values
	lats = df[lat_col].values

	# raster.sample() expects coordinates in the raster's native CRS.
	# Reproject from WGS84 only when the raster is not already in EPSG:4326.
	raster_crs = raster.crs
	if raster_crs and raster_crs.to_epsg() != 4326:
		from pyproj import Transformer
		transformer = Transformer.from_crs('EPSG:4326', raster_crs, always_xy=True)
		lons, lats = transformer.transform(lons, lats)

	from rasterio.transform import rowcol
	from rasterio.windows import Window

	rows, cols = rowcol(raster.transform, lons, lats)
	rows = np.asarray(rows, dtype=np.intp)
	cols = np.asarray(cols, dtype=np.intp)
	in_bounds = (
		(rows >= 0) & (rows < raster.height) &
		(cols >= 0) & (cols < raster.width)
	)
	fill = nodata_value if nodata_value is not None else np.nan
	sampled_values = np.full((len(rows), num_bands), fill, dtype=float)

	valid_idx = np.where(in_bounds)[0]
	if valid_idx.size > 0:
		raster_pixels = raster.height * raster.width
		# Target ~200 MB per band per tile (float64 = 8 bytes/pixel).
		# Not divided by num_bands — each band window read stays under 200 MB.
		tile_pixels = max(1, 200 * 1024 * 1024 // 8)
		side = max(1, int(tile_pixels ** 0.5))
		tile_rows = min(side, raster.height)
		tile_cols = min(side, raster.width)

		if raster_pixels <= tile_pixels:
			# Fits in one read — skip tiling overhead entirely
			data = raster.read().astype(float)
			sampled_values[valid_idx] = data[:, rows[valid_idx], cols[valid_idx]].T
		else:
			# Group valid points by tile key — only occupied tiles are read.
			# This avoids iterating empty tiles for large sparse rasters.
			valid_r = rows[valid_idx]
			valid_c = cols[valid_idx]
			tile_r_idx = valid_r // tile_rows
			tile_c_idx = valid_c // tile_cols
			n_tile_cols = (raster.width + tile_cols - 1) // tile_cols
			tile_keys = tile_r_idx * n_tile_cols + tile_c_idx
			order = np.argsort(tile_keys, kind='stable')
			sorted_keys = tile_keys[order]
			split_points = np.where(np.diff(sorted_keys))[0] + 1

			for group in np.split(order, split_points):
				r0 = int(tile_r_idx[group[0]]) * tile_rows
				c0 = int(tile_c_idx[group[0]]) * tile_cols
				r1 = min(r0 + tile_rows, raster.height)
				c1 = min(c0 + tile_cols, raster.width)
				window = Window(c0, r0, c1 - c0, r1 - r0)
				tile_data = raster.read(window=window).astype(float)
				orig_idx = valid_idx[group]
				sampled_values[orig_idx] = tile_data[:, valid_r[group] - r0, valid_c[group] - c0].T

	for band_idx in range(num_bands):
		band_values = sampled_values[:, band_idx]
		if nodata_value is not None:
			band_values = np.where(band_values == nodata_value, np.nan, band_values)

		col_name = f'Band_{band_idx + 1}'
		df[col_name] = band_values
	return df

def save_to_database(
	engine,
	joined: gpd.GeoDataFrame,
	config: Config,
	mode: str
):
	"""Save joined data to database table."""
	save_to_db = config.get_bool('save_to_db', prompt="Do you want to save the joined data to the database? (y/n): ")
	if save_to_db:
		table_name = config.get_env(
			'output_table_name',
			prompt="Enter the output table name to save the joined data:\n",
			case_sensitive=True
		)
		print("\nSaving results to database...")
		if mode == 'shape':
			output_df = joined.drop(columns=['geometry', 'index_right'])
		elif mode == 'raster':
			output_df = joined
		try:
			odbc_params = urllib.parse.unquote_plus(engine.url.query.get('odbc_connect', ''))
			# Check specifically for "{SQL Server}" driver
			if "DRIVER={SQL Server}" in odbc_params:
					print("Legacy Driver detected. Attempting 'Nuclear' cleaning (Converting objects to String)...")
					# Apply the fix to convert objects to strings and handle NaNs
					output_df = clean_df_nuclear_option(output_df)
			else:
					print(f"Modern driver detected. Proceeding with standard insert.")

			# Insert
			insert_data_to_db(engine, output_df, table_name)

		except Exception as e:
			logging.error(f"Failed to save data to database table '{table_name}'")
			logging.error(traceback.format_exc())
			print(f"\n❌ Error: Failed to save data to database table '{table_name}'")
			print(f"   Reason: {str(e)}")
			# Don't raise error here to allow process to continue even if DB save fails

def clean_df_nuclear_option(df):
	df = df.copy()
	for col in df.columns:
		# Only target object columns (strings, mixed types)
		if df[col].dtype == 'object':
			df[col] = df[col].astype(str)
			df[col] = df[col].replace({'nan': None, 'NaT': None, 'None': None})
	return df

def save_to_geojson(
	joined: gpd.GeoDataFrame,
	config: Config
):
	"""Save joined data to GeoJSON file."""
	save_to_geojson = config.get_bool('save_joined_geojson', prompt="Do you want to save the joined data to a GeoJSON file? (y/n): ")
	if save_to_geojson:
		geojson_path = config.get_env(
			'output_geojson',
			prompt="Enter the full path for the output GeoJSON file (including .geojson extension):\n",
			case_sensitive=True
		)
		try:
			joined.to_file(geojson_path, driver='GeoJSON')
			print(f"Joined data saved to GeoJSON: {geojson_path}")
		except Exception as e:
			logging.error(f"Failed to save GeoJSON file to '{geojson_path}'")
			logging.error(traceback.format_exc())
			print(f"\n❌ Error: Failed to save GeoJSON file to '{geojson_path}'")
			print(f"   Reason: {str(e)}")
			# Don't raise error here to allow process to continue even if GeoJSON save fails

def save_to_csv(
	joined: gpd.GeoDataFrame,
	config: Config
):
	"""Save joined data to CSV file."""
	save_to_csv = config.get_bool('save_to_csv', prompt="Do you want to save the joined data to a CSV file? (y/n): ")
	if save_to_csv:
		csv_path = config.get_env(
			'output_csv',
			prompt="Enter the full path for the output CSV file (including .csv extension):\n",
			case_sensitive=True
		)
		output_df = joined.drop(columns=['geometry', 'index_right'], errors='ignore')
		try:
			output_df.to_csv(csv_path, index=False)
			print(f"Joined data saved to CSV: {csv_path}")
		except Exception as e:
			logging.error(f"Failed to save CSV file to '{csv_path}'")
			logging.error(traceback.format_exc())
			print(f"\n❌ Error: Failed to save CSV file to '{csv_path}'")
			print(f"   Reason: {str(e)}")
			# Don't raise error here to allow process to continue even if CSV save fails

def verify_available_shapes(dir_path: str, grouped_set_names: Optional[set[str]] = None) -> List[str]:
	# Check for available shapes in the DIR
	# Directory will have subdirs, each for a country,
	# Each subdir will have an admin folder
	# Each admin folder will have shapefiles for each admin level
	# Return a dict of country (folder name) and a list of available shapes inside it
	available_shapes = {}
	grouped_shape_set_names = {name.lower() for name in (grouped_set_names or set())}
	for country_dir in os.listdir(dir_path):
		country_path = os.path.join(dir_path, country_dir)
		if os.path.isdir(country_path):
			admin_shapes = []
			# Generic grouped-set layout: top-level group contains child folders with admin/...
			if country_dir.lower() in grouped_shape_set_names:
				group_shapes = []
				for child_dir in os.listdir(country_path):
					child_path = os.path.join(country_path, child_dir)
					if not os.path.isdir(child_path):
						continue
					child_admin_dir = os.path.join(child_path, 'admin')
					child_mod_dir = os.path.join(child_admin_dir, 'mod')
					active_admin_dir = child_mod_dir if os.path.isdir(child_mod_dir) else child_admin_dir
					if os.path.isdir(active_admin_dir):
						for shape_file in os.listdir(active_admin_dir):
							if shape_file.endswith('.shp'):
								base_name = os.path.splitext(shape_file)[0]
								required_files = [f"{base_name}.shx", f"{base_name}.dbf", f"{base_name}.prj"]
								if all(os.path.exists(os.path.join(active_admin_dir, req)) for req in required_files):
									group_shapes.append(f"{child_dir}/{shape_file}")
				available_shapes[country_dir] = group_shapes
				continue

			admin_dir = os.path.join(country_path, 'admin')
			if os.path.isdir(admin_dir):
				for shape_file in os.listdir(admin_dir):
					if shape_file.endswith('.shp'):
						# Check if associated .shx, .dbf, .prj files exist
						base_name = os.path.splitext(shape_file)[0]
						required_files = [f"{base_name}.shx", f"{base_name}.dbf", f"{base_name}.prj"]
						if all(os.path.exists(os.path.join(admin_dir, req)) for req in required_files):
							admin_shapes.append(shape_file)
			available_shapes[country_dir] = admin_shapes
	return available_shapes

def detect_base_location_details_table(input_table: str, default_config: dict) -> str:
	mapper_engine = create_engine_connection(
		default_config.get('server'),
		default_config.get('database')
	)
	default_base_location_details_table = default_config.get('base_location_details_table')
	base_location_details_wildcard = default_config.get('base_location_details_table_wildcard')
	base_exposure_table_wildcard = default_config.get('base_exposure_table_wildcard')
	detected_base_location_details_table = None
	input_table_name = None
	if input_table:
		try:
			input_table_name = parse_db_object(input_table, default_schema=None).table
		except ValueError:
			input_table_name = None
	# Check if input table matches expected base exposure table pattern for event dashboard processing
	if input_table_name and base_exposure_table_wildcard and base_exposure_table_wildcard in input_table_name:
		# Extract Year and Quarter from input table name based on expected naming convention
		# eg 2025Q4 at the end
		year_quarter = input_table_name[-6:]
		import re
		match = re.match(r'(\d{4}Q\d)', year_quarter)

		if match:
			base_location_details_table = base_location_details_wildcard+year_quarter
			# Check if corresponding base location details table exists
			with mapper_engine.connect() as conn:
				query = text(f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{base_location_details_table}'")
				result = conn.execute(query)
				if result.fetchone():
					detected_base_location_details_table = base_location_details_table

	if not detected_base_location_details_table:
		detected_base_location_details_table = default_base_location_details_table

	return detected_base_location_details_table



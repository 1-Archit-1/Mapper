import os
import sys
from dotenv import load_dotenv
import geopandas as gpd
import logging
import traceback
from src.utils import (
	create_engine_connection,
	fetch_data_from_db,
	fetch_data_from_csv,
	get_latitude_longitude_columns,
	get_primary_key_columns,
	load_shapefile,
	create_geodataframe,
	save_to_database,
	save_to_geojson,
	save_to_csv,
	setup_logging
)
from src.location_mapper.map_generation import create_and_save_map
from src.Config import Config


def get_database_config(config: Config):
	server = config.get_env('server', prompt="Enter server name: ")
	database = config.get_env('database', prompt="Enter database name: ")
	use_windows_auth = config.get_bool('use_windows_auth', prompt="Use Windows Authentication? (y/n): ")
	username = None
	password = None
	if not use_windows_auth:
		username = config.get_env('db_username', prompt="Enter database username: ")
		password = config.get_env('db_password', prompt="Enter database password: ")
	table = config.get_env('table', prompt="Enter table name: ")
	return server, database, username, password, table


def main(config: Config):
	use_db_for_source_data  = config.get_bool(
		'use_db_for_source_data',
		prompt="Fetch data from database? (y/n): "
	)
	if not use_db_for_source_data:
		print("Defaulting to CSV input mode. Please ensure you have a CSV file with Latitude and Longitude columns.")


	if use_db_for_source_data:
		server, db, username, password, table = get_database_config(config)
		print(f"Using server: {server}, database: {db}, table: {table}")

		print("\nConnecting to database...")
		engine = create_engine_connection(server, db, username, password)
		df_table = fetch_data_from_db(engine, table)
		print(f"Fetched {len(df_table)} records from {table}")
	else:
		df_table = fetch_data_from_csv(config)

	print("\nConfiguring coordinate columns...")
	latitude, longitude = get_latitude_longitude_columns(df_table, config)

	print("\nConfiguring primary key...")
	use_pkey, pkey = get_primary_key_columns(df_table, config)

	# Validate that required columns exist in the DataFrame.
	if latitude not in df_table.columns:
		logging.error(f"Latitude column '{latitude}' not found in dataframe columns")
		raise ValueError(
			f"Latitude column '{latitude}' not found. "
			f"Available columns: {', '.join(df_table.columns)}"
		)
	if longitude not in df_table.columns:
		logging.error(f"Longitude column '{longitude}' not found in dataframe columns")
		raise ValueError(
			f"Longitude column '{longitude}' not found. "
			f"Available columns: {', '.join(df_table.columns)}"
		)
	if pkey and not all(col in df_table.columns for col in pkey):
		logging.error(f"Primary Key columns {pkey} not found in dataframe columns")
		raise ValueError(
			f"Primary Key columns {pkey} not found. "
			f"Available columns: {', '.join(df_table.columns)}"
		)

	print(f"Selected Latitude column: {latitude}")
	print(f"Selected Longitude column: {longitude}")
	if pkey:
		print(f"Selected Primary Key columns: {pkey}")

	print("\nLoading shapefile...")
	shape = load_shapefile(config = config)
	print(f"Loaded shapefile with {len(shape)} features")

	# Create GeoDataFrame from location data
	df_geo = create_geodataframe(df_table, latitude, longitude, use_pkey, pkey)
	print(f"Created GeoDataFrame with {len(df_geo)} points")
	print(f"Columns: {df_geo.columns.tolist()}")

	# Spatial join
	joined = gpd.sjoin(df_geo, shape, how="inner", predicate='within')
	print(f"Found {len(joined)} locations within shapefile boundaries")

	if len(joined) == 0:
		logging.warning("No locations found within shapefile boundaries")
		print(" No locations found within shapefile boundaries. Exiting.")
		return

	if use_db_for_source_data:
		save_to_database(engine, joined, config, mode = 'shape')

	# Save to GeoJSON
	save_to_geojson(joined, config)

	# Save to CSV
	save_to_csv(joined, config)

	# Create map visualization
	create_and_save_map(shape, joined, config)


if __name__ == "__main__":
	try:
		# Setup logging first
		log_file = setup_logging()

		config = Config()
		main(config)
		print("\n✅ Process completed successfully!")

	except KeyboardInterrupt:
		print("\n\n⚠️  Operation cancelled by user.")
		logging.warning("Operation cancelled by user")
		sys.exit(0)
	except Exception as e:
		if getattr(e, 'already_logged', False):
			pass
		else:
			logging.error("Unexpected error")
			logging.error(traceback.format_exc())
			print(f"\n❌ Unexpected Error: {str(e)}")
		if 'log_file' in locals():
			print(f"\n📝 Full error details have been written to: {log_file}")
		else:
			print(f"\n📝 Check the logs directory for error details.")
		sys.exit(1)

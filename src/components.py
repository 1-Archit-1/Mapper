"""
Reusable UI components for Streamlit tabs.
Provides common widgets to avoid code duplication.
"""
import traceback
import logging
import uuid
import streamlit as st
import pandas as pd
from typing import Optional, Tuple, Dict
from src.utils import (
    create_engine_connection,
    fetch_data_from_db,
    fetch_table_columns,
    insert_data_to_db,
    insert_event_metadata,
    seed_event_exposures,
    recalculate_znet,
    parse_db_object,
    format_db_object_sql
)
from sqlalchemy import text
from src.db_config import (
    get_saved_servers,
    get_recent_databases,
    get_recent_tables,
    add_server,
    add_recent_database,
    add_recent_table,
    set_output_server,
    set_output_database
)


def get_coordinate_column_default_indexes(df: pd.DataFrame) -> Tuple[Optional[int], Optional[int]]:
    """Guess default latitude/longitude column indexes from DataFrame columns."""
    columns = df.columns.tolist()
    normalized = [str(col).strip().lower() for col in columns]

    def _guess(
        exact_patterns: list[str],
        fuzzy_tokens: list[str],
        exclude_indexes: Optional[set] = None
    ) -> Optional[int]:
        exclude_indexes = exclude_indexes or set()

        for pattern in exact_patterns:
            p = pattern.lower()
            for i, col_name in enumerate(normalized):
                if i not in exclude_indexes and col_name == p:
                    return i

        for token in fuzzy_tokens:
            t = token.lower()
            for i, col_name in enumerate(normalized):
                if i in exclude_indexes:
                    continue
                if (
                    col_name.startswith(t)
                    or col_name.endswith(t)
                    or f"_{t}" in col_name
                    or f"{t}_" in col_name
                ):
                    return i
        return None

    lat_index = _guess(
        exact_patterns=["latitude", "lat"],
        fuzzy_tokens=["latitude", "lat"]
    )
    lon_index = _guess(
        exact_patterns=["longitude", "lon", "long"],
        fuzzy_tokens=["longitude", "lon", "long"],
        exclude_indexes={lat_index} if lat_index is not None else None
    )
    return lat_index, lon_index


def data_source_selector(key_prefix: str) -> str:
    """
    Render radio button for data source selection.

    Args:
        key_prefix: Unique prefix for widget keys (e.g., 'shape' or 'raster')

    Returns:
        Selected data source string
    """
    return st.radio(
        "Select data source:",
        ["Upload CSV File", "Fetch from Database"],
        key=f'{key_prefix}_data_source',
        horizontal=True
    )

@st.cache_data(show_spinner=False)
def load_csv(csv_file) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(csv_file)

    except Exception as e:
        st.error("❌ Could not read CSV file.")
        logging.error(f"Error loading CSV: {str(e)}")
        logging.error(traceback.format_exc())
        return None

def csv_uploader(key_prefix: str, label: str = "Upload CSV with coordinates", reset_func=lambda: None) -> Optional[pd.DataFrame]:
    """
    Render CSV file uploader and return loaded DataFrame.

    Args:
        key_prefix: Unique prefix for widget keys
        label: Label text for the uploader
        reset_func: Function to reset the state

    Returns:
        DataFrame if file uploaded, None otherwise
    """
    csv_file = st.file_uploader(label, type=['csv'], key=f'{key_prefix}_csv', on_change=reset_func)
    if csv_file:
        df = load_csv(csv_file)
        if df is not None:
            st.session_state[f'{key_prefix}_active_input_df'] = df
            return df
        st.session_state[f'{key_prefix}_active_input_df'] = None
        return None
    return None


def database_connection_ui(
    key_prefix: str,
    default_server:Optional[str] = None,
    default_database: Optional[str] = None,
    show_subheader: bool = True
) -> Optional[Tuple[str, str, str]]:
    """
    Render complete database connection UI with server/database/table inputs.
    Handles saved servers, recent history, test connection, and data fetching.

    Args:
        key_prefix: Unique prefix for widget keys
        default_server: Default server value to prefill
        default_database: Default database value to prefill
        session_key: Session state key to store fetched DataFrame
        show_subheader: Whether to show the "Database Connection" subheader

    Returns:
        Tuple of (server, database, table) if connection info provided, None otherwise

    Note: Also stores server and database in session state keys:
        {session_key}_server and {session_key}_database
    """
    if show_subheader:
        st.markdown("#### 1. Database Connection")

    # Server selection
    saved_servers = get_saved_servers()
    server_col1, server_col2 = st.columns([3, 1])
    with server_col1:
        server_options = [""] + saved_servers
        default_index = 0
        if default_server and default_server in saved_servers:
            default_index = server_options.index(default_server)
        server = st.selectbox(
            "Server:",
            server_options,
            index=default_index,
            key=f'{key_prefix}_server_select',
            accept_new_options = True
        )

    with server_col2:
        st.write("")
        st.write("")
        if st.button("💾", key=f'{key_prefix}_save_server', help="Save this server"):
            if server and server not in saved_servers:
                add_server(server)
                st.toast("Server saved!", icon="💾")

    # Database selection with recent history
    recent_dbs = get_recent_databases()
    db_options = [""] + recent_dbs
    default_db_index = 0
    if default_database and default_database in recent_dbs:
        default_db_index = db_options.index(default_database)
    database = st.selectbox(
        "Database:",
        db_options,
        index=default_db_index,
        key=f'{key_prefix}_db_select',
        accept_new_options=True
    )
    recent_tables = get_recent_tables()
    table = st.selectbox(
        "Table:",
        [""] + recent_tables,
        key=f'{key_prefix}_table_select',
        accept_new_options=True
    )
    st.caption('Currently supports only Windows Auth with SQL Server')
    return server, database, table


def event_database_connection_ui(
    key_prefix: str,
    default_config: Dict,
    show_subheader: bool = True
) -> Optional[Tuple[str, str, str]]:
    """Render database connection UI specifically for event shapefile tab,
    Sets defaults to the location_shape_mapper_prod database on catdb.
    Detects standard table names in that database for easier selection."""
    saved_servers = get_saved_servers()
    server_col1, server_col2 = st.columns([3, 1])
    default_server = default_config.get('server')
    default_database = default_config.get('database')

    # Display default as well as saved servers for easier selection
    if default_server not in saved_servers:
        add_server(default_server)
        saved_servers = get_saved_servers()

    with server_col1:
        server_options = [""] + saved_servers
        default_index = 0
        if default_server and default_server in saved_servers:
            default_index = server_options.index(default_server)
        server = st.selectbox(
            "Server:",
            server_options,
            index=default_index,
            key=f'{key_prefix}_server_select',
            accept_new_options = True
        )
    with server_col2:
        st.write("")
        st.write("")
        if st.button("💾", key=f'{key_prefix}_save_server', help="Save this server"):
            if server and server not in saved_servers:
                add_server(server)
                st.toast("Server saved!", icon="💾")

    # Display default as well as recently used databases for easier selection
    recent_dbs = get_recent_databases(event_dashboard=True)
    if default_database not in recent_dbs:
        add_recent_database(default_database, event_dashboard=True)
        recent_dbs = get_recent_databases(event_dashboard=True)

    db_options = [""] + recent_dbs
    default_db_index = 0
    if default_database and default_database in recent_dbs:
        default_db_index = db_options.index(default_database)
    database = st.selectbox(
        "Database:",
        db_options,
        index=default_db_index,
        key=f'{key_prefix}_db_select',
        accept_new_options=True
    )

    #detect when database is picked
    if database:
        exposure_tables_list = detect_base_exposure_tables(server, database, table_wildcard = default_config.get('base_exposure_table_wildcard'))
        recent_tables = get_recent_tables(event_dashboard=True)
        table_options = [""] + exposure_tables_list + recent_tables
        table = st.selectbox(
            "Table:",
            table_options,
            key=f'{key_prefix}_table_select',
            accept_new_options=True
        )
        st.caption('Currently supports only Windows Auth with SQL Server')
        return server, database, table

def detect_base_exposure_tables(server: str, database: str, table_wildcard: str) -> list[str]:
    """Detect tables in the database that match common exposure table naming patterns."""
    try:
        engine = create_engine_connection(server, database)
    except Exception as e:
        logging.error(f"Error creating engine for table detection: {str(e)}")
        logging.error(traceback.format_exc())
        st.error(f"❌ Error connecting to database {database} on server {server} for table detection: {str(e)}")
        return []

    try:
        with engine.connect() as conn:
            query = text(f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '{table_wildcard}%'")
            result = conn.execute(query)
            tables = [row[0] for row in result]
        engine.dispose()
        return tables
    except Exception as e:
        logging.error(f"Error detecting tables: {str(e)}")
        logging.error(traceback.format_exc())
        st.error(f"❌ Error detecting tables: {str(e)}")
        return []

def database_test_fetch_ui(
    server: str,
    database: str,
    table: str,
    key_prefix: str,
    reset_func=lambda: None
):
    # Test connection and fetch data
    if server and database and table:
        col_test, col_fetch_all, col_select = st.columns([2, 3, 3])
        progress_slot = st.empty()  # shared: spinner + live row count during fetch
        status_slot = st.empty()    # shared: final success/error message

        with col_test:
            if st.button("🔌 Test", key=f'{key_prefix}_test_conn', width='stretch'):
                with st.spinner("Testing connection..."):
                    try:
                        engine = create_engine_connection(server, database)
                        with engine.connect() as conn:
                            pass
                        status_slot.success("Connection successful!")
                        engine.dispose()
                    except Exception as e:
                        status_slot.error(f"❌ Connection failed: {str(e)}")

        with col_fetch_all:
            if st.button("📥 Fetch All", key=f'{key_prefix}_fetch_data', width='stretch'):
                st.session_state.pop(f'{key_prefix}_col_picker_cols', None)
                st.session_state.pop(f'{key_prefix}_col_picker_select', None)
                status_slot.empty()
                try:
                    with progress_slot.container():
                        with st.spinner("Fetching data..."):
                            progress_text = st.empty()
                            engine = create_engine_connection(server, database)
                            table_obj = parse_db_object(table, default_schema=None)
                            table_label = table_obj.schema_table
                            df = fetch_data_from_db(
                                engine, table_label,
                                progress_callback=lambda n: progress_text.caption(f"Fetched {n:,} rows...")
                            )
                    add_recent_database(database)
                    add_recent_table(table_label)
                    reset_func()
                    st.session_state[f'{key_prefix}_active_input_df'] = df
                    st.session_state[f'{key_prefix}_db_server'] = server
                    st.session_state[f'{key_prefix}_db_database'] = database
                    st.session_state[f'{key_prefix}_db_table'] = table_label
                    st.session_state[f'engine_{server}_{database}'] = engine
                    status_slot.success(f"Fetched {len(df):,} rows")
                except Exception as e:
                    if getattr(e, 'already_logged', False):
                        pass
                    else:
                        logging.error(f"Error fetching data: {str(e)}")
                        logging.error(traceback.format_exc())
                    status_slot.error(f"❌ Error: {str(e)}")
                    if 'engine' in locals():
                        engine.dispose()

        with col_select:
            if st.button("🔎 Select Cols", key=f'{key_prefix}_select_cols_btn', width='stretch'):
                status_slot.empty()
                try:
                    with progress_slot.container():
                        with st.spinner("Loading column names..."):
                            engine = create_engine_connection(server, database)
                            table_obj = parse_db_object(table, default_schema=None)
                            table_label = table_obj.schema_table
                            cols = fetch_table_columns(engine, table_label)
                            st.session_state[f'{key_prefix}_col_picker_cols'] = cols
                            engine.dispose()
                except Exception as e:
                    status_slot.error(f"❌ Error loading columns: {str(e)}")

        if f'{key_prefix}_col_picker_cols' in st.session_state:
            available_cols = st.session_state[f'{key_prefix}_col_picker_cols']
            multiselect_slot = st.empty()
            button_slot = st.empty()
            status_slot.caption("⚠️ Ensure you include your Latitude and Longitude columns.")
            multiselect_slot.multiselect(
                "Columns to fetch:",
                options=available_cols,
                default=available_cols,
                key=f'{key_prefix}_col_picker_select'
            )
            selected_cols = st.session_state.get(f'{key_prefix}_col_picker_select', available_cols)
            clicked = button_slot.button("📥 Fetch Selected Columns", key=f'{key_prefix}_fetch_selected', disabled=not selected_cols)
            if clicked:
                multiselect_slot.empty()
                button_slot.empty()
                status_slot.empty()
                st.session_state.pop(f'{key_prefix}_col_picker_cols', None)
                st.session_state.pop(f'{key_prefix}_col_picker_select', None)
                try:
                    with progress_slot.container():
                        with st.spinner("Fetching data..."):
                            progress_text = st.empty()
                            engine = create_engine_connection(server, database)
                            table_obj = parse_db_object(table, default_schema=None)
                            table_label = table_obj.schema_table
                            df = fetch_data_from_db(
                                engine, table_label, required_columns=selected_cols,
                                progress_callback=lambda n: progress_text.caption(f"Fetched {n:,} rows...")
                            )
                    add_recent_database(database)
                    add_recent_table(table_label)
                    reset_func()
                    st.session_state[f'{key_prefix}_active_input_df'] = df
                    st.session_state[f'{key_prefix}_db_server'] = server
                    st.session_state[f'{key_prefix}_db_database'] = database
                    st.session_state[f'{key_prefix}_db_table'] = table_label
                    st.session_state[f'engine_{server}_{database}'] = engine
                    status_slot.success(f"Fetched {len(df):,} rows with {len(selected_cols)} columns")
                except Exception as e:
                    if getattr(e, 'already_logged', False):
                        pass
                    else:
                        logging.error(f"Error fetching data: {str(e)}")
                        logging.error(traceback.format_exc())
                    status_slot.error(f"❌ Error: {str(e)}")
                    if 'engine' in locals():
                        engine.dispose()

def event_database_test_fetch_ui(
    server: str,
    database: str,
    table: str,
    required_columns: list[str],
    reset_func=lambda: None
):
    # Test connection and fetch data
    col_test, col_fetch = st.columns(2)

    with col_test:
        if st.button("🔌 Test Connection", key=f'event_shape_test_conn', width='stretch'):
            with st.spinner("Testing connection..."):
                try:
                    engine = create_engine_connection(server, database)
                    with engine.connect() as conn:
                        pass  # Just test the connection
                    st.success("Connection successful!")
                except Exception as e:
                    st.error(f"❌ Connection failed: {str(e)}")
                finally:
                    if 'engine' in locals():
                        engine.dispose()

    with col_fetch:
        if st.button("📥 Fetch Data from Table", key=f'event_shape_fetch_data', width='stretch'):
            with st.spinner("Fetching data from database..."):
                progress_text = st.empty()
                try:
                    engine = create_engine_connection(server, database)
                    table_obj = parse_db_object(table, default_schema=None)
                    table_label = table_obj.schema_table
                    df = fetch_data_from_db(
                        engine, table_label, required_columns,
                        progress_callback=lambda n: progress_text.caption(f"Fetched {n:,} rows...")
                    )
                    progress_text.empty()

                    reset_func()
                    # Store in session state (including server/db info)
                    st.session_state[f'event_shape_active_input_df'] = df
                    st.session_state['event_shape_db_table'] = table_label
                    st.session_state['event_shape_db_server'] = server
                    st.session_state['event_shape_db_database'] = database

                    add_recent_database(database, event_dashboard=True)
                    add_recent_table(table_label, event_dashboard=True)

                    st.success(f"Fetched {len(df):,} rows")

                except Exception as e:
                    if getattr(e, 'already_logged', False):
                        pass
                    else:
                        logging.error(f"Error fetching data: {str(e)}")
                        logging.error(traceback.format_exc())
                    st.error(f"❌ Error: {str(e)}")
                finally:
                    if 'engine' in locals():
                        engine.dispose()

def column_selector(df: pd.DataFrame, key_prefix: str,
                   include_pkey: bool = False) -> Dict[str, any]:
    """
    Render column selectors for latitude, longitude, and optionally primary keys.

    Args:
        df: DataFrame to select columns from
        key_prefix: Unique prefix for widget keys
        include_pkey: Whether to include primary key selection

    Returns:
        Dictionary with keys: 'lat_col', 'lon_col', 'use_pkey', 'pkey_cols'
    """
    result = {}
    columns = df.columns.tolist()
    lat_index, lon_index = get_coordinate_column_default_indexes(df)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        result['lat_col'] = st.selectbox(
            "Latitude column",
            columns,
            key=f'{key_prefix}_lat',
            index=lat_index
        )

    with col2:
        result['lon_col'] = st.selectbox(
            "Longitude column",
            columns,
            key=f'{key_prefix}_lon',
            index=lon_index
        )

    if include_pkey:
        result['use_pkey'] = st.checkbox(
            "Use primary key column(s)?",
            key=f'{key_prefix}_pkey',
            help="When enabled, only the selected key column(s) and coordinates are kept, and duplicate rows sharing the same key are removed before processing."
        )
        result['pkey_cols'] = []
        if result['use_pkey']:
            result['pkey_cols'] = st.multiselect(
                "Select primary key column(s)",
                #all cols except lat/lon
                df.columns[~df.columns.isin([result['lat_col'], result['lon_col']])].tolist(),
                key=f'{key_prefix}_pkey_select'
            )
    else:
        result['use_pkey'] = False
        result['pkey_cols'] = []

    return result

def data_preview(df: pd.DataFrame, num_rows: int = 10):
    """
    Display a preview of the DataFrame with row count.

    Args:
        df: DataFrame to preview
        num_rows: Number of rows to display (default: 10)
    """
    st.markdown("#### Data Preview")
    st.dataframe(df.head(num_rows), width='stretch')
    st.caption(f"Total rows: {len(df):,}")


def results_display(
    display_df: pd.DataFrame,

):
    """
    Display results with download and save to database options.

    Args:
        display_df: Results to be displayed
        output_df: Results for CSV/DB output
        output_filename: Name for downloaded CSV file
        key_prefix: Unique prefix for widget keys
        input_server: Server used for input (if fetched from DB) - used for prefilling
        input_database: Database used for input (if fetched from DB) - used for prefilling
        session_key: Session state key for database operations
    """
    st.dataframe(display_df.head(20), width='stretch')



@st.fragment
def save_outputs_ui(
    output_df: pd.DataFrame,
    output_filename: str,
    key_prefix: str,
    input_server: Optional[str] = None,
    input_database: Optional[str] = None
):
    csv_cache_key = f"{key_prefix}_csv_output"
    csv_source_id_key = f"{key_prefix}_csv_source_id"
    csv_selected_cols_key = f"{key_prefix}_csv_selected_cols"
    selected_columns_key = f"{key_prefix}_save_columns"

    columns = output_df.columns.tolist()
    previous_selection = st.session_state.get(selected_columns_key)
    if not isinstance(previous_selection, list) or any(col not in columns for col in previous_selection):
        st.session_state[selected_columns_key] = columns.copy()

    selected_columns = st.multiselect(
        "Columns to save",
        options=columns,
        default=columns,
        key=selected_columns_key,
        help="Choose which columns should be included in CSV download and database save."
    )

    if selected_columns:
        selected_output_df = output_df[selected_columns]
        st.caption(f"Saving {len(selected_columns)} of {len(columns)} columns")
    else:
        selected_output_df = output_df.iloc[:, 0:0]
        st.warning("Select at least one column to enable CSV download and database save.")

    # Streamlit reruns this fragment on each DB widget interaction; cache CSV
    # serialization to avoid re-encoding large result sets repeatedly.
    source_id = id(output_df)
    selected_columns_tuple = tuple(selected_columns)
    if (
        st.session_state.get(csv_source_id_key) != source_id
        or st.session_state.get(csv_selected_cols_key) != selected_columns_tuple
    ):
        st.session_state[csv_cache_key] = selected_output_df.to_csv(index=False)
        st.session_state[csv_source_id_key] = source_id
        st.session_state[csv_selected_cols_key] = selected_columns_tuple

    csv_output = st.session_state[csv_cache_key]

    col1, col2 = st.columns(2)
    # Download CSV button
    with col1:
        st.download_button(
            label="📥 Download Results CSV",
            data=csv_output,
            file_name=output_filename,
            mime="text/csv",
            disabled=not bool(selected_columns),
            width='stretch'
        )

    # Save to database option
    with col2:
        with st.expander("💾 Save Results to DB Table", expanded=False):
            # Reuse database UI component with prefilled values
            output_server, output_database, output_table = database_connection_ui(
                key_prefix=f'{key_prefix}_output',
                default_server=input_server,
                default_database=input_database,
                show_subheader=False
            )

            # Save button
            if st.button(
                "📤 Save to Database",
                key=f'{key_prefix}_save_db_btn',
                disabled=not (output_server and output_database and output_table and selected_columns),
                width='stretch'
            ):

                with st.spinner(f"Saving to {output_server}.{output_database}.{output_table}..."):
                    try:
                        # Check if we can reuse existing engine from session state
                        engine_key = f'engine_{input_server}_{input_database}'
                        reuse_engine = (
                            input_server == output_server and
                            input_database == output_database and
                            engine_key in st.session_state
                        )
                        inserted = False
                        if reuse_engine:
                            st.caption("Reusing existing database connection")
                            engine = st.session_state[engine_key]

                            try:
                                insert_data_to_db(engine, selected_output_df, output_table)
                                inserted = True
                            except Exception as e:
                                st.warning(f"Existing connection failed, trying new connection: {str(e)}")
                                engine.dispose()  # Dispose the old engine and create a new one

                        if not inserted:
                            engine = create_engine_connection(output_server, output_database)
                            st.session_state[f'engine_{output_server}_{output_database}'] = engine
                            try:
                                insert_data_to_db(engine, selected_output_df, output_table)
                            except Exception as e:
                                st.error(f"Error inserting data: {str(e)}")
                                engine.dispose()
                                del st.session_state[f'engine_{output_server}_{output_database}']
                                return

                        add_recent_database(output_database)
                        output_table_obj = parse_db_object(output_table, default_schema=None)
                        add_recent_table(output_table_obj.schema_table)

                        # Save preferences (Not currently used for prefilling, but could be in the future)
                        # Currently recent database/tables are used
                        set_output_server(output_server)
                        set_output_database(output_database)

                        st.success(
                            f"Successfully saved {len(selected_output_df):,} rows and "
                            f"{len(selected_columns):,} columns to {output_table}!"
                        )

                    except Exception as e:
                        if getattr(e, 'already_logged', False):
                            pass
                        else:
                            logging.error(f"Error saving to database: {str(e)}")
                            logging.error(traceback.format_exc())
                        st.error(f"❌ Error saving to database: {str(e)}")
            if not selected_columns:
                st.caption("⚠️ Select at least one column to enable save")
            elif not (output_server and output_database and output_table):
                st.caption("⚠️ Please fill in all fields to enable save")
            st.info("With great power comes great responsibility. \n You have the ability to overwrite existing tables. Please double-check your output table name to avoid data loss.")


def _rollback_event_registry(engine, event_id: int, default_config: Dict):
    """Remove an Event_Registry row when a later pipeline step fails."""
    try:
        event_table = default_config.get('event_table', 'Event_Registry')
        table_obj = parse_db_object(event_table, default_schema=None)
        table_ref = format_db_object_sql(table_obj)
        with engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
            conn.execute(
                text(f"DELETE FROM {table_ref} WHERE event_id = :eid"),
                {"eid": event_id}
            )
    except Exception as rollback_err:
        logging.error(f"Rollback failed for event_id={event_id}: {rollback_err}")


def _rollback_raw_table(engine, table_name: str):
    """Drop the raw intersection table created during a failed save."""
    try:
        table_obj = parse_db_object(table_name, default_schema=None)
        table_ref = format_db_object_sql(table_obj)
        with engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_ref}"))
    except Exception as rollback_err:
        logging.error(f"Failed to drop raw table '{table_name}': {rollback_err}")


def event_dashboard_save_outputs_ui(

    output_df: pd.DataFrame,
    key_prefix: str,
    default_config: Dict,
    detected_location_details_table: Optional[str] = None
):
    # form for saving outputs with prefilled values and detected table suggestions
    st.markdown("#### Save Results")

    error_key = f'{key_prefix}_save_error'
    if error_key not in st.session_state:
        st.session_state[error_key] = None

    event_name = st.text_input(
        "Event Name",
        key=f'{key_prefix}_event_name',
        placeholder="MMM_DD_EventType_Location",
        help="Provide a name for the event"
    )
    output_table = st.text_input(
        "Raw Table name",
        key=f'{key_prefix}_raw_table_name',
        placeholder="Recommended: locations_EventName",
        help = "Provide the name of the raw table where the data will be stored"
    )

    col_left, col_right = st.columns(2)
    with col_left:
        affected_location = st.text_input(
            "Affected Location",
            key=f'{key_prefix}_affected_location',
            placeholder="Central USA",
            help="Provide a description of the affected location (e.g., 'Midwest', 'Southern USA')"
        )
        event_type = st.selectbox(
            "Event Type",
            options = ["Assessment Only", "Hailstorm"],
            key=f'{key_prefix}_event_type'
        )
    with col_right:
        event_type_label = st.text_input(
            "Event Type Label",
            key=f'{key_prefix}_event_type_label',
            placeholder="Hail Intensity/Tornado",
            help="Provide a label for the event type (e.g., 'Flood', 'Tornado', 'Hail/Tornado')."
        )
        event_date = st.date_input(
            "Event Date",
            key=f'{key_prefix}_event_date',
            help="Select the date of the event"
        )

    col_left2, col_right2 = st.columns(2)
    with col_left2:
        location_details_table = st.text_input(
            "Location Details Table",
            value=detected_location_details_table or "",
            key=f'{key_prefix}_location_details_table',
            placeholder="GAM_ZMaster_Loc_2025Q4",
            help="Auto-detected from selected base table. Override if needed."
        )
    with col_right2:
        peril_metric_set = st.radio(
            "Select Peril",
            options=["SC", "EQ", "FL", "WT", "WS"],
            key=f'{key_prefix}_peril_select',
            horizontal=True,
        )

    output_server = default_config.get('server')
    output_database = default_config.get('database')

    # Clear stale errors on rerun (will be re-set if save fails)
    st.session_state[error_key] = None

    if st.button(
        "📤 Save to Event Dashboard Database",
        key=f'{key_prefix}_save_db_btn',
        disabled=not (
            output_server and
            output_database and
            output_table and
            event_name and
            affected_location and
            event_type and
            event_type_label and
            event_date and
            location_details_table
        ),
        width='stretch'
    ):
        progress = st.progress(0, text="Starting save...")
        event_id = None

        with st.spinner(f"Saving to {output_server}.{output_database}.{output_table}..."):
            try:
                progress.progress(25, text="Saving raw table...")
                output_table_obj = parse_db_object(output_table, default_schema=None)
                engine = create_engine_connection(output_server, output_database)
                insert_data_to_db(
                    engine,
                    output_df,
                    output_table_obj.schema_table,
                )
            except Exception as e:
                st.session_state[error_key] = f"Error inserting data: {str(e)}"
                progress.progress(100, text="Save failed.")
                st.error(st.session_state[error_key])
                if 'engine' in locals():
                    engine.dispose()
                return
        with st.spinner("Inserting event metadata in event registry..."):
            try:
                progress.progress(50, text="Inserting event metadata...")
                event_table = default_config.get('event_table')
                event_id = insert_event_metadata(
                    engine,
                    event_table=event_table,
                    event_name=event_name,
                    event_date=event_date,
                    affected_location=affected_location,
                    event_type=event_type,
                    event_type_label=event_type_label,
                    peril_metric_set=peril_metric_set,
                    raw_table_name=output_table_obj.bare_table
                )
            except Exception as e:
                st.session_state[error_key] = f"Error inserting event metadata: {str(e)}"
                _rollback_raw_table(engine, output_table)
                progress.progress(100, text="Save failed.")
                st.error(st.session_state[error_key])
                return
        with st.spinner("Seeding event exposures..."):
            try:
                progress.progress(75, text="Seeding event exposures...")
                seed_event_exposures(
                    engine,
                    event_id=event_id,
                    location_details_table=location_details_table
                )
            except Exception as e:
                # Rollback: remove the orphaned Event_Registry row and raw table
                _rollback_event_registry(engine, event_id, default_config)
                _rollback_raw_table(engine, output_table)
                st.session_state[error_key] = (
                    f"Seeding failed — event registry and raw table have been rolled back (event_id={event_id}). "
                    f"You can retry. Error: {str(e)}"
                )
                progress.progress(100, text="Save failed — rolled back.")
                st.error(st.session_state[error_key])
                return
        with st.spinner("Recalculating ZNet..."):
            try:
                progress.progress(90, text="Recalculating ZNet...")
                recalculate_znet(engine, event_id=event_id)
            except Exception as e:
                st.session_state[error_key] = (
                    f"Event saved and exposures seeded (event_id={event_id}), but ZNet recalculation failed. "
                    f"Run manually: EXEC [dbo].[usp_Recalculate_ZNet] @event_id = {event_id}; "
                    f"Error: {str(e)}"
                )
                progress.progress(100, text="Save partial — ZNet recalculation failed.")
                st.error(st.session_state[error_key])
                return

        progress.progress(100, text="Save complete.")
        st.success("Save complete. Event data, metadata, exposures, and ZNet updates are finished.")

    # Show error if present (persists across reruns until user interacts with form)
    if st.session_state.get(error_key):
        st.error(st.session_state[error_key])





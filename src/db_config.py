"""
Database configuration management for saved connections and recent items.
Handles reading/writing db_connections.json file.
"""
import json
from pathlib import Path
from typing import List, Dict
from src.utils.helpers import parse_db_object

DEFAULTS_FILE = Path(__file__).parent.parent / "db_connections.json"  # Static defaults
USER_CONFIG_FILE = Path(__file__).parent.parent / "db_connections.user.json"  # User-specific state (saved servers, recent items, output preferences)
USER_TEMPLATE_FILE = Path(__file__).parent.parent / "db_connections.user.template.json"  # Template for user state

USER_STATE_KEYS = {
    "saved_servers",
    "recent_databases",
    "recent_databases_event_dashboard",
    "recent_tables",
    "recent_tables_event_dashboard",
    "output_server",
    "output_database"
}

EVENT_DASHBOARD_REQUIRED_KEYS = {
    "event_table",
    "base_exposure_table_wildcard",
    "base_location_details_table",
    "base_location_details_table_wildcard",
    "required_columns",
    "generated_columns"
}

def _load_defaults() -> Dict:
    """Load static defaults from db_connections.json."""
    if not DEFAULTS_FILE.exists():
        print("Warning: db_connections.json defaults file is missing.")
        return {}

    try:
        with open(DEFAULTS_FILE, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Warning: Could not load db_connections.json: {e}")
        return {}


def _load_user_template() -> Dict:
    """Load the user state template for initialization and defaults."""
    if not USER_TEMPLATE_FILE.exists():
        raise FileNotFoundError("db_connections.user.template.json is missing")

    with open(USER_TEMPLATE_FILE, 'r') as f:
        return json.load(f)


def _ensure_user_state_file():
    """Create db_connections.user.json from the template if missing."""
    if USER_CONFIG_FILE.exists():
        return

    template = _load_user_template()
    _save_user_state(template)


def _normalize_database_name(name: str) -> str:
    """Normalize database name by stripping surrounding brackets."""
    return str(name).strip().strip('[]')


def _normalize_table_name(name: str) -> str:
    """Normalize table name to schema.table when possible."""
    try:
        table_obj = parse_db_object(name, default_schema=None)
        return table_obj.schema_table
    except Exception:
        return str(name).strip()


def get_event_dashboard_default_config() -> Dict:
    """Get default config values for event dashboard."""
    config = _load_defaults()
    defaults = config.get("event_dashboard_default")
    if not defaults:
        raise FileNotFoundError("event_dashboard_default is missing from db_connections.json")

    missing_keys = sorted([key for key in EVENT_DASHBOARD_REQUIRED_KEYS if key not in defaults])
    if missing_keys:
        raise KeyError(f"event_dashboard_default missing keys: {', '.join(missing_keys)}")

    if not isinstance(defaults.get("required_columns"), list):
        raise TypeError("event_dashboard_default.required_columns must be a list")
    if not isinstance(defaults.get("generated_columns"), list):
        raise TypeError("event_dashboard_default.generated_columns must be a list")

    return defaults

def _save_defaults(config: Dict):
    """Save defaults configuration to JSON file."""
    try:
        with open(DEFAULTS_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save db_connections.json: {e}")


def _load_user_state() -> Dict:
    """Load user state, fill missing keys from template, and normalize values."""
    _ensure_user_state_file()
    template = _load_user_template()
    try:
        with open(USER_CONFIG_FILE, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load db_connections.user.json: {e}")
        config = {}

    state = {}
    for key in USER_STATE_KEYS:
        if key in config:
            state[key] = config[key]
        else:
            state[key] = template.get(key)

    return state


def _save_user_state(state: Dict):
    """Persist user state to db_connections.user.json."""
    template = _load_user_template()
    payload = {}
    for key in USER_STATE_KEYS:
        if key in state:
            payload[key] = state[key]
        else:
            payload[key] = template.get(key)
    try:
        with open(USER_CONFIG_FILE, 'w') as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save db_connections.user.json: {e}")


def save_db_config(config: Dict):
    """Save user-state database configuration to JSON file."""
    _save_user_state(config)

def add_server(server_name: str):
    """Add a server to saved servers list (no duplicates)."""
    if not server_name or not server_name.strip():
        return

    config = _load_user_state()
    server_name = server_name.strip()

    if server_name not in config["saved_servers"]:
        config["saved_servers"].append(server_name)
        save_db_config(config)

def remove_server(server_name: str):
    """Remove a server from saved servers list."""
    config = _load_user_state()
    if server_name in config["saved_servers"]:
        config["saved_servers"].remove(server_name)
        save_db_config(config)

def add_recent_database(database_name: str, max_items: int = 10, event_dashboard: bool = False):
    """Add database to recent list, keeping only last N items."""
    if not database_name or not database_name.strip():
        return

    config = _load_user_state()
    database_name = _normalize_database_name(database_name)

    key = "recent_databases_event_dashboard" if event_dashboard else "recent_databases"

    # Remove if already exists (will re-add at front)
    if database_name in config[key]:
        config[key].remove(database_name)

    # Add to front
    config[key].insert(0, database_name)

    # Keep only max_items
    config[key] = config[key][:max_items]

    save_db_config(config)

def add_recent_table(table_name: str, max_items: int = 10, event_dashboard: bool = False):
    """Add table to recent list, keeping only last N items."""
    if not table_name or not table_name.strip():
        return

    config = _load_user_state()
    table_name = _normalize_table_name(table_name)

    key = "recent_tables_event_dashboard" if event_dashboard else "recent_tables"

    # Remove if already exists (will re-add at front)
    if table_name in config[key]:
        config[key].remove(table_name)

    # Add to front
    config[key].insert(0, table_name)

    # Keep only max_items
    config[key] = config[key][:max_items]

    save_db_config(config)

def get_saved_servers() -> List[str]:
    """Get list of saved server names."""
    config = _load_user_state()
    return config.get("saved_servers", [])

def get_recent_databases(event_dashboard: bool = False) -> List[str]:
    """Get list of recent database names."""
    config = _load_user_state()
    key = "recent_databases_event_dashboard" if event_dashboard else "recent_databases"
    return config.get(key, [])

def get_recent_tables(event_dashboard: bool = False) -> List[str]:
    """Get list of recent table names."""
    config = _load_user_state()
    key = "recent_tables_event_dashboard" if event_dashboard else "recent_tables"
    return config.get(key, [])

def get_output_server() -> str:
    """Get last used output server."""
    config = _load_user_state()
    return config.get("output_server", "")

def get_output_database() -> str:
    """Get last used output database."""
    config = _load_user_state()
    return config.get("output_database", "")

def set_output_server(server_name: str):
    """Save output server preference."""
    if not server_name or not server_name.strip():
        return

    config = _load_user_state()
    config["output_server"] = server_name.strip()
    save_db_config(config)

def set_output_database(database_name: str):
    """Save output database preference."""
    if not database_name or not database_name.strip():
        return

    config = _load_user_state()
    config["output_database"] = _normalize_database_name(database_name)
    save_db_config(config)

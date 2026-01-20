"""Configuration loader for TIS Artifact Fetcher.

This module loads user-configurable settings from config.json and provides
constants and computed values for the application.

All other modules should import from this file.
"""

from pathlib import Path
from typing import Dict, List, Optional
import json

# =============================================================================
# LOAD CONFIGURATION FROM JSON
# =============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    """Load configuration from JSON file."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

_config = _load_config()

# =============================================================================
# DEBUG SETTINGS (from config.json)
# =============================================================================

DEBUG_MODE = _config["debug"]["debug_mode"]
SLOW_MODE = _config["debug"]["slow_mode"]
API_WAIT_TIME = _config["debug"]["api_wait_time"]
LOG_LEVEL = _config["debug"].get("log_level", "INFO").upper()

# =============================================================================
# API CONFIGURATION (from config.json)
# =============================================================================

TIS_URL = _config["api"]["tis_url"]
TIS_LINK_TEMPLATE = _config["api"]["tis_link_template"]
API_TIMEOUT = (_config["api"]["timeout_connect"], _config["api"]["timeout_read"])
API_MAX_RETRIES = _config["api"]["max_retries"]
API_BACKOFF_FACTOR = _config["api"]["backoff_factor"]
API_RETRY_STATUS_CODES = _config["api"]["retry_status_codes"]
VW_XCU_PROJECT_ID = _config["api"]["root_project_id"]

# =============================================================================
# OPTIMIZATION SETTINGS (from config.json)
# =============================================================================

CONCURRENT_REQUESTS = _config["optimization"]["concurrent_requests"]
CHILDREN_LEVEL = _config["optimization"]["children_level"]
UNLIMITED_FALLBACK_DEPTH = _config["optimization"]["unlimited_fallback_depth"]
RATE_LIMIT_DELAY = _config["optimization"]["rate_limit_delay"]
CACHE_MAX_SIZE = _config["optimization"]["cache_max_size"]
ADAPTIVE_TIMEOUT_THRESHOLD = _config["optimization"]["adaptive_timeout_threshold"]
MIN_CHILDREN_LEVEL = _config["optimization"]["min_children_level"]
DEPTH_REDUCTION_STEP = _config["optimization"]["depth_reduction_step"]
MAX_RETRIES_PER_COMPONENT = _config["optimization"]["max_retries_per_component"]
RETRY_BACKOFF_SECONDS = _config["optimization"]["retry_backoff_seconds"]
FINAL_TIMEOUT_SECONDS = _config["optimization"]["final_timeout_seconds"]

# =============================================================================
# BRANCH PRUNING (from config.json)
# =============================================================================

INCLUDE_PROJECTS = _config["branch_pruning"].get("include_projects", [])
INCLUDE_SOFTWARE_LINES = _config["branch_pruning"].get("include_software_lines", [])
SKIP_PROJECTS = _config["branch_pruning"].get("skip_projects", [])

_skip_folders = _config["branch_pruning"]["skip_folders"]
_skip_patterns = _config["branch_pruning"]["skip_patterns"]
SKIP_FOLDER_PATTERNS = [f'^{folder}$' for folder in _skip_folders] + _skip_patterns

# =============================================================================
# ARTIFACT FILTER SETTINGS (from config.json)
# =============================================================================

def _normalize_to_list(value):
    """Convert single value to list, keep None as None, keep list as list."""
    if value is None:
        return None
    if isinstance(value, list):
        return value if value else None
    return [value]

COMPONENT_TYPE_FILTER = _normalize_to_list(_config["artifact_filters"].get("component_type"))
COMPONENT_NAME_FILTER = _normalize_to_list(_config["artifact_filters"].get("component_name"))
COMPONENT_GRP_FILTER = _config["artifact_filters"].get("component_grp")
LIFE_CYCLE_STATUS_FILTER = _config["artifact_filters"].get("life_cycle_status")
SKIP_DELETED_ARTIFACTS = _config["artifact_filters"].get("skip_deleted", True)

# =============================================================================
# OUTPUT SETTINGS
# =============================================================================

def get_json_prefix(component_name: str = None) -> str:
    """Get JSON output prefix based on component_name."""
    if component_name:
        return f"{component_name.lower()}_artifacts"
    # Default to first component_name in filter if available
    if COMPONENT_NAME_FILTER and len(COMPONENT_NAME_FILTER) > 0:
        return f"{COMPONENT_NAME_FILTER[0].lower()}_artifacts"
    return "artifacts"

def get_latest_json_prefix(component_name: str = None) -> str:
    """Get latest JSON output prefix based on component_name."""
    return f"latest_{get_json_prefix(component_name)}"

# =============================================================================
# DISPLAY SETTINGS (from config.json)
# =============================================================================

DATE_DISPLAY_FORMAT = _config.get("display", {}).get("date_format", "%d-%m-%Y %H:%M:%S")

# =============================================================================
# NAMING CONVENTION SETTINGS (from config.json)
# =============================================================================

NAMING_CONVENTION_ENABLED = _config.get("naming_convention", {}).get("enabled", False)
NAMING_CONVENTION_PATTERNS = _config.get("naming_convention", {}).get("patterns", {})

# =============================================================================
# PATH CONVENTION SETTINGS (from config.json)
# =============================================================================

PATH_CONVENTION_ENABLED = _config.get("path_convention", {}).get("enabled", False)
PATH_CONVENTION_CONFIG = _config.get("path_convention", {})

PATH_CONVENTIONS: Dict[str, Dict] = {}
for key, value in PATH_CONVENTION_CONFIG.items():
    if key.startswith('_') or key == 'enabled' or not isinstance(value, dict):
        continue
    PATH_CONVENTIONS[key] = value

# =============================================================================
# COMPUTED VALUES
# =============================================================================

APP_TITLE = "TIS Artifact Fetcher"
APP_VERSION = "2.0.0"

PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CURRENT_RUN_DIR: Optional[Path] = None

OUTPUT_DIR.mkdir(exist_ok=True)

# =============================================================================
# VALIDATION SETTINGS (from config.json)
# =============================================================================

GENERATE_VALIDATION_REPORT = _config.get("validation", {}).get("generate_validation_report", True)
TIS_LINK_TEMPLATE = _config.get("api", {}).get("tis_link_template", "https://rb-ps-tis-dashboard.bosch.com/?gotoCompInstanceId={}")

# =============================================================================
# VERSION PARSING PATTERNS
# =============================================================================

VEMOX_SVN_PATTERN = r'^vemox(?![._]).+'
VEMOX_CONAN_PATTERN = r"VeMoX/(\d+(\.\d+)*?)@VeMoX_classic/release#[a-f0-9]+"
VEMOX_SEARCH_PATH = "mdl/Simulink_VeMoX/src"

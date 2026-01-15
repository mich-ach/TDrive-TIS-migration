"""Configuration loader for TIS Artifact extraction and mapping.

This module loads user-configurable settings from config.json and provides
constants and computed values for the application.

All other modules should import from this file.
"""

from pathlib import Path
from typing import Optional
import json
import os

# =============================================================================
# LOAD CONFIGURATION FROM JSON
# =============================================================================

# Determine script and config paths
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    """Load configuration from JSON file."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# Load the configuration
_config = _load_config()

# =============================================================================
# WORKFLOW SETTINGS (from config.json)
# =============================================================================

DEFAULT_EXCEL_FILE = _config["workflow"]["default_excel_file"]
AUTO_OPEN_REPORT = _config["workflow"]["auto_open_report"]
GENERATE_VALIDATION_REPORT = _config["workflow"]["generate_validation_report"]
OPEN_ARTIFACT_VIEWER = _config["workflow"].get("open_artifact_viewer", False)

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

# Include lists (empty = include all, exact match)
INCLUDE_PROJECTS = _config["branch_pruning"].get("include_projects", [])
INCLUDE_SOFTWARE_LINES = _config["branch_pruning"].get("include_software_lines", [])

# Projects to skip entirely (by exact name)
SKIP_PROJECTS = _config["branch_pruning"].get("skip_projects", [])

# Convert simple folder names to regex patterns
_skip_folders = _config["branch_pruning"]["skip_folders"]
_skip_patterns = _config["branch_pruning"]["skip_patterns"]

SKIP_FOLDER_PATTERNS = [f'^{folder}$' for folder in _skip_folders] + _skip_patterns

# Root project ID for TIS API (moved from tis_project to api section)
VW_XCU_PROJECT_ID = _config["api"]["root_project_id"]

# =============================================================================
# ARTIFACT FILTER SETTINGS (from config.json)
# =============================================================================

def _normalize_to_list(value):
    """Convert single value to list, keep None as None, keep list as list."""
    if value is None:
        return None
    if isinstance(value, list):
        return value if value else None  # Empty list = disabled
    return [value]  # Single string -> list

# Values for matching artifact components (None/null or empty list disables the filter)
# Can be single string or list of allowed values
COMPONENT_TYPE_FILTER = _normalize_to_list(_config["artifact_filters"].get("component_type"))
COMPONENT_NAME_FILTER = _normalize_to_list(_config["artifact_filters"].get("component_name"))
COMPONENT_GRP_FILTER = _config["artifact_filters"].get("component_grp")  # Keep as single value
# List of allowed lifeCycleStatus values (None/null or empty list disables the filter)
LIFE_CYCLE_STATUS_FILTER = _config["artifact_filters"].get("life_cycle_status")
# Skip artifacts that have been deleted (deletion date has passed)
SKIP_DELETED_ARTIFACTS = _config["artifact_filters"].get("skip_deleted", True)

# =============================================================================
# OUTPUT SETTINGS (from config.json)
# =============================================================================

JSON_OUTPUT_PREFIX = _config["output"]["json_prefix"]
LATEST_JSON_PREFIX = _config["output"]["latest_json_prefix"]
EXCEL_OUTPUT_PREFIX = _config["output"]["excel_prefix"]

# =============================================================================
# DISPLAY SETTINGS (from config.json)
# =============================================================================

# Date format for displaying dates in GUI and reports
# Uses Python strftime format codes: %d=day, %m=month, %Y=year, %H=hour, %M=minute, %S=second
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
LABCAR_PLATFORMS = PATH_CONVENTION_CONFIG.get("labcar_platforms", ["VME", "PCIe"])

# Expected structure and model subfolders per component_name
PATH_EXPECTED_STRUCTURE = PATH_CONVENTION_CONFIG.get("expected_structure", {})
PATH_MODEL_SUBFOLDERS = PATH_CONVENTION_CONFIG.get("model_subfolders", {})

# Legacy compatibility - derive HIL/SIL subfolders from new structure
PATH_VALID_SUBFOLDERS_HIL = PATH_MODEL_SUBFOLDERS.get("MDL", ["CSP", "SWB"])
PATH_VALID_SUBFOLDERS_SIL = PATH_MODEL_SUBFOLDERS.get("MDL_SiL", [])

# =============================================================================
# COMPUTED VALUES (not in config.json)
# =============================================================================

# Application info
APP_TITLE = "Software Line - LCO/VeMox Version Extractor"
APP_VERSION = "1.0.0"

# Project structure
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CURRENT_RUN_DIR: Optional[Path] = None

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)

# =============================================================================
# EXCEL SETTINGS (constants)
# =============================================================================

EXCEL_MASTER_COLUMNS = {
    "Project line": None,
    "ECU - HW Variante": None,
    "Project class": None
}

COLORS = {
    'header_blue': "BDD7EE",
    'header_green': "C6E0B4",
    'found_green': "E8F5E8",
    'not_found_red': "FFE6E6",
    'not_in_tis_grey': "D9D9D9"
}

EXPLANATION_TEXT = [
    "Software Line Mapping Report",
    "{generation_time}",
    "",
    "Purpose:",
    "This report shows the mapping between software lines from the master Excel file and their corresponding artifacts in TIS.",
    "",
    "Color Coding:",
    "- White columns: Master data from Excel file",
    "- Grey: Software line not found in TIS",
    "- Green: Latest artifact found in TIS",
    "- Red: No artifact found in TIS",
    "",
    "Column Groups:",
    "1. Master Data (white): Original software line information from Excel",
    "2. TIS Status (blue): Indicates if the software line exists in TIS",
    "3. Artifact Data (green): Latest artifact information from TIS",
    "",
    "Notes:",
    "- Software lines are matched flexibly (ignoring spaces, underscores, and special characters)",
    "- TIS links are provided for direct access to the projects",
    ""
]

# Excel column definitions
MASTER_DATA_HEADERS = [
    "Software Line",
    "ECU - HW Variante",
    "Project class"
]

TIS_STATUS_HEADER = ["Software Line Found in TIS"]

ARTIFACT_HEADERS = [
    "Latest Artifact Found",
    "Project Name",
    "Project RID",
    "Software Line RID",
    "Latest Artifact Name",
    "Latest Artifact RID",
    "Software Type",
    "LCO Version",
    "VeMoX Version",
    "Labcar Type",
    "Life Cycle Status",
    "Upload Path",
    "TIS Link"
]

# Regular expressions
VEMOX_SVN_PATTERN = r'^vemox(?![._]).+'
VEMOX_CONAN_PATTERN = r"VeMoX/(\d+(\.\d+)*?)@VeMoX_classic/release#[a-f0-9]+"

# Search paths
VEMOX_SEARCH_PATH = "mdl/Simulink_VeMoX/src"

"""Configuration loader for vVeh_LCO Software Line Mapping.

This module loads user-configurable settings from config.json.
"""

from pathlib import Path
from typing import Optional
import json
import sys

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


# Load the configuration
_config = _load_config()

# =============================================================================
# WORKFLOW SETTINGS
# =============================================================================

DEFAULT_EXCEL_FILE = _config["workflow"]["default_excel_file"]
AUTO_OPEN_REPORT = _config["workflow"]["auto_open_report"]
GENERATE_VALIDATION_REPORT = _config["workflow"]["generate_validation_report"]
TIS_EXTRACTOR_PATH = _config["workflow"]["tis_extractor_path"]

# =============================================================================
# OUTPUT SETTINGS
# =============================================================================

EXCEL_OUTPUT_PREFIX = _config["output"]["excel_prefix"]

# =============================================================================
# DISPLAY SETTINGS
# =============================================================================

DATE_DISPLAY_FORMAT = _config.get("display", {}).get("date_format", "%d-%m-%Y %H:%M:%S")

# =============================================================================
# API SETTINGS
# =============================================================================

TIS_LINK_TEMPLATE = _config["api"]["tis_link_template"]

# =============================================================================
# EXCEL SETTINGS
# =============================================================================

EXCEL_MASTER_COLUMNS = _config["excel"]["master_columns"]
COLORS = _config["excel"]["colors"]

# =============================================================================
# NAMING CONVENTION
# =============================================================================

NAMING_CONVENTION_ENABLED = _config.get("naming_convention", {}).get("enabled", False)
NAMING_CONVENTION_PATTERNS = _config.get("naming_convention", {}).get("patterns", {})

# =============================================================================
# COMPUTED VALUES
# =============================================================================

PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CURRENT_RUN_DIR: Optional[Path] = None

# TIS Extractor path (relative to this script or absolute)
TIS_EXTRACTOR_ABS_PATH = (SCRIPT_DIR / TIS_EXTRACTOR_PATH).resolve()

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)

# =============================================================================
# EXPLANATION TEXT FOR EXCEL REPORT
# =============================================================================

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

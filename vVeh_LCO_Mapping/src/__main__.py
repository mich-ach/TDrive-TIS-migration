"""
vVeh_LCO Software Line Mapping Workflow

This workflow maps software lines from an Excel master file to vVeh_LCO artifacts in TIS.
It uses extracted artifact data (JSON) and creates an Excel mapping report.

The TIS data extraction is handled separately by TIS_SWLine_Model_Mapping.
This workflow expects vVeh_LCO artifact JSON files as input.

Usage:
    1. First run TIS extraction: python -m TIS_SWLine_Model_Mapping
    2. Then run this mapping: python -m vVeh_LCO_Mapping <json_file> <excel_file>

    Or with defaults from config:
    python -m vVeh_LCO_Mapping
"""

import datetime
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, NoReturn

from Handlers import DirectoryHandler, ExcelHandler

import config
from config import (
    EXCEL_OUTPUT_PREFIX,
    AUTO_OPEN_REPORT,
    EXCEL_FILE_PATH,
    ARTIFACTS_JSON_PATH,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def exit_with_error(message: str) -> NoReturn:
    """Exit the program with an error message."""
    logger.error(message)
    sys.exit(1)


def open_excel_file(file_path: Path) -> None:
    """Open Excel file with the default application."""
    try:
        file_path_str = str(file_path)
        if platform.system() == 'Darwin':       # macOS
            subprocess.run(['open', file_path_str])
        elif platform.system() == 'Windows':    # Windows
            os.startfile(file_path_str)
        else:                                   # Linux variants
            subprocess.run(['xdg-open', file_path_str])
        logger.info(f"Opened Excel file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to open Excel file: {e}")


def find_latest_vveh_json(search_dir: Path) -> Optional[Path]:
    """Find the latest vVeh_LCO artifacts JSON file."""
    # Look for vVeh_LCO specific files
    patterns = [
        "vveh_lco_artifacts_*.json",
        "latest_vveh_lco_artifacts_*.json",
    ]

    all_files = []
    for pattern in patterns:
        all_files.extend(search_dir.glob(pattern))

    # Also check in run subdirectories
    for run_dir in search_dir.glob("run_*"):
        for pattern in patterns:
            all_files.extend(run_dir.glob(pattern))

    if not all_files:
        return None

    # Return the most recent file
    return max(all_files, key=lambda x: x.stat().st_mtime)


def run_mapping_workflow(json_file: Path, excel_file: Path) -> bool:
    """
    Run the vVeh_LCO mapping workflow.

    Args:
        json_file: Path to vVeh_LCO artifacts JSON file
        excel_file: Path to master Excel file with software lines

    Returns:
        True if successful, False otherwise
    """
    logger.info("=" * 60)
    logger.info("vVeh_LCO Software Line Mapping Workflow")
    logger.info("=" * 60)

    try:
        # Initialize directories
        base_output_dir, run_dir, excel_copy_path = DirectoryHandler.initialize_directories(excel_file)

        logger.info(f"Input JSON: {json_file}")
        logger.info(f"Input Excel: {excel_file}")
        logger.info(f"Output directory: {run_dir}")

        # Copy input JSON file to output directory
        json_copy_path = run_dir / json_file.name
        shutil.copy2(json_file, json_copy_path)
        logger.info(f"Copied input JSON to: {json_copy_path}")

        # Load JSON data
        logger.info("")
        logger.info("Step 1: Loading vVeh_LCO artifact data")

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Count artifacts
            total_projects = len(json_data)
            total_sw_lines = 0
            lines_with_artifacts = 0

            for project_name, project_data in json_data.items():
                sw_lines = project_data.get('software_lines', {})
                total_sw_lines += len(sw_lines)
                for sw_line_name, sw_line_data in sw_lines.items():
                    if sw_line_data.get('latest_artifact') or sw_line_data.get('artifacts'):
                        lines_with_artifacts += 1

            logger.info(f"  Projects: {total_projects}")
            logger.info(f"  Software lines: {total_sw_lines}")
            logger.info(f"  With artifacts: {lines_with_artifacts}")

        except Exception as e:
            exit_with_error(f"Error reading JSON file: {e}")

        # Create Excel mapping
        logger.info("")
        logger.info("Step 2: Creating Excel mapping")

        excel_handler = ExcelHandler()

        excel_data, error = excel_handler.get_excel_data(str(excel_copy_path))
        if error:
            exit_with_error(f"Error reading Excel file: {error}")

        software_lines = excel_data['software_lines']
        project_data = excel_data['project_data']

        logger.info(f"  Software lines from Excel: {len(software_lines)}")

        # Convert JSON to latest_artifact format if needed
        json_latest = {}
        for project_name, proj_data in json_data.items():
            json_latest[project_name] = {
                'project_rid': proj_data.get('project_rid', ''),
                'software_lines': {}
            }
            for sw_name, sw_data in proj_data.get('software_lines', {}).items():
                # Check if already has latest_artifact or need to extract from artifacts list
                latest = sw_data.get('latest_artifact')
                if not latest and sw_data.get('artifacts'):
                    # Get artifact with highest RID
                    artifacts = sw_data['artifacts']
                    latest = max(artifacts, key=lambda x: int(x.get('artifact_rid', 0)))

                json_latest[project_name]['software_lines'][sw_name] = {
                    'software_line_rid': sw_data.get('software_line_rid', ''),
                    'latest_artifact': latest
                }

        mapping = excel_handler.create_mapping(software_lines, json_latest, project_data)

        output_file = DirectoryHandler.get_output_file_path(EXCEL_OUTPUT_PREFIX, "xlsx")
        success, error = excel_handler.generate_report(mapping, output_file)

        if not success:
            exit_with_error(f"Error generating report: {error}")

        logger.info(f"  Report generated: {output_file}")

        # Open report
        if AUTO_OPEN_REPORT:
            open_excel_file(output_file)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Mapping Workflow Complete")
        logger.info("=" * 60)
        logger.info(f"Output: {output_file}")

        return True

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    # Parse arguments - command line takes priority over config
    json_file = None
    excel_file = None

    if len(sys.argv) >= 3:
        json_file = Path(sys.argv[1]).resolve()
        excel_file = Path(sys.argv[2]).resolve()
    elif len(sys.argv) == 2:
        # Single argument: assume it's JSON file, use Excel from config
        json_file = Path(sys.argv[1]).resolve()
        if EXCEL_FILE_PATH:
            excel_file = Path(EXCEL_FILE_PATH).resolve()
    else:
        # No arguments: use paths from config
        if ARTIFACTS_JSON_PATH:
            json_file = Path(ARTIFACTS_JSON_PATH).resolve()
        if EXCEL_FILE_PATH:
            excel_file = Path(EXCEL_FILE_PATH).resolve()

    # Validate inputs
    if not json_file:
        logger.error("No vVeh_LCO artifact JSON file specified!")
        logger.info("")
        logger.info("Usage:")
        logger.info("  python -m vVeh_LCO_Mapping <json_file> <excel_file>")
        logger.info("  python -m vVeh_LCO_Mapping <json_file>")
        logger.info("  python -m vVeh_LCO_Mapping")
        logger.info("")
        logger.info("Or set paths in config.json:")
        logger.info('  "inputs": {')
        logger.info('    "excel_file": "/path/to/masterdata.xlsx",')
        logger.info('    "artifacts_json": "/path/to/vVeh_LCO_artifacts.json"')
        logger.info('  }')
        sys.exit(1)

    if not json_file.exists():
        exit_with_error(f"JSON file not found: {json_file}")

    if not excel_file:
        exit_with_error("No Excel file specified! Provide as argument or set in config.json")

    if not excel_file.exists():
        exit_with_error(f"Excel file not found: {excel_file}")

    logger.info(f"JSON file: {json_file}")
    logger.info(f"Excel file: {excel_file}")

    success = run_mapping_workflow(json_file, excel_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

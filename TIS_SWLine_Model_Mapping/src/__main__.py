"""
Main script to run the complete workflow of TIS data extraction and Excel mapping.

This version uses the OPTIMIZED RECURSIVE artifact extractor which:
- Uses BFS recursive search to find ALL vVeh artifacts
- Finds artifacts even when uploaded in non-standard locations
- Uses adaptive depth to handle slow API responses
- Uses concurrent requests for better performance
- Has caching and branch pruning optimizations

The output format remains compatible with the original workflow.

Usage:
    1. Set DEFAULT_EXCEL_FILE in config.py and run: python run_workflow.py
    2. Or pass file as argument: python run_workflow.py <excel_file>

Configuration:
    All settings are in config.py:
    - DEFAULT_EXCEL_FILE: Default input Excel file path
    - AUTO_OPEN_REPORT: Whether to open reports automatically
    - GENERATE_VALIDATION_REPORT: Whether to generate path deviation report
"""
import datetime
import json
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, NoReturn

from Handlers import DirectoryHandler, ExcelHandler
from tis_artifact_extractor import main as extract_artifacts
from Models import DeviationType, ValidationReport

# Import settings from config
from config import (
    JSON_OUTPUT_PREFIX,
    LATEST_JSON_PREFIX,
    EXCEL_OUTPUT_PREFIX,
    DEFAULT_EXCEL_FILE,
    AUTO_OPEN_REPORT,
    GENERATE_VALIDATION_REPORT,
    OPEN_ARTIFACT_VIEWER,
    LOG_LEVEL,
    TIS_LINK_TEMPLATE,
    NAMING_CONVENTION_ENABLED,
)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
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


def launch_artifact_viewer(json_file: Path) -> None:
    """Launch the artifact viewer GUI with the specified JSON file."""
    try:
        from artifact_viewer_gui import ArtifactViewerGUI
        import tkinter as tk

        logger.info("Launching Artifact Viewer GUI...")
        root = tk.Tk()
        app = ArtifactViewerGUI(root)

        # Load the JSON file
        app._load_file(json_file)

        root.mainloop()
    except ImportError as e:
        logger.warning(f"Could not import artifact viewer: {e}")
        logger.info("Make sure tkinter is installed.")
    except Exception as e:
        logger.warning(f"Failed to launch artifact viewer: {e}")


def generate_validation_report(json_data: dict, output_dir: Path) -> Optional[str]:
    """
    Generate a validation report showing path and naming convention deviations.

    This validates artifacts against:
    1. Path convention: {Project}/{SWLine}/Model/HiL|SiL/{subfolder}/...
    2. Naming convention: Based on patterns in config.json
    """
    try:
        from Reports import generate_excel_report
        from Validators import PathValidator
    except ImportError as e:
        logger.warning(f"Could not import validation modules: {e}")
        return None

    logger.info("Step 3: Generating Validation Report (Path & Naming Deviations)")
    logger.info("       Analyzing artifact paths and names for convention compliance...")

    # Create path validator instance
    path_validator = PathValidator()

    # Build validation report from extracted data
    report = ValidationReport(
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    # Process all artifacts
    for project_name, project_data in json_data.items():
        report.total_projects += 1
        report.processed_projects += 1

        for sw_line_name, sw_line_data in project_data.get('software_lines', {}).items():
            latest = sw_line_data.get('latest_artifact')
            if not latest:
                continue

            report.total_artifacts_found += 1

            artifact_name = latest.get('name', '')
            path = latest.get('upload_path', '')
            component_type = latest.get('component_type', '')

            # Validate naming convention
            name_valid, matched_pattern, matched_groups, name_error = path_validator.validate_naming_convention(artifact_name)

            # Validate path convention
            path_deviation, path_details, path_hint = path_validator.validate_path(path, artifact_name, component_type)

            deviation_type = DeviationType.VALID
            details = ""
            hint = ""

            if not name_valid and NAMING_CONVENTION_ENABLED:
                deviation_type = DeviationType.INVALID_NAME_FORMAT
                details = f"Name format invalid: {name_error}"
                hint = "See naming convention patterns in config"
            elif path_deviation != DeviationType.VALID:
                deviation_type = path_deviation
                details = path_details
                hint = path_hint

            artifact_dict = {
                'component_id': latest.get('artifact_rid', ''),
                'component_name': artifact_name,
                'path': path,
                'user': latest.get('user', 'UNKNOWN'),
                'tis_link': TIS_LINK_TEMPLATE.format(latest.get('artifact_rid', '')),
                'deviation_type': deviation_type.value,
                'deviation_details': details,
                'expected_path_hint': hint,
                'name_pattern_matched': matched_pattern,
                'name_pattern_groups': matched_groups,
            }

            if deviation_type == DeviationType.VALID:
                report.valid_artifacts += 1
                report.valid_paths.append(artifact_dict)
            else:
                report.deviations_found += 1
                report.deviations.append(artifact_dict)

                if deviation_type.value not in report.deviations_by_type:
                    report.deviations_by_type[deviation_type.value] = []
                report.deviations_by_type[deviation_type.value].append(artifact_dict)

                user = artifact_dict['user']
                if user not in report.deviations_by_user:
                    report.deviations_by_user[user] = []
                report.deviations_by_user[user].append(artifact_dict)

                if project_name not in report.deviations_by_project:
                    report.deviations_by_project[project_name] = []
                report.deviations_by_project[project_name].append(artifact_dict)

    # Generate Excel report
    if report.total_artifacts_found > 0:
        output_file = generate_excel_report(report, output_dir)
        logger.info("Validation Report Summary:")
        logger.info(f"  Total Artifacts: {report.total_artifacts_found}")
        logger.info(f"  Valid (Path & Name): {report.valid_artifacts}")
        logger.info(f"  Deviations: {report.deviations_found}")

        if report.deviations_by_type:
            logger.info("Deviations by Type:")
            for dev_type, devs in sorted(report.deviations_by_type.items(), key=lambda x: -len(x[1])):
                logger.info(f"  {dev_type}: {len(devs)}")

        if report.deviations_by_user:
            logger.info("Top Uploaders with Deviations:")
            sorted_users = sorted(report.deviations_by_user.items(), key=lambda x: len(x[1]), reverse=True)[:5]
            for user, devs in sorted_users:
                logger.info(f"  {user}: {len(devs)}")

        return output_file
    else:
        logger.info("No artifacts found to validate")
        return None


def run_workflow(excel_file: str):
    logger.info("=" * 60)
    logger.info("Starting Complete Workflow (Optimized Recursive Version)")
    logger.info("=" * 60)

    try:
        import config

        excel_path = Path(excel_file).resolve()

        base_output_dir, run_dir, excel_copy_path = DirectoryHandler.initialize_directories(excel_path)

        logger.info(f"Input Excel: {excel_path}")
        logger.info(f"Excel copy: {excel_copy_path}")
        logger.info(f"Base output directory: {base_output_dir}")
        logger.info(f"Run directory: {run_dir}")

        if not DirectoryHandler.ensure_run_directory_set():
            raise ValueError("Failed to properly initialize run directory in config!")

        current_run_dir = DirectoryHandler.get_current_run_dir()
        logger.debug(f"Verified config run directory: {current_run_dir}")

        # Step 1: Extract artifacts from TIS
        logger.info("")
        logger.info("Step 1: Extracting artifacts from TIS (Optimized Recursive Search)")
        logger.info("       This version finds ALL artifacts, including misplaced ones.")
        if not extract_artifacts():
            raise ValueError("Failed to extract artifacts from TIS")

        # Find JSON files
        logger.debug("Checking created JSON files...")
        all_json_files = list(current_run_dir.glob("*.json"))
        logger.debug(f"All JSON files in run directory: {[f.name for f in all_json_files]}")

        latest_artifact_files = list(current_run_dir.glob(f'{LATEST_JSON_PREFIX}_*.json'))
        logger.debug(f"Found {len(latest_artifact_files)} latest artifact files")

        if not latest_artifact_files:
            logger.warning("No latest artifact files found, checking for regular artifact files...")
            artifact_files = list(current_run_dir.glob(f'{JSON_OUTPUT_PREFIX}_*.json'))

            if not artifact_files:
                exit_with_error("No JSON files found at all!")

            latest_file = max(artifact_files, key=lambda x: x.stat().st_mtime)
            logger.info(f"Using regular artifacts file as fallback: {latest_file.name}")
        else:
            latest_file = max(latest_artifact_files, key=lambda x: x.stat().st_mtime)
            logger.info(f"Using latest artifacts file: {latest_file.name}")

        # Load JSON data
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                logger.info(f"Successfully loaded JSON data from {latest_file.name}")
                logger.info(f"  Number of projects: {len(json_data)}")

                total_sw_lines = 0
                lines_with_artifacts = 0
                for project_name, project_data in json_data.items():
                    sw_lines = project_data.get('software_lines', {})
                    total_sw_lines += len(sw_lines)
                    for sw_line_name, sw_line_data in sw_lines.items():
                        if sw_line_data.get('latest_artifact'):
                            lines_with_artifacts += 1

                logger.info(f"  Total software lines: {total_sw_lines}")
                logger.info(f"  Software lines with artifacts: {lines_with_artifacts}")

                if lines_with_artifacts == 0:
                    logger.warning("No software lines have artifacts!")

        except Exception as e:
            exit_with_error(f"Error reading JSON file {latest_file}: {e}")

        # Step 2: Create Excel mapping
        logger.info("")
        logger.info("Step 2: Creating Excel mapping")
        excel_handler = ExcelHandler()

        logger.info(f"Reading from: {excel_copy_path}")
        excel_data, error = excel_handler.get_excel_data(str(excel_copy_path))
        if error:
            exit_with_error(f"Error reading Excel file: {error}")

        software_lines = excel_data['software_lines']
        project_data = excel_data['project_data']

        logger.info("Excel data loaded:")
        logger.info(f"  Software lines from Excel: {len(software_lines)}")
        logger.info(f"  Project data entries: {len(project_data)}")

        logger.info("Creating mapping and generating report")
        mapping = excel_handler.create_mapping(software_lines, json_data, project_data)

        output_file = DirectoryHandler.get_output_file_path(EXCEL_OUTPUT_PREFIX, "xlsx")

        success, error = excel_handler.generate_report(mapping, output_file)
        if not success:
            exit_with_error(f"Error generating report: {error}")

        logger.info(f"Workflow completed successfully!")
        logger.info(f"Final report: {output_file}")

        # Step 3 (Optional): Generate validation report
        validation_report_file = None
        if GENERATE_VALIDATION_REPORT:
            validation_report_file = generate_validation_report(json_data, current_run_dir)
            if validation_report_file:
                logger.info(f"Validation report: {validation_report_file}")

        # Open the Excel files
        if AUTO_OPEN_REPORT:
            logger.info("Opening Excel file...")
            open_excel_file(output_file)
            if validation_report_file and GENERATE_VALIDATION_REPORT:
                open_excel_file(Path(validation_report_file))

        # Launch artifact viewer GUI
        if OPEN_ARTIFACT_VIEWER:
            launch_artifact_viewer(latest_file)

        logger.info("=" * 60)
        logger.info("Workflow Finished")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Unexpected error in workflow: {e}")
        import config
        logger.debug(f"Current config.CURRENT_RUN_DIR = {config.CURRENT_RUN_DIR}")
        return False
    return True


def resolve_excel_path(file_path: str) -> Path:
    """
    Resolve Excel file path. Handles both absolute and relative paths.
    Relative paths are resolved from the script directory.
    """
    path = Path(file_path)

    if path.is_absolute():
        return path

    script_dir = Path(__file__).resolve().parent
    return (script_dir / path).resolve()


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        excel_file = sys.argv[1]
        logger.info(f"Using Excel file from argument: {excel_file}")
    else:
        excel_file = DEFAULT_EXCEL_FILE
        logger.info(f"No argument provided, using default: {excel_file}")

    resolved_path = resolve_excel_path(excel_file)

    if not resolved_path.exists():
        logger.error(f"Excel file not found: {resolved_path}")
        logger.info("To fix this, either:")
        logger.info("  1. Update DEFAULT_EXCEL_FILE in config.py")
        logger.info("  2. Pass the file path as an argument: python run_workflow.py <excel_file>")
        sys.exit(1)

    logger.info(f"Resolved path: {resolved_path}")

    success = run_workflow(str(resolved_path))
    sys.exit(0 if success else 1)

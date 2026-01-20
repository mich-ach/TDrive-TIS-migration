"""
TIS Artifact Extractor - General purpose TIS data extraction tool.

This tool extracts artifacts from TIS (Test Information System) using recursive
BFS search. It works with any artifact type configured in config.json.

Features:
- Extracts ALL artifacts matching configured filters (component_type, component_name, etc.)
- Finds artifacts even when uploaded in non-standard locations
- Uses adaptive depth to handle slow API responses
- Uses concurrent requests for better performance
- Has caching and branch pruning optimizations
- Separates output by component_type (one JSON file per type)
- Generates validation report showing path/naming deviations

Output:
- {component_type}_artifacts_{timestamp}.json - Artifacts grouped by component type
- latest_{component_type}_artifacts_{timestamp}.json - Latest artifact per software line
- optimized_validation_report_{timestamp}.xlsx - Validation report (if enabled)

Usage:
    python -m TIS_SWLine_Model_Mapping [--gui]

    --gui: Open the artifact viewer GUI after extraction

Configuration:
    All settings are in config.json:
    - artifact_filters: Filter by component_type, component_name, etc.
    - branch_pruning: Skip unnecessary folders
    - optimization: Concurrent requests, caching settings
    - validation: Generate validation report settings
"""

import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from Fetchers import run_extraction as fetch_artifacts, separate_by_component_type, extract_latest_artifacts

import config
from config import (
    LOG_LEVEL,
    GENERATE_VALIDATION_REPORT,
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


def initialize_run_directory() -> Path:
    """Initialize a new run directory for output files."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = config.OUTPUT_DIR / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    config.CURRENT_RUN_DIR = run_dir
    return run_dir


def launch_artifact_viewer(search_dir: Path) -> None:
    """Launch the artifact viewer GUI."""
    try:
        from artifact_viewer_gui import main as gui_main
        import wx

        # Find JSON files
        json_files = list(search_dir.glob("*_artifacts_*.json"))
        json_files = [f for f in json_files if not f.name.startswith("latest_")]

        if json_files:
            # Launch GUI with the first file found
            latest_file = max(json_files, key=lambda x: x.stat().st_mtime)
            logger.info(f"Launching Artifact Viewer with: {latest_file.name}")

            app = wx.App(False)
            from artifact_viewer_gui import ArtifactViewerFrame
            frame = ArtifactViewerFrame(None, json_file=latest_file)
            frame.Show()
            app.MainLoop()
        else:
            logger.warning("No artifact files found to view")
    except ImportError as e:
        logger.warning(f"Could not import artifact viewer: {e}")
        logger.info("Make sure wxPython is installed: pip install wxPython")
    except Exception as e:
        logger.warning(f"Failed to launch artifact viewer: {e}")


def generate_validation_report(structured_data: Dict[str, Any], output_dir: Path) -> Optional[str]:
    """
    Generate a validation report showing path and naming convention deviations.

    Args:
        structured_data: The extracted artifact data from ArtifactFetcher.extract()
        output_dir: Directory to save the validation report

    Returns:
        Path to the generated Excel file, or None if generation failed
    """
    try:
        from Reports import generate_excel_report
        from Validators import PathValidator
        from Models import DeviationType, ValidationReport
    except ImportError as e:
        logger.warning(f"Could not import validation modules: {e}")
        return None

    logger.info("Generating Validation Report (Path & Naming Deviations)")

    path_validator = PathValidator()

    report = ValidationReport(
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    for project_name, project_data in structured_data.items():
        report.total_projects += 1
        report.processed_projects += 1

        for sw_line_name, sw_line_data in project_data.get('software_lines', {}).items():
            artifacts = sw_line_data.get('artifacts', [])

            for artifact in artifacts:
                report.total_artifacts_found += 1

                artifact_name = artifact.get('name', '')
                path = artifact.get('upload_path', '')
                component_type = artifact.get('component_type', '')

                name_valid, matched_pattern, matched_groups, name_error = path_validator.validate_naming_convention(artifact_name)
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
                    'component_id': artifact.get('artifact_rid', ''),
                    'component_name': artifact_name,
                    'component_type': component_type,
                    'path': path,
                    'user': artifact.get('user', 'UNKNOWN'),
                    'tis_link': TIS_LINK_TEMPLATE.format(artifact.get('artifact_rid', '')),
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

    if report.total_artifacts_found > 0:
        output_file = generate_excel_report(report, output_dir)
        logger.info("Validation Report Summary:")
        logger.info(f"  Total Artifacts: {report.total_artifacts_found}")
        logger.info(f"  Valid: {report.valid_artifacts}")
        logger.info(f"  Deviations: {report.deviations_found}")
        return output_file
    else:
        logger.info("No artifacts found to validate")
        return None


def run_extraction_workflow(open_gui: bool = False) -> bool:
    """
    Run the TIS artifact extraction workflow.

    Args:
        open_gui: Whether to open the artifact viewer GUI after extraction

    Returns:
        True if successful, False otherwise
    """
    logger.info("=" * 60)
    logger.info("TIS Artifact Extractor")
    logger.info("=" * 60)

    try:
        # Initialize run directory
        run_dir = initialize_run_directory()
        logger.info(f"Output directory: {run_dir}")

        # Run extraction
        logger.info("")
        logger.info("Extracting artifacts from TIS...")
        logger.info("This may take several minutes depending on the number of artifacts.")
        logger.info("")

        success, structured_data = fetch_artifacts()
        if not success:
            logger.error("Extraction failed!")
            return False

        # List output files
        output_files = list(run_dir.glob("*_artifacts_*.json"))
        output_files = [f for f in output_files if not f.name.startswith("latest_")]

        logger.info("")
        logger.info("=" * 60)
        logger.info("Extraction Complete")
        logger.info("=" * 60)
        logger.info(f"Output directory: {run_dir}")
        logger.info(f"Generated files:")
        for f in sorted(output_files):
            logger.info(f"  - {f.name}")

        # Generate validation report if enabled
        if GENERATE_VALIDATION_REPORT and structured_data:
            logger.info("")
            logger.info("Generating validation report...")
            validation_report_file = generate_validation_report(structured_data, run_dir)
            if validation_report_file:
                logger.info(f"  - {Path(validation_report_file).name}")

        # Launch GUI if requested
        if open_gui:
            launch_artifact_viewer(run_dir)

        return True

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main entry point."""
    open_gui = "--gui" in sys.argv

    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)

    success = run_extraction_workflow(open_gui=open_gui)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

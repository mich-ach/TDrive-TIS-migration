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
- {component_type}_validation_report_{timestamp}.xlsx - Validation report per component type (if enabled)

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


def generate_validation_report_for_component(
    component_name: str,
    component_data: Dict[str, Any],
    output_dir: Path,
    path_validator,
    DeviationType,
    ValidationReport,
    generate_excel_report
) -> Optional[str]:
    """
    Generate a validation report for a single component type.

    Args:
        component_name: Name of the component type (e.g., 'vVeh_LCO', 'test_ECU-TEST')
        component_data: The extracted artifact data for this component type
        output_dir: Directory to save the validation report
        path_validator: PathValidator instance
        DeviationType: DeviationType enum
        ValidationReport: ValidationReport class
        generate_excel_report: Function to generate Excel report

    Returns:
        Path to the generated Excel file, or None if generation failed
    """
    import time
    start_time = time.time()

    report = ValidationReport(
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    for project_name, project_data in component_data.items():
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
                    # Get expected path structure for this component type
                    hint = path_validator._get_expected_structure(component_type) or path_hint
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

    # Set runtime
    report.total_time_seconds = time.time() - start_time

    if report.total_artifacts_found > 0:
        # Create component-specific filename
        safe_name = component_name.replace(' ', '_')
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_file = output_dir / f"{safe_name}_validation_report_{timestamp}.xlsx"

        # Generate report with custom filename, skip component type sheets since this is per-component
        from Reports import generate_excel_report as _gen_report
        result = _gen_report(report, output_dir, skip_component_type_sheets=True)

        # Rename to component-specific name if successful
        if result:
            result_path = Path(result)
            if result_path.exists():
                result_path.rename(output_file)
                return str(output_file)

        return result
    return None


def generate_validation_reports_by_component(structured_data: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    """
    Generate separate validation reports for each component type.

    Args:
        structured_data: The extracted artifact data from ArtifactFetcher.extract()
        output_dir: Directory to save the validation reports

    Returns:
        Dict mapping component_name to output file path
    """
    try:
        from Reports import generate_excel_report
        from Validators import PathValidator
        from Models import DeviationType, ValidationReport
    except ImportError as e:
        logger.warning(f"Could not import validation modules: {e}")
        return {}

    logger.info("Generating Validation Reports by Component Type (Path & Naming Deviations)")

    path_validator = PathValidator()
    output_files = {}

    # Separate data by component type
    by_component = separate_by_component_type(structured_data)

    for component_name, component_data in by_component.items():
        logger.info(f"  Generating validation report for {component_name}...")

        output_file = generate_validation_report_for_component(
            component_name=component_name,
            component_data=component_data,
            output_dir=output_dir,
            path_validator=path_validator,
            DeviationType=DeviationType,
            ValidationReport=ValidationReport,
            generate_excel_report=generate_excel_report
        )

        if output_file:
            output_files[component_name] = output_file
            logger.info(f"    -> {Path(output_file).name}")

    return output_files


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

        # Generate validation reports (one per component type) if enabled
        if GENERATE_VALIDATION_REPORT and structured_data:
            logger.info("")
            validation_report_files = generate_validation_reports_by_component(structured_data, run_dir)
            if validation_report_files:
                logger.info(f"Generated {len(validation_report_files)} validation report(s)")

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

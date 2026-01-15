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
import os
import subprocess
import platform
import sys
from pathlib import Path
import json
import datetime
from typing import Optional, NoReturn
from directory_handler import DirectoryHandler
from tis_artifact_extractor import TISAPIService, main as extract_artifacts
from excel_handler import ExcelHandler

# Import all settings from config
from config import (
    OUTPUT_DIR,
    JSON_OUTPUT_PREFIX,
    LATEST_JSON_PREFIX,
    EXCEL_OUTPUT_PREFIX,
    DEFAULT_EXCEL_FILE,
    AUTO_OPEN_REPORT,
    GENERATE_VALIDATION_REPORT,
    OPEN_ARTIFACT_VIEWER,
)


def exit_with_error(message: str) -> NoReturn:
    """Exit the program with an error message."""
    print(f"\nError: {message}")
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
        print(f"\nOpened Excel file: {file_path}")
    except Exception as e:
        print(f"\nWarning: Failed to open Excel file: {e}")


def launch_artifact_viewer(json_file: Path) -> None:
    """Launch the artifact viewer GUI with the specified JSON file."""
    try:
        from artifact_viewer_gui import ArtifactViewerGUI
        import tkinter as tk

        print("\nLaunching Artifact Viewer GUI...")
        root = tk.Tk()
        app = ArtifactViewerGUI(root)

        # Load the JSON file
        app._load_file(json_file)

        root.mainloop()
    except ImportError as e:
        print(f"\nWarning: Could not import artifact viewer: {e}")
        print("Make sure tkinter is installed.")
    except Exception as e:
        print(f"\nWarning: Failed to launch artifact viewer: {e}")


def generate_validation_report(json_data: dict, output_dir: Path) -> Optional[str]:
    """
    Generate a validation report showing path and naming convention deviations.

    This validates artifacts against:
    1. Path convention: {Project}/{SWLine}/Model/HiL|SiL/{subfolder}/...
    2. Naming convention: Based on patterns in config.json
    """
    try:
        from artifact_structure_validator_optimized import (
            ValidationReport,
            DeviationType,
            generate_excel_report
        )
        from config import (
            TIS_LINK_TEMPLATE,
            NAMING_CONVENTION_ENABLED,
            NAMING_CONVENTION_PATTERNS,
            PATH_CONVENTION_ENABLED,
            PATH_EXPECTED_STRUCTURE,
            PATH_MODEL_SUBFOLDERS,
            PATH_VALID_SUBFOLDERS_HIL,
        )
    except ImportError as e:
        print(f"Warning: Could not import validation module: {e}")
        return None

    print("\nStep 3: Generating Validation Report (Path & Naming Deviations)")
    print("       Analyzing artifact paths and names for convention compliance...")

    # Build validation report from extracted data
    report = ValidationReport()
    report.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    import re

    # Compile naming convention patterns
    compiled_patterns = {}
    if NAMING_CONVENTION_ENABLED and NAMING_CONVENTION_PATTERNS:
        for pattern_name, pattern_config in NAMING_CONVENTION_PATTERNS.items():
            try:
                compiled_patterns[pattern_name] = {
                    'regex': re.compile(pattern_config['pattern']),
                    'description': pattern_config.get('description', ''),
                    'example': pattern_config.get('example', '')
                }
            except re.error as e:
                print(f"Warning: Invalid regex for pattern '{pattern_name}': {e}")

    def validate_naming_convention(artifact_name: str) -> tuple:
        """Validate artifact name against configured patterns."""
        if not NAMING_CONVENTION_ENABLED or not compiled_patterns:
            return (True, None, None, None)  # Validation disabled

        for pattern_name, pattern_data in compiled_patterns.items():
            match = pattern_data['regex'].match(artifact_name)
            if match:
                return (True, pattern_name, match.groupdict(), None)

        # No pattern matched
        return (False, None, None, "Name does not match any known pattern")

    def get_model_subfolders_for_component(component_name: str) -> list:
        """Get expected model subfolders for a component_name by matching patterns."""
        if not component_name:
            return []

        # Try exact match first
        if component_name in PATH_MODEL_SUBFOLDERS:
            return PATH_MODEL_SUBFOLDERS[component_name]

        # Try prefix match (e.g., "MDL_HiL_PCIe" matches "MDL_HiL")
        for pattern, subfolders in PATH_MODEL_SUBFOLDERS.items():
            if pattern.startswith('_comment'):
                continue
            if component_name.startswith(pattern):
                return subfolders

        # Fallback to HIL defaults if component contains HiL indicators
        if 'MDL' in component_name and 'SiL' not in component_name:
            return PATH_VALID_SUBFOLDERS_HIL

        return []

    def get_expected_structure_for_component(component_name: str) -> str:
        """Get expected path structure for a component_name."""
        if not component_name:
            return ""

        # Try exact match first
        if component_name in PATH_EXPECTED_STRUCTURE:
            return PATH_EXPECTED_STRUCTURE[component_name]

        # Try prefix match
        for pattern, structure in PATH_EXPECTED_STRUCTURE.items():
            if pattern.startswith('_comment'):
                continue
            if component_name.startswith(pattern):
                return structure

        return ""

    def validate_path_convention(path: str, artifact_name: str, component_name: str = None) -> tuple:
        """Validate path against configured convention based on component_name."""
        if not PATH_CONVENTION_ENABLED:
            return (DeviationType.VALID, "", "")

        path_parts = path.split('/') if path else []

        if len(path_parts) < 2:
            return (
                DeviationType.WRONG_LOCATION,
                "Path too short",
                "[Project]/[SWLine]/Model/HiL|SiL/[subfolder]/..."
            )

        project = path_parts[0]
        sw_line = path_parts[1] if len(path_parts) > 1 else "Unknown"

        if 'Model' not in path_parts:
            return (
                DeviationType.MISSING_MODEL,
                "Artifact not under 'Model' folder",
                f"{project}/{sw_line}/Model/..."
            )

        model_index = path_parts.index('Model')
        remaining = path_parts[model_index + 1:]

        # Check for HiL or SiL path
        is_hil_path = 'HiL' in remaining
        is_sil_path = 'SiL' in remaining

        # Get expected structure and model subfolders for this component
        expected_structure = get_expected_structure_for_component(component_name) if component_name else ""
        model_subfolders = get_model_subfolders_for_component(component_name) if component_name else []

        if not is_hil_path and not is_sil_path:
            # Check if CSP/SWB directly under Model (common mistake)
            if remaining and any(sf in remaining[0] for sf in PATH_VALID_SUBFOLDERS_HIL):
                return (
                    DeviationType.CSP_SWB_UNDER_MODEL,
                    f"{remaining[0]} directly under Model (missing HiL)",
                    f"{project}/{sw_line}/Model/HiL/{remaining[0]}/..."
                )
            return (
                DeviationType.MISSING_HIL,
                "Missing 'HiL' or 'SiL' folder after Model",
                expected_structure or f"{project}/{sw_line}/Model/HiL|SiL/[subfolder]/..."
            )

        # Validate HiL path
        if is_hil_path:
            hil_index = remaining.index('HiL')
            after_hil = remaining[hil_index + 1:]

            if not after_hil:
                return (
                    DeviationType.MISSING_CSP_SWB,
                    "Missing subfolder after HiL",
                    expected_structure or f"{project}/{sw_line}/Model/HiL/[CSP|SWB]/..."
                )

            # Check if first folder after HiL is valid
            first_after_hil = after_hil[0]
            check_subfolders = model_subfolders if model_subfolders else PATH_VALID_SUBFOLDERS_HIL
            is_valid_subfolder = any(
                sf.lower() in first_after_hil.lower()
                for sf in check_subfolders
            )
            if not is_valid_subfolder:
                return (
                    DeviationType.INVALID_SUBFOLDER,
                    f"Invalid subfolder '{first_after_hil}' after HiL",
                    expected_structure or f"{project}/{sw_line}/Model/HiL/[{'/'.join(check_subfolders)}]/..."
                )

        # Validate SiL path
        if is_sil_path:
            sil_index = remaining.index('SiL')
            after_sil = remaining[sil_index + 1:]

            if not after_sil:
                return (
                    DeviationType.MISSING_SIL,
                    "Missing subfolder after SiL",
                    expected_structure or f"{project}/{sw_line}/Model/SiL/[subfolder]/..."
                )

            # Check if first folder after SiL is valid (if model_subfolders configured for this component)
            if model_subfolders:
                first_after_sil = after_sil[0]
                is_valid_subfolder = any(
                    sf.lower() in first_after_sil.lower()
                    for sf in model_subfolders
                )
                if not is_valid_subfolder:
                    return (
                        DeviationType.INVALID_SUBFOLDER,
                        f"Invalid subfolder '{first_after_sil}' after SiL (expected: {', '.join(model_subfolders)})",
                        expected_structure or f"{project}/{sw_line}/Model/SiL/[{'/'.join(model_subfolders)}]/..."
                    )

        return (DeviationType.VALID, "", "")

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
            component_type = latest.get('component_type', '')  # e.g., "vVeh_LCO", "MDL_SiL"

            # Validate naming convention
            name_valid, matched_pattern, matched_groups, name_error = validate_naming_convention(artifact_name)

            # Validate path convention (using component_type for lookup)
            path_deviation, path_details, path_hint = validate_path_convention(path, artifact_name, component_type)

            # Determine overall deviation
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

            # Build artifact dict
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

                # Group by type
                if deviation_type.value not in report.deviations_by_type:
                    report.deviations_by_type[deviation_type.value] = []
                report.deviations_by_type[deviation_type.value].append(artifact_dict)

                # Group by user
                user = artifact_dict['user']
                if user not in report.deviations_by_user:
                    report.deviations_by_user[user] = []
                report.deviations_by_user[user].append(artifact_dict)

                # Group by project
                if project_name not in report.deviations_by_project:
                    report.deviations_by_project[project_name] = []
                report.deviations_by_project[project_name].append(artifact_dict)

    # Generate Excel report
    if report.total_artifacts_found > 0:
        output_file = generate_excel_report(report, output_dir)
        print(f"\nValidation Report Summary:")
        print(f"  Total Artifacts: {report.total_artifacts_found}")
        print(f"  Valid (Path & Name): {report.valid_artifacts}")
        print(f"  Deviations: {report.deviations_found}")

        if report.deviations_by_type:
            print(f"\nDeviations by Type:")
            for dev_type, devs in sorted(report.deviations_by_type.items(), key=lambda x: -len(x[1])):
                print(f"  {dev_type}: {len(devs)}")

        if report.deviations_by_user:
            print(f"\nTop Uploaders with Deviations:")
            sorted_users = sorted(report.deviations_by_user.items(), key=lambda x: len(x[1]), reverse=True)[:5]
            for user, devs in sorted_users:
                print(f"  {user}: {len(devs)}")

        return output_file
    else:
        print("  No artifacts found to validate")
        return None


def run_workflow(excel_file: str):
    print("\n=== Starting Complete Workflow (Optimized Recursive Version) ===\n")

    try:
        # Import config for run-time access
        import config

        # Convert input path to absolute path
        excel_path = Path(excel_file).resolve()

        # Initialize directories and copy Excel file
        base_output_dir, run_dir, excel_copy_path = DirectoryHandler.initialize_directories(excel_path)

        print(f"Input Excel: {excel_path}")
        print(f"Excel copy: {excel_copy_path}")
        print(f"Base output directory: {base_output_dir}")
        print(f"Run directory: {run_dir}")

        # Verify that the run directory was properly set in config
        if not DirectoryHandler.ensure_run_directory_set():
            raise ValueError("Failed to properly initialize run directory in config!")

        current_run_dir = DirectoryHandler.get_current_run_dir()
        print(f"Verified config run directory: {current_run_dir}")

        # Step 1: Extract artifacts from TIS (using optimized recursive extractor)
        print("\nStep 1: Extracting artifacts from TIS (Optimized Recursive Search)")
        print("       This version finds ALL artifacts, including misplaced ones.")
        if not extract_artifacts():
            raise ValueError("Failed to extract artifacts from TIS")

        # DEBUG: List all JSON files created
        print("\nDEBUG: Checking created JSON files...")
        all_json_files = list(current_run_dir.glob("*.json"))
        print(f"All JSON files in run directory:")
        for json_file in all_json_files:
            print(f"  - {json_file.name} (size: {json_file.stat().st_size} bytes)")

        # Find the most recent LATEST artifacts file (this is what we need for mapping)
        latest_artifact_files = list(current_run_dir.glob(f'{LATEST_JSON_PREFIX}_*.json'))
        print(f"\nLooking for files matching pattern: {LATEST_JSON_PREFIX}_*.json")
        print(f"Found {len(latest_artifact_files)} latest artifact files:")
        for f in latest_artifact_files:
            print(f"  - {f.name}")

        if not latest_artifact_files:
            # Fallback: check for regular artifact files
            print("No latest artifact files found, checking for regular artifact files...")
            artifact_files = list(current_run_dir.glob(f'{JSON_OUTPUT_PREFIX}_*.json'))
            print(f"Found {len(artifact_files)} regular artifact files:")
            for f in artifact_files:
                print(f"  - {f.name}")

            if not artifact_files:
                exit_with_error("No JSON files found at all!")

            # Use the regular artifacts file as fallback
            latest_file = max(artifact_files, key=lambda x: x.stat().st_mtime)
            print(f"Using regular artifacts file as fallback: {latest_file.name}")
        else:
            # Use the most recent latest artifacts file
            latest_file = max(latest_artifact_files, key=lambda x: x.stat().st_mtime)
            print(f"Using latest artifacts file: {latest_file.name}")

        # DEBUG: Check the content of the JSON file
        print(f"\nDEBUG: Checking JSON file content...")
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                print(f"[OK] Successfully loaded JSON data from {latest_file.name}")
                print(f"  File size: {latest_file.stat().st_size} bytes")
                print(f"  Number of projects: {len(json_data)}")

                # Check if any projects have software lines with artifacts
                total_sw_lines = 0
                lines_with_artifacts = 0
                for project_name, project_data in json_data.items():
                    sw_lines = project_data.get('software_lines', {})
                    total_sw_lines += len(sw_lines)
                    for sw_line_name, sw_line_data in sw_lines.items():
                        if sw_line_data.get('latest_artifact'):
                            lines_with_artifacts += 1

                print(f"  Total software lines: {total_sw_lines}")
                print(f"  Software lines with artifacts: {lines_with_artifacts}")

                if lines_with_artifacts == 0:
                    print("  WARNING: No software lines have artifacts!")
                else:
                    print(f"  [OK] Found {lines_with_artifacts} software lines with artifacts")

        except Exception as e:
            exit_with_error(f"Error reading JSON file {latest_file}: {e}")

        # Step 2: Create Excel mapping
        print("\nStep 2: Creating Excel mapping")
        excel_handler = ExcelHandler()

        # Get Excel data from the copied Excel file
        print(f"Reading from: {excel_copy_path}")
        excel_data, error = excel_handler.get_excel_data(str(excel_copy_path))
        if error:
            exit_with_error(f"Error reading Excel file: {error}")

        software_lines = excel_data['software_lines']
        project_data = excel_data['project_data']

        print(f"Excel data loaded:")
        print(f"  Software lines from Excel: {len(software_lines)}")
        print(f"  Project data entries: {len(project_data)}")

        # Create mapping and generate report
        print("\nCreating mapping and generating report")
        mapping = excel_handler.create_mapping(software_lines, json_data, project_data)

        # Generate output file path using DirectoryHandler
        output_file = DirectoryHandler.get_output_file_path(EXCEL_OUTPUT_PREFIX, "xlsx")

        # Generate report
        success, error = excel_handler.generate_report(mapping, output_file)
        if not success:
            exit_with_error(f"Error generating report: {error}")

        print(f"\nWorkflow completed successfully!")
        print(f"Final report: {output_file}")

        # Step 3 (Optional): Generate validation report
        validation_report_file = None
        if GENERATE_VALIDATION_REPORT:
            validation_report_file = generate_validation_report(json_data, current_run_dir)
            if validation_report_file:
                print(f"Validation report: {validation_report_file}")

        # Open the Excel files
        if AUTO_OPEN_REPORT:
            print("\nOpening Excel file...")
            open_excel_file(output_file)
            if validation_report_file and GENERATE_VALIDATION_REPORT:
                open_excel_file(Path(validation_report_file))

        # Launch artifact viewer GUI
        if OPEN_ARTIFACT_VIEWER:
            launch_artifact_viewer(latest_file)

        print("\n=== Workflow Finished ===")

    except Exception as e:
        print(f"\nUnexpected error in workflow: {e}")
        # Print additional debug info
        import config
        print(f"DEBUG: Current config.CURRENT_RUN_DIR = {config.CURRENT_RUN_DIR}")
        return False
    return True


def resolve_excel_path(file_path: str) -> Path:
    """
    Resolve Excel file path. Handles both absolute and relative paths.
    Relative paths are resolved from the script directory.
    """
    path = Path(file_path)

    # If absolute path, use as-is
    if path.is_absolute():
        return path

    # If relative, resolve from script directory
    script_dir = Path(__file__).resolve().parent
    return (script_dir / path).resolve()


if __name__ == "__main__":
    # Determine which Excel file to use
    if len(sys.argv) >= 2:
        # Use command-line argument
        excel_file = sys.argv[1]
        print(f"Using Excel file from argument: {excel_file}")
    else:
        # Use default from configuration
        excel_file = DEFAULT_EXCEL_FILE
        print(f"No argument provided, using default: {excel_file}")

    # Resolve the path
    resolved_path = resolve_excel_path(excel_file)

    # Check if file exists
    if not resolved_path.exists():
        print(f"\nError: Excel file not found: {resolved_path}")
        print(f"\nTo fix this, either:")
        print(f"  1. Update DEFAULT_EXCEL_FILE in config.py")
        print(f"  2. Pass the file path as an argument: python run_workflow.py <excel_file>")
        sys.exit(1)

    print(f"Resolved path: {resolved_path}")

    success = run_workflow(str(resolved_path))
    sys.exit(0 if success else 1)

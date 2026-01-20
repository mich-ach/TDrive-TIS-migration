#!/usr/bin/env python3
"""
Discover unique folder names at a specific position in artifact paths.

Scans artifact paths and extracts folder names after a specified parent folder.
Useful for discovering allowed values for path convention variables.

Usage:
    python -m src.utils.discover_folders <parent_folder> [json_file]

Examples:
    # Find all folders under "Test" (TestType discovery)
    python -m src.utils.discover_folders Test

    # Find all folders under "Model/SiL"
    python -m src.utils.discover_folders SiL

    # Find all folders under "Model/HiL"
    python -m src.utils.discover_folders HiL

    # With specific JSON file
    python -m src.utils.discover_folders Test /path/to/artifacts.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, Optional, List


def find_latest_json(output_dir: Path) -> Optional[Path]:
    """Find the latest artifacts JSON file in output directory."""
    if not output_dir.exists():
        return None

    run_dirs = sorted(output_dir.glob("run_*"), reverse=True)
    for run_dir in run_dirs:
        json_files = list(run_dir.glob("*_artifacts_*.json"))
        if json_files:
            return sorted(json_files, reverse=True)[0]

    return None


def extract_folder_after(path: str, parent_folder: str) -> Optional[str]:
    """
    Extract the folder name immediately after the specified parent folder.

    Args:
        path: The full path (e.g., "Project/SWLine/Model/SiL/vVeh/...")
        parent_folder: The folder to look for (e.g., "SiL")

    Returns:
        The folder name after parent_folder, or None if not found
    """
    if not path:
        return None

    parts = path.split('/')
    for i, part in enumerate(parts):
        if part == parent_folder and i + 1 < len(parts):
            return parts[i + 1]

    return None


def discover_folders(json_file: Path, parent_folder: str) -> Dict[str, Set[str]]:
    """
    Discover all unique folder names after the specified parent folder.

    Returns:
        Dict mapping: folder_name -> Set of full paths where it was found
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # folder_name -> Set of example paths
    results: Dict[str, Set[str]] = defaultdict(set)

    for project_name, project_data in data.items():
        if not isinstance(project_data, dict) or 'software_lines' not in project_data:
            continue

        for sw_line_name, sw_line_data in project_data.get('software_lines', {}).items():
            if not isinstance(sw_line_data, dict):
                continue

            artifacts = sw_line_data.get('artifacts', [])
            if sw_line_data.get('latest_artifact'):
                artifacts = [sw_line_data['latest_artifact']] + artifacts

            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue

                upload_path = artifact.get('upload_path', '')
                folder_name = extract_folder_after(upload_path, parent_folder)

                if folder_name:
                    # Store a truncated example path
                    parts = upload_path.split('/')
                    if len(parts) > 6:
                        example = '/'.join(parts[:6]) + '/...'
                    else:
                        example = upload_path
                    results[folder_name].add(example)

    return results


def print_results(results: Dict[str, Set[str]], parent_folder: str) -> None:
    """Print discovered folders in a readable format."""
    sorted_folders = sorted(results.keys())

    print("\n" + "=" * 60)
    print(f"FOLDERS FOUND UNDER '{parent_folder}/'")
    print("=" * 60)

    # Print as Python list
    print(f"\nUnique folders ({len(sorted_folders)}):")
    print(f'"{parent_folder}_values": {sorted_folders}')

    # Print with example paths
    print("\n" + "-" * 60)
    print("DETAILS WITH EXAMPLE PATHS")
    print("-" * 60)

    for folder_name in sorted_folders:
        examples = sorted(results[folder_name])[:3]  # Show max 3 examples
        print(f"\n{folder_name}/")
        for ex in examples:
            print(f"  Example: {ex}")

    # Print for config.json
    print("\n" + "=" * 60)
    print("FOR CONFIG.JSON")
    print("=" * 60)
    print(f'\n"{parent_folder}Type": {sorted_folders}')


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.utils.discover_folders <parent_folder> [json_file]")
        print("\nExamples:")
        print("  python -m src.utils.discover_folders Test      # Find TestTypes")
        print("  python -m src.utils.discover_folders SiL       # Find SiL subfolders")
        print("  python -m src.utils.discover_folders HiL       # Find HiL subfolders")
        print("  python -m src.utils.discover_folders vVeh      # Find vVeh subfolders")
        sys.exit(1)

    parent_folder = sys.argv[1]

    # Determine paths
    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent
    project_dir = src_dir.parent
    output_dir = project_dir / "output"

    # Get JSON file
    if len(sys.argv) > 2:
        json_file = Path(sys.argv[2])
    else:
        json_file = find_latest_json(output_dir)
        if not json_file:
            print("Error: No artifacts JSON file found in output/")
            print("Provide a JSON file path as second argument")
            sys.exit(1)

    if not json_file.exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)

    print(f"Scanning: {json_file}")
    print(f"Looking for folders under: {parent_folder}/")

    results = discover_folders(json_file, parent_folder)

    if not results:
        print(f"\nNo folders found under '{parent_folder}/'")
        print("Make sure the artifacts have paths with this folder.")
    else:
        print_results(results, parent_folder)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Discover all TestType folders from TIS artifact data.

Scans artifact paths to find unique TestType values following the pattern:
{Project}/{SoftwareLine}/Test/{TestType}/...

Usage:
    python -m src.utils.discover_test_types [json_file]

If no JSON file is provided, uses the latest artifacts file from output/.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Optional


def find_latest_json(output_dir: Path) -> Optional[Path]:
    """Find the latest artifacts JSON file in output directory."""
    if not output_dir.exists():
        return None

    # Look for run directories
    run_dirs = sorted(output_dir.glob("run_*"), reverse=True)
    for run_dir in run_dirs:
        # Find any artifacts JSON file
        json_files = list(run_dir.glob("*_artifacts_*.json"))
        if json_files:
            return sorted(json_files, reverse=True)[0]

    return None


def extract_test_type_from_path(path: str) -> Optional[str]:
    """
    Extract TestType from path following pattern:
    {Project}/{SoftwareLine}/Test/{TestType}/...

    Returns the folder name immediately after 'Test'.
    """
    if not path:
        return None

    parts = path.split('/')
    for i, part in enumerate(parts):
        if part == 'Test' and i + 1 < len(parts):
            return parts[i + 1]

    return None


def discover_test_types(json_file: Path) -> Dict[str, Dict[str, Set[str]]]:
    """
    Discover all TestType folders from artifact data.

    Returns:
        Dict mapping: Project -> SoftwareLine -> Set of TestTypes
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Structure: Project -> SoftwareLine -> Set[TestType]
    results: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))

    for project_name, project_data in data.items():
        if not isinstance(project_data, dict) or 'software_lines' not in project_data:
            continue

        for sw_line_name, sw_line_data in project_data.get('software_lines', {}).items():
            if not isinstance(sw_line_data, dict):
                continue

            # Check all artifacts
            artifacts = sw_line_data.get('artifacts', [])
            if sw_line_data.get('latest_artifact'):
                artifacts = [sw_line_data['latest_artifact']] + artifacts

            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue

                upload_path = artifact.get('upload_path', '')
                test_type = extract_test_type_from_path(upload_path)

                if test_type:
                    results[project_name][sw_line_name].add(test_type)

    return results


def print_results(results: Dict[str, Dict[str, Set[str]]]) -> None:
    """Print discovered TestTypes in a readable format."""
    # Collect all unique test types
    all_test_types: Set[str] = set()
    for project_data in results.values():
        for test_types in project_data.values():
            all_test_types.update(test_types)

    print("\n" + "=" * 60)
    print("DISCOVERED TEST TYPES")
    print("=" * 60)

    # Print unique test types as Python list
    sorted_types = sorted(all_test_types)
    print(f"\nUnique TestTypes found ({len(sorted_types)}):")
    print(f"TEST_TYPES = {sorted_types}")

    # Print detailed breakdown
    print("\n" + "-" * 60)
    print("BREAKDOWN BY PROJECT / SOFTWARE LINE")
    print("-" * 60)

    for project_name in sorted(results.keys()):
        project_data = results[project_name]
        print(f"\n{project_name}/")

        for sw_line_name in sorted(project_data.keys()):
            test_types = sorted(project_data[sw_line_name])
            print(f"  {sw_line_name}/Test/")
            for tt in test_types:
                print(f"    - {tt}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_projects = len(results)
    total_sw_lines = sum(len(p) for p in results.values())
    print(f"Projects with Test folders: {total_projects}")
    print(f"Software Lines with Test folders: {total_sw_lines}")
    print(f"Unique TestTypes: {len(all_test_types)}")
    print(f"\nPython list for config.json:")
    print(f'"TestType": {sorted_types}')


def main():
    # Determine script location and output directory
    script_dir = Path(__file__).resolve().parent
    src_dir = script_dir.parent
    project_dir = src_dir.parent
    output_dir = project_dir / "output"

    # Get JSON file from argument or find latest
    if len(sys.argv) > 1:
        json_file = Path(sys.argv[1])
    else:
        json_file = find_latest_json(output_dir)
        if not json_file:
            print("Error: No artifacts JSON file found in output/")
            print("Usage: python -m src.utils.discover_test_types [json_file]")
            sys.exit(1)

    if not json_file.exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)

    print(f"Scanning: {json_file}")

    results = discover_test_types(json_file)

    if not results:
        print("\nNo Test folders found in artifact paths.")
        print("Make sure the artifacts have paths with /Test/{TestType}/ pattern.")
    else:
        print_results(results)


if __name__ == "__main__":
    main()

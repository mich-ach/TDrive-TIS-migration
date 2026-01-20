#!/usr/bin/env python3
"""
Discover all TestType folders from TIS using recursive API calls.

Searches the tree structure recursively following the pattern:
{Project}/{SoftwareLine}/Test/{TestType}/...

Usage:
    python -m src.utils.discover_test_types
"""

import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, List, Any

# Add src to path for imports
script_dir = Path(__file__).resolve().parent
src_dir = script_dir.parent
sys.path.insert(0, str(src_dir))

from Api import TISClient
from config import VW_XCU_PROJECT_ID


def find_test_types_in_tree(
    data: Dict[str, Any],
    results: Dict[str, Set[str]],
    path: List[str]
) -> None:
    """
    Recursively find TestType folders in the component tree.
    TestTypes are folders directly under a 'Test' folder.

    Args:
        data: TIS component data
        results: Dict to store results (folder_name -> set of paths)
        path: Current path as list of folder names
    """
    name = data.get('name', '')
    current_path = path + [name] if name else path

    # Check if parent was "Test" - then this is a TestType
    if len(path) > 0 and path[-1] == 'Test':
        path_str = '/'.join(current_path)
        results[name].add(path_str)

    # Recurse into children
    children = data.get('children', [])
    for child in children:
        find_test_types_in_tree(child, results, current_path)


def discover_test_types_recursive(client: TISClient) -> Dict[str, Set[str]]:
    """
    Discover TestType folders using recursive API calls.

    Follows the structure: Project/SoftwareLine/Test/TestType

    Returns:
        Dict mapping TestType name -> Set of example paths
    """
    results: Dict[str, Set[str]] = defaultdict(set)

    # Step 1: Get all projects
    print(f"Fetching projects from root: {VW_XCU_PROJECT_ID}")
    root_data, timed_out, elapsed = client.get_component(
        VW_XCU_PROJECT_ID, children_level=1
    )

    if timed_out or not root_data:
        print(f"Error: Failed to fetch root project (elapsed: {elapsed:.1f}s)")
        return results

    projects = root_data.get('children', [])
    print(f"Found {len(projects)} projects ({elapsed:.1f}s)")

    # Step 2: For each project, get software lines
    for proj_idx, project in enumerate(projects, 1):
        project_name = project.get('name', 'Unknown')
        project_id = project.get('rId')

        if not project_id:
            continue

        print(f"  [{proj_idx}/{len(projects)}] Project: {project_name}")

        proj_data, timed_out, _ = client.get_component(project_id, children_level=1)
        if timed_out or not proj_data:
            continue

        software_lines = proj_data.get('children', [])

        # Step 3: For each software line, look for Test folder
        for sw_line in software_lines:
            sw_line_name = sw_line.get('name', 'Unknown')
            sw_line_id = sw_line.get('rId')

            if not sw_line_id:
                continue

            # Fetch software line with depth 3 to get Test/TestType level
            # Structure: SWLine -> Test -> TestType -> ...
            sw_data, timed_out, _ = client.get_component(sw_line_id, children_level=3)
            if timed_out or not sw_data:
                continue

            # Look for Test folder
            sw_children = sw_data.get('children', [])
            for child in sw_children:
                child_name = child.get('name', '')
                if child_name == 'Test':
                    # Found Test folder - get its children (TestTypes)
                    test_children = child.get('children', [])
                    for test_type in test_children:
                        test_type_name = test_type.get('name', '')
                        if test_type_name:
                            full_path = f"{project_name}/{sw_line_name}/Test/{test_type_name}"
                            results[test_type_name].add(full_path)

    return results


def print_results(results: Dict[str, Set[str]]) -> None:
    """Print discovered TestTypes."""
    sorted_types = sorted(results.keys())

    print("\n" + "=" * 60)
    print("DISCOVERED TEST TYPES")
    print("=" * 60)

    print(f"\nUnique TestTypes found ({len(sorted_types)}):")
    print(f"TEST_TYPES = {sorted_types}")

    print("\n" + "-" * 60)
    print("EXAMPLE PATHS")
    print("-" * 60)

    for folder_name in sorted_types:
        examples = sorted(results[folder_name])[:3]
        print(f"\n{folder_name}/ ({len(results[folder_name])} occurrences)")
        for ex in examples:
            print(f"  {ex}")

    print("\n" + "=" * 60)
    print("FOR CONFIG.JSON")
    print("=" * 60)
    print(f'\n"TestType": {sorted_types}')


def main():
    print("TIS TestType Discovery Tool")
    print("=" * 60)
    print(f"Root project ID: {VW_XCU_PROJECT_ID}")
    print("Pattern: {Project}/{SoftwareLine}/Test/{TestType}")
    print("=" * 60 + "\n")

    client = TISClient(children_level=3)
    results = discover_test_types_recursive(client)

    if not results:
        print("\nNo TestType folders found.")
    else:
        print_results(results)


# Backwards compatibility aliases
discover_test_types_from_api = discover_test_types_recursive
find_test_type_folders = find_test_types_in_tree


if __name__ == "__main__":
    main()

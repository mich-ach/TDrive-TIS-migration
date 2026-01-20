#!/usr/bin/env python3
"""
Discover unique folder names under a specific parent folder using recursive TIS API calls.

Searches the tree structure recursively to find all folders
that appear directly under the specified parent folder.

Usage:
    python -m src.utils.discover_folders <parent_folder>

Examples:
    python -m src.utils.discover_folders Test      # Find TestTypes
    python -m src.utils.discover_folders SiL       # Find SiL subfolders
    python -m src.utils.discover_folders vVeh      # Find vVeh subfolders
    python -m src.utils.discover_folders HiL       # Find HiL subfolders
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


def find_folders_in_tree(
    data: Dict[str, Any],
    parent_folder: str,
    results: Dict[str, Set[str]],
    path: List[str]
) -> None:
    """
    Recursively find folders directly under the specified parent folder.

    Args:
        data: TIS component data
        parent_folder: The folder name to look for (e.g., "Test", "SiL")
        results: Dict to store results (folder_name -> set of paths)
        path: Current path as list of folder names
    """
    name = data.get('name', '')
    current_path = path + [name] if name else path

    # Check if parent was the target folder
    if len(path) > 0 and path[-1] == parent_folder:
        path_str = '/'.join(current_path)
        results[name].add(path_str)

    # Recurse into children
    children = data.get('children', [])
    for child in children:
        find_folders_in_tree(child, parent_folder, results, current_path)


def discover_folders_recursive(
    client: TISClient,
    parent_folder: str,
    search_depth: int = 4
) -> Dict[str, Set[str]]:
    """
    Discover folders under parent_folder using recursive API calls.

    Follows the structure: Project/SoftwareLine/.../parent_folder/target

    Args:
        client: TISClient instance
        parent_folder: The folder to search under (e.g., "Test", "SiL", "vVeh")
        search_depth: Depth to search within each software line

    Returns:
        Dict mapping folder_name -> Set of example paths
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

        # Step 3: For each software line, search for parent_folder
        for sw_line in software_lines:
            sw_line_name = sw_line.get('name', 'Unknown')
            sw_line_id = sw_line.get('rId')

            if not sw_line_id:
                continue

            # Fetch software line with enough depth to find parent_folder and its children
            sw_data, timed_out, _ = client.get_component(sw_line_id, children_level=search_depth)
            if timed_out or not sw_data:
                continue

            # Recursively find folders under parent_folder
            find_folders_in_tree(
                sw_data,
                parent_folder,
                results,
                [project_name, sw_line_name]
            )

    return results


def print_results(results: Dict[str, Set[str]], parent_folder: str) -> None:
    """Print discovered folders."""
    sorted_folders = sorted(results.keys())

    print("\n" + "=" * 60)
    print(f"FOLDERS FOUND UNDER '{parent_folder}/'")
    print("=" * 60)

    print(f"\nUnique folders ({len(sorted_folders)}):")
    print(f'FOLDERS = {sorted_folders}')

    print("\n" + "-" * 60)
    print("EXAMPLE PATHS")
    print("-" * 60)

    for folder_name in sorted_folders:
        examples = sorted(results[folder_name])[:3]
        print(f"\n{folder_name}/ ({len(results[folder_name])} occurrences)")
        for ex in examples:
            print(f"  {ex}")

    print("\n" + "=" * 60)
    print("FOR CONFIG.JSON")
    print("=" * 60)
    print(f'\n"{parent_folder}Type": {sorted_folders}')


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.utils.discover_folders <parent_folder> [search_depth]")
        print("\nExamples:")
        print("  python -m src.utils.discover_folders Test   # Find TestTypes")
        print("  python -m src.utils.discover_folders SiL    # Find SiL subfolders")
        print("  python -m src.utils.discover_folders vVeh   # Find vVeh subfolders")
        print("  python -m src.utils.discover_folders HiL    # Find HiL subfolders")
        sys.exit(1)

    parent_folder = sys.argv[1]
    search_depth = 4

    if len(sys.argv) > 2:
        try:
            search_depth = int(sys.argv[2])
        except ValueError:
            print(f"Invalid search_depth: {sys.argv[2]}")
            sys.exit(1)

    print("TIS Folder Discovery Tool")
    print("=" * 60)
    print(f"Root project ID: {VW_XCU_PROJECT_ID}")
    print(f"Looking for folders under: {parent_folder}/")
    print(f"Search depth: {search_depth}")
    print("=" * 60 + "\n")

    client = TISClient(children_level=search_depth)
    results = discover_folders_recursive(client, parent_folder, search_depth)

    if not results:
        print(f"\nNo folders found under '{parent_folder}/'")
        print("Try increasing search_depth for deeper search.")
    else:
        print_results(results, parent_folder)


if __name__ == "__main__":
    main()

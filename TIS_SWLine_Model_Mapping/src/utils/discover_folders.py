#!/usr/bin/env python3
"""
Discover unique folder names under a specific parent folder using TIS API.

Makes a single API call to fetch the project tree and finds all folders
that appear directly under the specified parent folder.

Usage:
    python -m src.utils.discover_folders <parent_folder> [children_level]

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


def find_folders_under_parent(
    component: Dict[str, Any],
    parent_folder: str,
    results: Dict[str, Set[str]],
    path: List[str] = None
) -> None:
    """
    Recursively find folders directly under the specified parent folder.

    Args:
        component: TIS component data
        parent_folder: The folder name to look for (e.g., "Test", "SiL")
        results: Dict to store results (folder_name -> set of paths)
        path: Current path as list of folder names
    """
    if path is None:
        path = []

    name = component.get('name', '')
    current_path = path + [name] if name else path

    # Check if parent was the target folder
    if len(path) > 0 and path[-1] == parent_folder:
        path_str = '/'.join(current_path)
        results[name].add(path_str)

    # Recurse into children
    children = component.get('children', [])
    for child in children:
        find_folders_under_parent(child, parent_folder, results, current_path)


def discover_folders_from_api(parent_folder: str, children_level: int = 6) -> Dict[str, Set[str]]:
    """
    Discover folders under parent_folder by fetching from TIS API.

    Args:
        parent_folder: The folder to search under (e.g., "Test", "SiL")
        children_level: Depth of children to fetch

    Returns:
        Dict mapping folder_name -> Set of example paths
    """
    print(f"Fetching TIS data (children_level={children_level})...")
    print(f"Root project ID: {VW_XCU_PROJECT_ID}")
    print(f"Looking for folders under: {parent_folder}/")

    client = TISClient(children_level=children_level)
    data, timed_out, elapsed = client.get_component(
        VW_XCU_PROJECT_ID,
        children_level=children_level,
        use_cache=False
    )

    if timed_out or not data:
        print(f"Error: API call failed or timed out (elapsed: {elapsed:.1f}s)")
        return {}

    print(f"API call completed in {elapsed:.1f}s")

    # Find all folders under the parent
    results: Dict[str, Set[str]] = defaultdict(set)
    find_folders_under_parent(data, parent_folder, results)

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
        examples = sorted(results[folder_name])[:2]
        print(f"\n{folder_name}/")
        for ex in examples:
            print(f"  {ex}")

    print("\n" + "=" * 60)
    print("FOR CONFIG.JSON")
    print("=" * 60)
    print(f'\n"{parent_folder}Type": {sorted_folders}')


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.utils.discover_folders <parent_folder> [children_level]")
        print("\nExamples:")
        print("  python -m src.utils.discover_folders Test   # Find TestTypes")
        print("  python -m src.utils.discover_folders SiL    # Find SiL subfolders")
        print("  python -m src.utils.discover_folders vVeh   # Find vVeh subfolders")
        print("  python -m src.utils.discover_folders HiL    # Find HiL subfolders")
        sys.exit(1)

    parent_folder = sys.argv[1]
    children_level = 6

    if len(sys.argv) > 2:
        try:
            children_level = int(sys.argv[2])
        except ValueError:
            print(f"Invalid children_level: {sys.argv[2]}")
            sys.exit(1)

    results = discover_folders_from_api(parent_folder, children_level)

    if not results:
        print(f"\nNo folders found under '{parent_folder}/'")
        print("Try increasing children_level for deeper search.")
    else:
        print_results(results, parent_folder)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Discover all TestType folders from TIS using a single API call.

Fetches the root project with children and finds all unique folder names
under Test/ folders following the pattern:
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
from config import ROOT_PROJECT_ID


def find_test_type_folders(component: Dict[str, Any], results: Dict[str, Set[str]], path: List[str] = None) -> None:
    """
    Recursively find TestType folders under Test/ in the component tree.

    Args:
        component: TIS component data
        results: Dict to store results (folder_name -> set of paths)
        path: Current path as list of folder names
    """
    if path is None:
        path = []

    name = component.get('name', '')
    current_path = path + [name] if name else path

    # Check if parent was "Test" - then this is a TestType
    if len(path) > 0 and path[-1] == 'Test':
        # This folder is directly under Test, so it's a TestType
        path_str = '/'.join(current_path)
        results[name].add(path_str)

    # Recurse into children
    children = component.get('children', [])
    for child in children:
        find_test_type_folders(child, results, current_path)


def discover_test_types_from_api(children_level: int = 6) -> Dict[str, Set[str]]:
    """
    Discover TestType folders by fetching from TIS API.

    Args:
        children_level: Depth of children to fetch (higher = more complete, slower)

    Returns:
        Dict mapping folder_name -> Set of example paths
    """
    print(f"Fetching TIS data (children_level={children_level})...")
    print(f"Root project ID: {ROOT_PROJECT_ID}")

    client = TISClient(children_level=children_level)
    data, timed_out, elapsed = client.get_component(
        ROOT_PROJECT_ID,
        children_level=children_level,
        use_cache=False
    )

    if timed_out or not data:
        print(f"Error: API call failed or timed out (elapsed: {elapsed:.1f}s)")
        return {}

    print(f"API call completed in {elapsed:.1f}s")

    # Find all TestType folders
    results: Dict[str, Set[str]] = defaultdict(set)
    find_test_type_folders(data, results)

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
        examples = sorted(results[folder_name])[:2]
        print(f"\n{folder_name}/")
        for ex in examples:
            print(f"  {ex}")

    print("\n" + "=" * 60)
    print("FOR CONFIG.JSON")
    print("=" * 60)
    print(f'\n"TestType": {sorted_types}')


def main():
    # Use higher children_level for more complete results
    children_level = 6
    if len(sys.argv) > 1:
        try:
            children_level = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python -m src.utils.discover_test_types [children_level]")
            print(f"  children_level: Depth of API fetch (default: 6)")
            sys.exit(1)

    results = discover_test_types_from_api(children_level)

    if not results:
        print("\nNo TestType folders found.")
        print("Try increasing children_level for deeper search.")
    else:
        print_results(results)


if __name__ == "__main__":
    main()

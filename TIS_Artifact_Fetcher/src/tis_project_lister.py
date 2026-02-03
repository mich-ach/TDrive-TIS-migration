"""
TIS Project Lister - Generates a CSV of projects and software lines from TIS.

Connects to the TIS API, traverses the project tree, and outputs a CSV file
listing all projects and their software lines. This CSV can be used as input
for vVeh_LCO_Mapping instead of the master Excel file.

Usage:
    python -m src.tis_project_lister
    python -m src.tis_project_lister --output my_projects.csv

Output CSV format (semicolon-delimited):
    Project line;ECU - HW Variante;Project class
    SoftwareLine1;;ProjectA
    SoftwareLine2;;ProjectA
    SoftwareLine3;;ProjectB
"""

import argparse
import datetime
import logging
import sys
from pathlib import Path

from Api import TISClient
from config import (
    VW_XCU_PROJECT_ID,
    SKIP_PROJECTS,
    INCLUDE_PROJECTS,
    LOG_LEVEL,
    OUTPUT_DIR,
)

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

_console_handler = logging.StreamHandler()
_console_level = getattr(logging, LOG_LEVEL, logging.INFO)
_console_handler.setLevel(_console_level)
_console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
))
logger.addHandler(_console_handler)

# CSV column headers (matching Excel master format for vVeh_LCO_Mapping compatibility)
CSV_HEADERS = ["Project line", "ECU - HW Variante", "Project class"]


def list_projects_and_software_lines(client: TISClient) -> list:
    """
    Traverse TIS project tree and collect all project/software line pairs.

    Args:
        client: Initialized TISClient instance

    Returns:
        List of dicts with keys: project_line, ecu_hw_variante, project_class
    """
    entries = []

    logger.info(f"Fetching root project (ID: {VW_XCU_PROJECT_ID})...")
    root_data, _, _ = client.get_component(VW_XCU_PROJECT_ID, children_level=1)

    if not root_data:
        logger.error("Failed to fetch root project from TIS API")
        return entries

    projects = root_data.get('children', [])
    total_projects = len(projects)
    logger.info(f"Found {total_projects} projects")

    for project_idx, project in enumerate(projects, 1):
        project_id = project.get('rId')
        project_name = project.get('name', 'Unknown')

        # Apply same filtering as ArtifactFetcher
        if project_name in SKIP_PROJECTS:
            logger.debug(f"[{project_idx}/{total_projects}] Skipping: {project_name}")
            continue

        if INCLUDE_PROJECTS and project_name not in INCLUDE_PROJECTS:
            logger.debug(f"[{project_idx}/{total_projects}] Skipping: {project_name}")
            continue

        logger.info(f"[{project_idx}/{total_projects}] {project_name}")

        # Fetch software lines (direct children of project)
        project_data, _, _ = client.get_component(project_id, children_level=1)
        if not project_data:
            logger.warning(f"  Failed to fetch project data for {project_name}")
            continue

        software_lines = project_data.get('children', [])
        logger.info(f"  {len(software_lines)} software lines")

        for sw_line in software_lines:
            sw_line_name = sw_line.get('name', '')
            if sw_line_name:
                entries.append({
                    "Project line": sw_line_name,
                    "ECU - HW Variante": "",
                    "Project class": project_name
                })

    return entries


def write_csv(entries: list, output_path: Path) -> None:
    """
    Write project/software line entries to a semicolon-delimited CSV.

    Args:
        entries: List of dicts with CSV_HEADERS keys
        output_path: Path to write the CSV file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(';'.join(CSV_HEADERS) + '\n')
        for entry in entries:
            values = [entry.get(h, '') for h in CSV_HEADERS]
            f.write(';'.join(values) + '\n')

    logger.info(f"CSV written: {output_path} ({len(entries)} entries)")


def main():
    parser = argparse.ArgumentParser(
        description="Generate CSV of TIS projects and software lines"
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help="Output CSV path (default: output/tis_projects_<timestamp>.csv)"
    )
    args = parser.parse_args()

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = OUTPUT_DIR / f"tis_projects_{timestamp}.csv"

    logger.info("=" * 60)
    logger.info("TIS Project Lister")
    logger.info("=" * 60)

    # Initialize TIS client
    client = TISClient(enable_cache=True)

    # Collect data
    entries = list_projects_and_software_lines(client)

    if not entries:
        logger.warning("No entries found. Check API connectivity and config.")
        sys.exit(1)

    # Summary
    unique_projects = len(set(e["Project class"] for e in entries))
    logger.info(f"Total: {len(entries)} software lines across {unique_projects} projects")

    # Write CSV
    write_csv(entries, output_path)

    logger.info("=" * 60)
    logger.info(f"Done. Output: {output_path}")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()

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

Output:
- {component_type}_artifacts_{timestamp}.json - Artifacts grouped by component type
- latest_{component_type}_artifacts_{timestamp}.json - Latest artifact per software line

Usage:
    python -m TIS_SWLine_Model_Mapping [--gui]

    --gui: Open the artifact viewer GUI after extraction

Configuration:
    All settings are in config.json:
    - artifact_filters: Filter by component_type, component_name, etc.
    - branch_pruning: Skip unnecessary folders
    - optimization: Concurrent requests, caching settings
"""

import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from Fetchers import run_extraction as fetch_artifacts

import config
from config import (
    LOG_LEVEL,
    OPEN_ARTIFACT_VIEWER,
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

        if not fetch_artifacts():
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

        # Launch GUI if requested
        if open_gui or OPEN_ARTIFACT_VIEWER:
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

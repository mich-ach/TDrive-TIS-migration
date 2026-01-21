"""
TDrive Artifact Fetcher - Main entry point.

This script performs the complete artifact extraction and migration workflow:
1. Scans network drive for LCO 5.4.5 and 5.4.11 artifacts
2. Extracts metadata from Model_Overview.html in each zip file
3. Exports artifact lists to JSON in the output/ directory
4. Transforms missing PVER Excel export to CSV
5. Maps artifacts to missing PVER entries
6. Generates migration JSON for TIS upload

Usage:
    python -m TDrive_Artifact_Fetcher

Requirements:
    - Network drive access to LCO_Projects directory
    - missing.xlsx in the input/ directory
    - config.json in the project root
"""
import logging
import os
import sys

from Artifacts import Artifact545, Artifact5411, INPUT_DIR, OUTPUT_DIR, LOG_LEVEL
from Check import Check

# Setup logging for main module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Console handler with level from config
_console_handler = logging.StreamHandler()
_console_level = getattr(logging, LOG_LEVEL, logging.INFO)
_console_handler.setLevel(_console_level)
_console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
))
logger.addHandler(_console_handler)


if __name__ == '__main__':
    logger.info(f"Input directory: {INPUT_DIR}")
    logger.info(f"Output directory: {OUTPUT_DIR}")

    # Construct paths using config values
    input_excel = os.path.join(INPUT_DIR, "missing.xlsx")
    input_csv = os.path.join(INPUT_DIR, "missing.csv")
    output_545 = os.path.join(OUTPUT_DIR, "545list.json")
    output_5411 = os.path.join(OUTPUT_DIR, "5411list.json")
    output_check = os.path.join(OUTPUT_DIR, "check.json")

    # Initialize and process 5.4.5 artifacts
    art545 = Artifact545()
    art545.start_logging()
    logger.info("Processing 5.4.5 artifacts...")
    art545.create_dir()
    art545.cleanup_dir()
    art545.dump_dir()
    art545.create_list()
    art545.cleanup_list()
    art545.dump_list()
    art545.stop_logging()
    logger.info("5.4.5 artifact processing complete.")

    # Initialize and process 5.4.11 artifacts
    art5411 = Artifact5411()
    art5411.start_logging()
    logger.info("Processing 5.4.11 artifacts...")
    art5411.create_dir()
    art5411.cleanup_dir()
    art5411.dump_dir()
    art5411.create_list()
    art5411.cleanup_list()
    art5411.dump_list()
    art5411.stop_logging()
    logger.info("5.4.11 artifact processing complete.")

    # Transform the missing PVER Excel export to CSV
    logger.info(f"Transforming '{os.path.basename(input_excel)}' to CSV...")
    Check.transform_excel(input_excel, input_csv)
    logger.info("Excel to CSV transformation complete.")

    # Perform comparison and generate migration JSON
    logger.info("Comparing artifacts with missing PVER entries...")
    check = Check([output_545, output_5411], input_csv)
    check.compare()
    check.dump()  # Will use OUTPUT_DIR from config by default
    logger.info("Comparison complete. Results dumped to 'check.json'.")

    # Create the final migration JSON for TIS upload
    logger.info("Generating migration JSON for TIS upload...")
    Check.create_mig(output_check)  # Will use OUTPUT_DIR from config by default
    logger.info("Migration JSON generated.")

    logger.info("TDrive Artifact Fetcher workflow completed successfully!")
    logger.info(f"All output files saved to: {OUTPUT_DIR}")

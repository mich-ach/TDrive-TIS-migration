"""Abstraction layer for reading software line input data.

Supports both Excel (.xlsx) and CSV (.csv) input formats, returning
a unified data structure for the mapping workflow.

The CSV format is semicolon-delimited with headers:
    Project line;ECU - HW Variante;Project class

This matches the output of TIS_Artifact_Fetcher/src/tis_project_lister.py.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .excel_reader import ExcelReader

logger = logging.getLogger(__name__)


class InputReader:
    """
    Reads software line data from either Excel or CSV files.

    Returns a unified format regardless of input type:
        {
            'software_lines': ['line1', 'line2', ...],
            'project_data': {
                'line1': {'ECU - HW Variante': '...', 'Project class': '...'},
                'line2': {'ECU - HW Variante': '...', 'Project class': '...'},
            }
        }
    """

    def __init__(self):
        self._excel_reader = ExcelReader()

    def read(
        self, file_path: str, sheet_name: Optional[str] = None
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Read software line data from file, auto-detecting format.

        Args:
            file_path: Path to Excel (.xlsx) or CSV (.csv) file
            sheet_name: Sheet name for Excel files (ignored for CSV)

        Returns:
            Tuple of (data_dict, error_message)
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == '.csv':
            logger.info(f"Reading CSV input: {path.name}")
            return self._read_csv(str(path))
        elif suffix in ('.xlsx', '.xls'):
            logger.info(f"Reading Excel input: {path.name}")
            return self._excel_reader.get_excel_data(str(path), sheet_name)
        else:
            return {}, f"Unsupported file format: '{suffix}'. Expected .xlsx or .csv"

    def _read_csv(self, file_path: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Read software line data from a semicolon-delimited CSV.

        Expected CSV format:
            Project line;ECU - HW Variante;Project class

        Args:
            file_path: Path to CSV file

        Returns:
            Tuple of (data_dict, error_message)
        """
        try:
            software_lines = []
            project_data = {}

            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')

                # Validate headers
                if not reader.fieldnames:
                    return {}, "CSV file is empty or has no headers"

                has_project_line = any(
                    h.strip().lower() == 'project line'
                    for h in reader.fieldnames
                )
                if not has_project_line:
                    return {}, (
                        f"CSV missing required 'Project line' column. "
                        f"Found headers: {reader.fieldnames}"
                    )

                # Normalize header names for lookup
                header_map = {}
                for h in reader.fieldnames:
                    header_map[h.strip().lower()] = h

                pl_key = header_map.get('project line', '')
                ecu_key = header_map.get('ecu - hw variante', '')
                pc_key = header_map.get('project class', '')

                row_count = 0
                for row in reader:
                    project_line = row.get(pl_key, '').strip()
                    if not project_line:
                        continue

                    row_count += 1
                    software_lines.append(project_line)

                    ecu_value = row.get(ecu_key, '').strip() if ecu_key else ''
                    pc_value = row.get(pc_key, '').strip() if pc_key else ''

                    project_data[project_line] = {
                        "ECU - HW Variante": ecu_value,
                        "Project class": pc_value
                    }

            logger.info(f"CSV data loaded: {row_count} software lines")

            if project_data:
                logger.debug("Sample CSV entries (first 3):")
                for key in list(project_data.keys())[:3]:
                    logger.debug(f"  {key}: {project_data[key]}")

            result = {
                'software_lines': software_lines,
                'project_data': project_data
            }

            return result, None

        except Exception as e:
            logger.error(f"Error reading CSV file: {e}")
            return {}, f"Error reading CSV file: {e}"

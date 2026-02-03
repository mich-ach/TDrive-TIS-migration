"""Abstraction layer for reading software line input data.

Supports both Excel (.xlsx) and CSV (.csv) input formats, returning
a unified data structure for the mapping workflow.

The CSV format is semicolon-delimited with headers:
    Project line;ECU - HW Variante;Project class

This matches the output of TIS_Artifact_Fetcher/src/tis_project_lister.py.
"""

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

    DELIMITER = ";"

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
                lines = f.read().splitlines()

            if not lines:
                return {}, "CSV file is empty"

            # Parse headers
            headers = [h.strip() for h in lines[0].split(self.DELIMITER)]

            header_lower = {h.lower(): i for i, h in enumerate(headers)}
            if 'project line' not in header_lower:
                return {}, (
                    f"CSV missing required 'Project line' column. "
                    f"Found headers: {headers}"
                )

            pl_idx = header_lower['project line']
            ecu_idx = header_lower.get('ecu - hw variante')
            pc_idx = header_lower.get('project class')

            row_count = 0
            for line in lines[1:]:
                if not line.strip():
                    continue

                fields = line.split(self.DELIMITER)
                project_line = fields[pl_idx].strip() if pl_idx < len(fields) else ''
                if not project_line:
                    continue

                row_count += 1
                software_lines.append(project_line)

                ecu_value = fields[ecu_idx].strip() if ecu_idx is not None and ecu_idx < len(fields) else ''
                pc_value = fields[pc_idx].strip() if pc_idx is not None and pc_idx < len(fields) else ''

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

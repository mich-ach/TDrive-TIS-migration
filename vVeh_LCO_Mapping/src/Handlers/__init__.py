"""Handler classes for directory and Excel operations.

This module provides classes for managing directories and Excel file operations.

Classes:
    DirectoryHandler: Handles directory operations for the TIS artifact extraction workflow
    ExcelHandler: Facade combining Excel reading, mapping, and report generation
    ExcelReader: Handles reading data from Excel files
    MappingHandler: Handles software line matching and mapping
    ReportGenerator: Generates Excel reports for mapping results
"""

from .directory_handler import DirectoryHandler
from .excel_reader import ExcelReader
from .mapping_handler import MappingHandler
from .report_generator import ReportGenerator


class ExcelHandler:
    """
    Facade class combining Excel reading, mapping, and report generation.

    This class provides backward compatibility with the original monolithic
    ExcelHandler while delegating to specialized handler classes.
    """

    def __init__(self):
        self._reader = ExcelReader()
        self._mapper = MappingHandler()
        self._reporter = ReportGenerator()
        self.openpyxl_available = self._reader.openpyxl_available

    # Excel reading methods (delegated to ExcelReader)
    def get_excel_data(self, file_path, sheet_name=None):
        """Get comprehensive data from Excel file."""
        return self._reader.get_excel_data(file_path, sheet_name)

    def read_software_lines(self, file_path, sheet_name=None):
        """Read software lines from Excel file."""
        return self._reader.read_software_lines(file_path, sheet_name)

    def get_sheet_names(self, file_path):
        """Get all sheet names from Excel file."""
        return self._reader.get_sheet_names(file_path)

    def get_column_values_by_header(self, file_path, header_value, sheet_name=None):
        """Get values from a specific column identified by its header."""
        return self._reader.get_column_values_by_header(file_path, header_value, sheet_name)

    # Mapping methods (delegated to MappingHandler)
    def clean_software_line(self, sw_line):
        """Clean software line for matching."""
        return self._mapper.clean_software_line(sw_line)

    def create_mapping(self, software_lines, json_data, master_data):
        """Create mapping between software lines and latest artifacts JSON data."""
        return self._mapper.create_mapping(software_lines, json_data, master_data)

    # Report generation methods (delegated to ReportGenerator)
    def generate_report(self, mapping, output_file):
        """Generate Excel report with mapping results."""
        return self._reporter.generate_report(mapping, output_file)


__all__ = [
    'DirectoryHandler',
    'ExcelHandler',
    'ExcelReader',
    'MappingHandler',
    'ReportGenerator',
]

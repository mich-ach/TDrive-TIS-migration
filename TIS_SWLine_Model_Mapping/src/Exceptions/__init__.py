"""Custom exceptions for TIS artifact extraction.

This module defines a hierarchy of exceptions for consistent error handling
throughout the application.

Classes:
    TISError: Base exception for all TIS-related errors
    TISAPIError: Exception for TIS API communication errors
    TISTimeoutError: Exception for TIS API timeout errors
    TISConnectionError: Exception for TIS API connection errors
    ConfigurationError: Exception for configuration-related errors
    DirectoryError: Exception for directory/file operation errors
    ExcelError: Exception for Excel file operation errors
    ValidationError: Exception for artifact validation errors
    ParsingError: Exception for data parsing errors
"""


class TISError(Exception):
    """Base exception for all TIS-related errors."""

    def __init__(self, message: str, details: str = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class TISAPIError(TISError):
    """Exception for TIS API communication errors."""

    def __init__(self, message: str, url: str = None, status_code: int = None, details: str = None):
        super().__init__(message, details)
        self.url = url
        self.status_code = status_code


class TISTimeoutError(TISAPIError):
    """Exception for TIS API timeout errors."""

    def __init__(self, message: str, url: str = None, elapsed_time: float = None):
        super().__init__(message, url)
        self.elapsed_time = elapsed_time


class TISConnectionError(TISAPIError):
    """Exception for TIS API connection errors."""
    pass


class ConfigurationError(TISError):
    """Exception for configuration-related errors."""

    def __init__(self, message: str, config_key: str = None):
        super().__init__(message)
        self.config_key = config_key


class DirectoryError(TISError):
    """Exception for directory/file operation errors."""

    def __init__(self, message: str, path: str = None):
        super().__init__(message)
        self.path = path


class ExcelError(TISError):
    """Exception for Excel file operation errors."""

    def __init__(self, message: str, file_path: str = None, sheet_name: str = None):
        super().__init__(message)
        self.file_path = file_path
        self.sheet_name = sheet_name


class ValidationError(TISError):
    """Exception for artifact validation errors."""

    def __init__(self, message: str, artifact_id: str = None, deviation_type: str = None):
        super().__init__(message)
        self.artifact_id = artifact_id
        self.deviation_type = deviation_type


class ParsingError(TISError):
    """Exception for data parsing errors (JSON, dates, versions, etc.)."""

    def __init__(self, message: str, raw_value: str = None):
        super().__init__(message)
        self.raw_value = raw_value

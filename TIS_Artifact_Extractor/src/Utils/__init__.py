"""Utility functions for TIS artifact extraction.

This module provides utility functions for date/time conversion and version parsing.

Classes:
    VersionParser: Parser for extracting version information from various formats

Functions:
    convert_ticks_to_iso: Convert .NET DateTime ticks to formatted date string
    parse_ticks_to_datetime: Parse .NET DateTime ticks to Python datetime
    format_datetime: Format a datetime object using the configured format
    is_date_in_past: Check if a datetime is in the past
    get_current_timestamp: Get current timestamp formatted for filenames
"""

import datetime
import json
import logging
import re
from typing import List, Dict, Any, Optional, Union

from config import DATE_DISPLAY_FORMAT, VEMOX_SVN_PATTERN, VEMOX_CONAN_PATTERN, VEMOX_SEARCH_PATH

logger = logging.getLogger(__name__)

# .NET epoch difference: seconds between 0001-01-01 and 1970-01-01
DOTNET_EPOCH_DIFF = 62135596800


# =============================================================================
# DATE/TIME UTILITIES
# =============================================================================

def convert_ticks_to_iso(ticks_value: str) -> Optional[str]:
    """
    Convert .NET DateTime ticks to formatted date string.

    .NET DateTime ticks are 100-nanosecond intervals since January 1, 0001.
    TIS API returns dates in this format (e.g., "638349664128090000").

    The output format is configurable via DATE_DISPLAY_FORMAT in config.json.
    Default format: "%d-%m-%Y %H:%M:%S" (e.g., "03-10-2023 09:06:28")

    Args:
        ticks_value: The ticks value as string, or ISO date string

    Returns:
        Formatted date string or None if conversion fails
    """
    if not ticks_value:
        return None

    try:
        # Check if it's already an ISO date string - convert to configured format
        if 'T' in str(ticks_value) or '-' in str(ticks_value):
            try:
                iso_str = str(ticks_value)
                if iso_str.endswith('Z'):
                    iso_str = iso_str[:-1]
                dt = datetime.datetime.fromisoformat(iso_str.split('.')[0])
                return dt.strftime(DATE_DISPLAY_FORMAT)
            except (ValueError, TypeError):
                return str(ticks_value)

        # Convert .NET ticks (100-nanosecond intervals since 0001-01-01)
        ticks = int(ticks_value)

        # Convert 100-nanosecond intervals to seconds
        unix_timestamp = (ticks / 10_000_000) - DOTNET_EPOCH_DIFF

        # Convert to datetime and format using configured display format
        dt = datetime.datetime.utcfromtimestamp(unix_timestamp)
        return dt.strftime(DATE_DISPLAY_FORMAT)

    except (ValueError, TypeError, OSError) as e:
        logger.debug(f"Failed to convert ticks '{ticks_value}': {e}")
        return None


def parse_ticks_to_datetime(ticks_value: str) -> Optional[datetime.datetime]:
    """
    Parse .NET DateTime ticks to a Python datetime object.

    Handles both ticks format (e.g., "638349664128090000") and ISO format.
    Returns None if parsing fails.

    Args:
        ticks_value: The ticks value as string, or ISO date string

    Returns:
        Python datetime object (UTC) or None if parsing fails
    """
    if not ticks_value:
        return None

    try:
        value_str = str(ticks_value)

        # Check if it's ISO format (contains 'T' or '-')
        if 'T' in value_str or '-' in value_str:
            iso_str = value_str
            if iso_str.endswith('Z'):
                iso_str = iso_str[:-1] + '+00:00'
            result = datetime.datetime.fromisoformat(iso_str.split('.')[0]).replace(
                tzinfo=datetime.timezone.utc
            )
            logger.debug(f"Parsed ISO format '{value_str}' -> {result}")
            return result

        # Parse .NET ticks (100-nanosecond intervals since 0001-01-01)
        ticks = int(value_str)
        unix_timestamp = (ticks / 10_000_000) - DOTNET_EPOCH_DIFF
        result = datetime.datetime.utcfromtimestamp(unix_timestamp).replace(
            tzinfo=datetime.timezone.utc
        )
        logger.debug(f"Parsed ticks '{value_str}' -> {result}")
        return result

    except (ValueError, TypeError, OSError) as e:
        logger.debug(f"Failed to parse datetime '{ticks_value}': {e}")
        return None


def format_datetime(dt: datetime.datetime, format_str: str = None) -> str:
    """
    Format a datetime object using the configured format.

    Args:
        dt: The datetime object to format
        format_str: Optional format string (defaults to DATE_DISPLAY_FORMAT)

    Returns:
        Formatted date string
    """
    fmt = format_str or DATE_DISPLAY_FORMAT
    return dt.strftime(fmt)


def is_date_in_past(dt: datetime.datetime) -> bool:
    """
    Check if a datetime is in the past (before now).

    Args:
        dt: The datetime to check (should be UTC)

    Returns:
        True if the datetime is in the past
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # Ensure dt has timezone info
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    return dt <= now


def get_current_timestamp() -> str:
    """
    Get current timestamp formatted for filenames.

    Returns:
        Timestamp string in format YYYYMMDD_HHMMSS
    """
    return datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


# =============================================================================
# VERSION PARSER
# =============================================================================

class VersionParser:
    """Parser for extracting version information from various formats."""

    def find_vemox_versions(self, data: Union[str, List, Dict], path_value: str = VEMOX_SEARCH_PATH) -> List[str]:
        """Find VeMox versions in externals where path contains path_value."""
        logger.debug(f"Starting VeMox version search with path_value: {path_value}")

        try:
            # Handle JSON string input
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                    logger.debug("Successfully parsed JSON string")
                except json.JSONDecodeError as e:
                    logger.debug(f"Error parsing JSON: {e}")
                    return []

            # Handle both list and single item inputs
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                logger.debug(f"Unexpected data type: {type(data)}")
                return []

            versions = set()
            for item in data:
                if not isinstance(item, dict):
                    logger.debug(f"Skipping non-dict item: {item}")
                    continue

                source_type = item.get('type', '').upper()
                logger.debug(f"Processing source type: {source_type}")

                if source_type == "SVN":
                    svn_versions = self._find_svn_versions(item, path_value)
                    logger.debug(f"Found SVN versions: {svn_versions}")
                    versions.update(svn_versions)
                elif source_type == "CONAN":
                    conan_version = self._find_conan_version(item)
                    logger.debug(f"Found CONAN version: {conan_version}")
                    if conan_version:
                        versions.add(conan_version)

            result = sorted(list(versions))
            logger.debug(f"Final versions found: {result}")
            return result

        except Exception as e:
            logger.error(f"Error processing versions: {e}")
            return []

    def _find_svn_versions(self, item: Dict[str, Any], path_value: str) -> List[str]:
        """Extract VeMox versions from SVN externals."""
        logger.debug("Processing SVN externals")
        versions = set()
        try:
            externals = item.get('externals', [])

            if isinstance(externals, list):
                for external in externals:
                    if isinstance(external, dict):
                        path = external.get('path', '').lower()
                        url = external.get('url', '')

                        # Normalize path_value and path for comparison
                        normalized_path_value = path_value.lower().replace('\\', '/')
                        normalized_path = path.replace('\\', '/')

                        # Check if path ends with the normalized path_value
                        if normalized_path.endswith(normalized_path_value):
                            vemox_part = self._extract_vemox_from_svn_url(url)
                            if vemox_part:
                                versions.add(vemox_part)
                            else:
                                logger.debug("No VeMox version found in URL")

                return sorted(list(versions))
        except Exception as e:
            logger.error(f"Error extracting SVN versions: {e}")
            return []

    def _find_conan_version(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract VeMox version from CONAN package."""
        try:
            package = item.get('package', '')
            if not package:
                return None

            version = self._extract_vemox_from_conan_package(package)
            if version:
                # Additional validation for Conan version format
                if re.match(r'^VeMox\d{3}R\d{2}$', version):
                    return version
            return None
        except Exception as e:
            logger.error(f"Error extracting CONAN version: {e}")
            return None

    def _extract_vemox_from_svn_url(self, url: str) -> Optional[str]:
        """Extract VeMox version from SVN URL."""
        logger.debug(f"Extracting VeMox from URL: {url}")
        try:
            url_parts = url.split("/")
            for part in url_parts:
                # Look for version pattern like vemox1.2.3.4.5
                version_match = re.search(
                    r'vemox(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)',
                    part,
                    re.IGNORECASE
                )
                if version_match:
                    groups = version_match.groups()
                    version = f"VeMox{groups[0]}{groups[1]}{groups[2]}R{groups[3]}{groups[4]}"
                    logger.debug(f"Found version: {version}")
                    return version

                # Check general VeMox pattern
                if re.match(VEMOX_SVN_PATTERN, part, re.IGNORECASE):
                    version = self._format_vemox_version(part)
                    logger.debug(f"Found version using general pattern: {version}")
                    return version

            logger.debug("No VeMox version found in URL")
            return None
        except Exception as e:
            logger.error(f"Error extracting SVN version: {e}")
            return None

    def _extract_vemox_from_conan_package(self, package: str) -> Optional[str]:
        """Extract VeMox version from CONAN package string."""
        try:
            match = re.search(VEMOX_CONAN_PATTERN, package)
            if match:
                version = match.group(1)
                return self._format_vemox_version(version)
            return None
        except Exception as e:
            logger.error(f"Error extracting CONAN version: {e}")
            return None

    def _format_vemox_version(self, version: str) -> str:
        """Format VeMox version string (e.g., '1.2.3.4.5' -> 'VeMox123R45')."""
        try:
            # First try to extract version numbers if input is like 'vemox1.2.3.4.5'
            version_match = re.search(
                r'(?:vemox)?(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)',
                version,
                re.IGNORECASE
            )
            if version_match:
                groups = version_match.groups()
                return f"VeMox{groups[0]}{groups[1]}{groups[2]}R{groups[3]}{groups[4]}"

            # If that fails, try splitting by dots
            parts = version.split('.')
            if len(parts) >= 5:
                return f"VeMox{parts[0]}{parts[1]}{parts[2]}R{parts[3]}{parts[4]}"

            return version
        except Exception as e:
            logger.error(f"Error formatting version {version}: {e}")
            return version

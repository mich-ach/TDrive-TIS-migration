"""Date and time utilities for TIS artifact extraction.

This module provides functions for converting between different
date formats used by the TIS API and the application.
"""

import datetime
import logging
from typing import Optional

from config import DATE_DISPLAY_FORMAT

logger = logging.getLogger(__name__)

# .NET epoch difference: seconds between 0001-01-01 and 1970-01-01
DOTNET_EPOCH_DIFF = 62135596800


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

"""Artifact filtering logic for TIS extraction.

This module handles all artifact filtering decisions based on:
- Component type, name, and group
- Life cycle status
- Deletion status
"""

import datetime
import logging
import re
from typing import List, Dict, Optional

from config import (
    COMPONENT_TYPE_FILTER,
    COMPONENT_NAME_FILTER,
    COMPONENT_GRP_FILTER,
    LIFE_CYCLE_STATUS_FILTER,
    SKIP_DELETED_ARTIFACTS,
    SKIP_FOLDER_PATTERNS,
)
from datetime_utils import parse_ticks_to_datetime

logger = logging.getLogger(__name__)


class ArtifactFilter:
    """
    Filters artifacts based on configured criteria.

    This class encapsulates all filtering logic that was previously
    scattered throughout TISAPIService.
    """

    def __init__(
        self,
        component_type_filter: Optional[List[str]] = None,
        component_name_filter: Optional[List[str]] = None,
        component_grp_filter: Optional[str] = None,
        life_cycle_status_filter: Optional[List[str]] = None,
        skip_deleted: bool = True,
        skip_folder_patterns: Optional[List[str]] = None
    ):
        """
        Initialize the artifact filter.

        Args:
            component_type_filter: List of allowed component types (e.g., ["vVeh"])
            component_name_filter: List of allowed component names (e.g., ["vVeh_LCO"])
            component_grp_filter: Required component group (e.g., "TIS Artifact Container")
            life_cycle_status_filter: List of allowed statuses (e.g., ["released", "archived"])
            skip_deleted: Whether to skip deleted artifacts
            skip_folder_patterns: List of regex patterns for folders to skip
        """
        self.component_type_filter = component_type_filter or COMPONENT_TYPE_FILTER
        self.component_name_filter = component_name_filter or COMPONENT_NAME_FILTER
        self.component_grp_filter = component_grp_filter or COMPONENT_GRP_FILTER
        self.life_cycle_status_filter = life_cycle_status_filter or LIFE_CYCLE_STATUS_FILTER
        self.skip_deleted = skip_deleted if skip_deleted is not None else SKIP_DELETED_ARTIFACTS

        # Compile skip patterns
        patterns = skip_folder_patterns or SKIP_FOLDER_PATTERNS
        self._skip_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        logger.debug(f"Loaded {len(self._skip_patterns)} skip patterns")

    def should_include_artifact(
        self,
        component_type: Optional[str],
        component_name: Optional[str],
        component_grp: Optional[str],
        attributes: List[Dict],
        has_artifact_attr: bool
    ) -> bool:
        """
        Determine if an artifact should be included based on all filters.

        Args:
            component_type: The componentType.name value (e.g., "vVeh")
            component_name: The component.name value (e.g., "vVeh_LCO")
            component_grp: The componentGrp.name value (e.g., "TIS Artifact Container")
            attributes: List of attribute dictionaries from the API
            has_artifact_attr: Whether the artifact has an 'artifact' attribute

        Returns:
            True if the artifact should be included, False otherwise
        """
        # Must have artifact attribute
        if not has_artifact_attr:
            return False

        # Check component type filter
        if not self._matches_type_filter(component_type):
            logger.debug(f"Rejected: type '{component_type}' not in filter")
            return False

        # Check component name filter
        if not self._matches_name_filter(component_name):
            logger.debug(f"Rejected: name '{component_name}' not in filter")
            return False

        # Check component group filter
        if not self._matches_grp_filter(component_grp):
            logger.debug(f"Rejected: grp '{component_grp}' not in filter")
            return False

        # Check life cycle status
        life_cycle_status = self.get_life_cycle_status(attributes)
        if not self._matches_status_filter(life_cycle_status):
            logger.debug(f"Rejected: status '{life_cycle_status}' not in filter")
            return False

        # Check deletion status
        if self.skip_deleted and self.is_artifact_deleted(attributes):
            logger.debug("Rejected: artifact is deleted")
            return False

        return True

    def _matches_type_filter(self, component_type: Optional[str]) -> bool:
        """Check if component type matches filter."""
        if self.component_type_filter is None:
            return True
        return component_type in self.component_type_filter

    def _matches_name_filter(self, component_name: Optional[str]) -> bool:
        """Check if component name matches filter."""
        if self.component_name_filter is None:
            return True
        return component_name in self.component_name_filter

    def _matches_grp_filter(self, component_grp: Optional[str]) -> bool:
        """Check if component group matches filter."""
        if self.component_grp_filter is None:
            return True
        return component_grp == self.component_grp_filter

    def _matches_status_filter(self, life_cycle_status: Optional[str]) -> bool:
        """Check if life cycle status matches filter."""
        if not self.life_cycle_status_filter:
            return True
        return life_cycle_status in self.life_cycle_status_filter

    @staticmethod
    def get_life_cycle_status(attributes: List[Dict]) -> Optional[str]:
        """
        Get the lifeCycleStatus value from attributes.

        Args:
            attributes: List of attribute dictionaries

        Returns:
            The life cycle status string or None
        """
        for attr in attributes:
            if attr.get('name') == 'lifeCycleStatus':
                return attr.get('value')
        return None

    @staticmethod
    def is_artifact_deleted(attributes: List[Dict]) -> bool:
        """
        Check if an artifact is deleted based on tisFileDeletedDate attribute.

        An artifact is considered deleted only if:
        1. It has a tisFileDeletedDate attribute with a non-null value
        2. The deletion date has already passed (is in the past)

        Args:
            attributes: List of attribute dictionaries

        Returns:
            True if the artifact is deleted, False otherwise
        """
        for attr in attributes:
            if attr.get('name') == 'tisFileDeletedDate':
                deleted_date_str = attr.get('value')
                logger.debug(f"Found tisFileDeletedDate: {deleted_date_str}")

                if deleted_date_str:
                    deleted_date = parse_ticks_to_datetime(deleted_date_str)
                    if deleted_date:
                        now = datetime.datetime.now(datetime.timezone.utc)
                        is_deleted = deleted_date <= now
                        logger.debug(f"Deletion check: date={deleted_date}, now={now}, deleted={is_deleted}")
                        return is_deleted
                    # If date parsing fails, assume NOT deleted (safe default)
                    return False
        return False

    @staticmethod
    def has_artifact_attribute(attributes: List[Dict]) -> bool:
        """
        Check if attributes contain an 'artifact' attribute.

        Args:
            attributes: List of attribute dictionaries

        Returns:
            True if artifact attribute exists
        """
        return any(attr.get('name') == 'artifact' for attr in attributes)

    def should_skip_folder(self, folder_name: str) -> bool:
        """
        Determine if a folder should be skipped based on naming patterns.

        Args:
            folder_name: Name of the folder to check

        Returns:
            True if the folder should be skipped
        """
        for pattern in self._skip_patterns:
            if pattern.match(folder_name):
                logger.debug(f"Skipping folder '{folder_name}' - matched pattern: {pattern.pattern}")
                return True
        return False

    def get_filter_summary(self) -> Dict:
        """Get a summary of current filter settings."""
        return {
            'component_type_filter': self.component_type_filter,
            'component_name_filter': self.component_name_filter,
            'component_grp_filter': self.component_grp_filter,
            'life_cycle_status_filter': self.life_cycle_status_filter,
            'skip_deleted': self.skip_deleted,
            'skip_patterns_count': len(self._skip_patterns)
        }

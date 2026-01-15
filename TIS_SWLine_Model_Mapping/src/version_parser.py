"""Utilities for parsing version information from various sources."""

import re
import json
import logging
from typing import List, Dict, Any, Optional, Union

from config import VEMOX_SVN_PATTERN, VEMOX_CONAN_PATTERN, VEMOX_SEARCH_PATH

# Setup logger for this module
logger = logging.getLogger(__name__)


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
